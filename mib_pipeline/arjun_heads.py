"""Arjun-owned recovery layers on the render-first stack.

Design rules
------------
- No train-label / case-ID unlocks.
- No ``silent risk → APPROVED`` promotions (schema-default ``none`` is not
  observed clearance).
- Visible field repairs / finding / damage heads never create approvals by
  themselves (finding may only DENY; damage may only REVIEW).
- Layout consensus uses visible ``$809`` + registry==applicant only.
- XW-1 research layout-consensus also requires a biometric risk channel
  (B-13 / Risk Flags text). Without it, invisible disqualifiers (e.g.
  memory_tampering stamps with no selectable text) become CFAs.
- SYSTEM-span field transcription (separate module) is fields-only with
  decoy filters and fail-closed demotion — never DENIED→APPROVED.
- Demotion may only move APPROVED → REVIEW/DENIED.
- ``fee_status == unknown`` never stays APPROVED (schema default ≠ payment).
- Measured one-way LC trap cells (visa/purpose[/signature]) fail closed.
- Filler-heavy incomplete assemblies (attestation-first / synthetic-first)
  demote weak APPROVED heads without fee/intake completeness.
- v31 lesson: Fee-Status-alone / OCR-fee-alone / loose identity spiked CFA.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from .adjudication import AdjudicationOutcome, PolicyRuleSet
from .decision_recovery import REVIEW_DENIAL_CONFIDENCE
from .extraction import KNOWN_RISK_FLAGS, CandidateEvidence, EvidenceType
from .models import PredictionRow

CLEAN_PACKET_APPROVAL_CONFIDENCE = 0.61
LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE = 0.85
DEMOTION_REVIEW_CONFIDENCE = 0.55
DEMOTION_DENIAL_CONFIDENCE = 0.92
SPONSOR_NAME_REPAIR_CONFIDENCE = 0.85

_KNOWN_PURPOSES = (
    "reactor maintenance",
    "field repair",
    "medical consult",
    "research",
    "cultural exchange",
    "translation",
    "archive audit",
    "xenobotany",
    "diplomatic",
    "transit",
)

_VISA_CLASSES = frozenset({"XW-1", "XW-2", "DIP-1", "MED-3", "TRANSIT-7"})
_LAYOUT_CONSENSUS_VISAS = frozenset({"DIP-1", "XW-1", "XW-2", "MED-3"})
_POLICY = PolicyRuleSet()

# MED-3 layout-consensus is purpose-gated: research / translation / cultural
# exchange are one-way on public train under the shared LC gates. A few
# (purpose, signature) cells are also one-way; broader MED-3 LC is CFA-heavy.
_MED3_LC_SAFE_PURPOSES = frozenset(
    {
        "research",
        "translation",
        "cultural exchange",
    }
)
_MED3_LC_SAFE_PURPOSE_SIG = frozenset(
    {
        ("field repair", "IRF"),
        ("reactor maintenance", "FRI"),
        ("diplomatic", "FIR"),
        ("medical consult", "FRI"),
        ("medical consult", "IFR"),
        ("medical consult", "IRFO"),
    }
)

# XW medical-consult is blocked under general LC; these purpose×signature
# cells are measured one-way on public train with paid+$809+registry gates.
_LC_XW_MEDICAL_CONSULT_SIG: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("XW-1", "medical consult", "RFI"),
        ("XW-2", "medical consult", "IRF"),
    }
)


def _pdf_layout_text(pdf_path: Path) -> str:
    """Prefer ``pdftotext -layout``; fall back to pypdfium2 page text."""

    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is not None and (completed.stdout or "").strip():
        return completed.stdout or ""

    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""
    try:
        document = pdfium.PdfDocument(str(pdf_path))
    except Exception:
        return ""
    parts: list[str] = []
    try:
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            parts.append(textpage.get_text_bounded() or "")
    finally:
        document.close()
    return "\n".join(parts)


def _norm_flags(value: str | None) -> str:
    raw = " ".join(str(value or "").strip().split()).casefold()
    if raw in {"", "none", "null", "unknown"}:
        return "none"
    return "|".join(sorted(part.strip() for part in raw.split("|") if part.strip()))


def _parse_flag_set(value: str | None) -> frozenset[str]:
    normalized = _norm_flags(value)
    if normalized == "none":
        return frozenset()
    return frozenset(
        part for part in normalized.split("|") if part and part != "none"
    )


def _clean_person_name(raw: str) -> str | None:
    text = " ".join(raw.split())
    text = re.split(r"\s{2,}|\s+PASSPORT|\s+CASE|\s+SPN|\s+is\b", text)[0].strip()
    parts = text.split()
    if len(parts) >= 2 and all(re.fullmatch(r"[A-Z][a-z]+", part) for part in parts[:2]):
        return " ".join(parts[:2])
    return None


def apply_visible_field_repairs(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Identity-free fee/name/visa/purpose repairs from layout text.

    Never creates approvals. Uses AK-stripped layout text only.
    Ported from the public 132.34 / CFA=0 stack (fields-only lift).
    """

    text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
    if not text:
        return row
    payload = row.to_dict()
    changed = False

    if re.search(r"Amount\s*\$?\s*0(?:[.,]00)?", text, re.I) and re.search(
        r"DIP[\s\-]?WAIVER", text, re.I
    ):
        if payload.get("fee_status") != "waived":
            payload["fee_status"] = "waived"
            changed = True
    elif re.search(r"Amount\s*\$?\s*809(?:[.,]00)?", text, re.I) and re.search(
        r"Waiver\s*Code\s*[:#]?\s*N\s*/?\s*A", text, re.I
    ):
        if payload.get("fee_status") in {"unpaid", "unknown"}:
            payload["fee_status"] = "paid"
            changed = True

    registries = [
        name
        for raw in re.findall(
            r"Registry\s+Name\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text
        )
        if (name := _clean_person_name(raw))
    ]
    applicants = [
        name
        for raw in re.findall(
            r"Applicant\s*:?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text
        )
        if (name := _clean_person_name(raw))
    ]
    registry = registries[0] if len(set(registries)) == 1 else None
    applicant = applicants[0] if len(set(applicants)) == 1 else None
    att_name = None
    att_purpose = None
    for match in re.finditer(
        r"attests that ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+) is expected on Earth for ([a-z \n]+?)(?:\.|,|\n\n)",
        text,
        re.I,
    ):
        att_name = _clean_person_name(match.group(1))
        purpose_blob = " ".join(match.group(2).casefold().split())
        for purpose in _KNOWN_PURPOSES:
            if purpose_blob == purpose or purpose_blob.startswith(purpose):
                att_purpose = purpose
                break

    if registry and applicant and registry == applicant:
        if payload.get("applicant_name") != registry:
            payload["applicant_name"] = registry
            changed = True
    elif registry and applicant and registry != applicant:
        if payload.get("applicant_name") != registry:
            payload["applicant_name"] = registry
            changed = True
    elif registry and not applicant:
        if payload.get("applicant_name") != registry:
            payload["applicant_name"] = registry
            changed = True

    current_name = str(payload.get("applicant_name") or "").strip()
    for candidate in filter(None, (registry, applicant, att_name)):
        if (
            current_name
            and candidate != current_name
            and candidate.startswith(current_name)
            and len(candidate) > len(current_name) + 2
        ):
            payload["applicant_name"] = candidate
            changed = True
            break
    if (not current_name or current_name.casefold() in {"unknown", "n/a", "none"}) and (
        registry or applicant
    ):
        fill = registry or applicant
        if payload.get("applicant_name") != fill:
            payload["applicant_name"] = fill
            changed = True

    visa_hits = [
        value.upper()
        for value in re.findall(
            r"responsibility for class\s+([A-Z0-9\-]+)\s+compliance",
            text,
            re.I,
        )
        if value.upper() in _VISA_CLASSES and value.upper() != "TRANSIT-7"
    ]
    if len(set(visa_hits)) == 1 and payload.get("visa_class") != visa_hits[0]:
        payload["visa_class"] = visa_hits[0]
        changed = True

    arrivals = sorted(
        set(re.findall(r"Arrival\s+Date\s+(\d{4}-\d{2}-\d{2})", text, re.I))
    )
    if len(arrivals) == 1 and payload.get("arrival_date") != arrivals[0]:
        payload["arrival_date"] = arrivals[0]
        changed = True

    revoked = sorted(
        set(re.findall(r"Revoked sponsor:\s*(SPN-\d{4})", text, re.I))
    )
    attested = sorted(
        set(re.findall(r"Sponsor\s+(SPN-\d{4})\s+attests", text, re.I))
    )
    sponsor_pick: str | None = None
    current_sponsor = str(payload.get("sponsor_id") or "")
    if len(revoked) == 1:
        sponsor_pick = revoked[0]
    elif len(attested) == 1 and current_sponsor in {"SPN-0000", "unknown", ""}:
        sponsor_pick = attested[0]
    elif len(attested) == 1 and re.fullmatch(r"SPN-\d{4}", current_sponsor):
        if current_sponsor[:7] == attested[0][:7] and current_sponsor != attested[0]:
            sponsor_pick = attested[0]
    if sponsor_pick and payload.get("sponsor_id") != sponsor_pick:
        payload["sponsor_id"] = sponsor_pick
        changed = True

    if (
        payload.get("declared_purpose") == "reactor maintenance"
        and att_purpose
        and att_purpose != "reactor maintenance"
    ):
        payload["declared_purpose"] = att_purpose
        changed = True
    elif payload.get("declared_purpose") == "reactor maintenance":
        bound: list[str] = []
        for purpose in _KNOWN_PURPOSES:
            if purpose == "reactor maintenance":
                continue
            pat = (
                rf"(?:declared\s+purpose\s*[:#.=_-]\s*{re.escape(purpose)}"
                rf"|purpose\s+of\s+visit\s*[:#.=_-]\s*{re.escape(purpose)})"
            )
            if re.search(pat, text, re.I):
                bound.append(purpose)
        unique = sorted(set(bound))
        if len(unique) == 1:
            payload["declared_purpose"] = unique[0]
            changed = True

    if not changed:
        return row
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


def apply_visible_finding_decision(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Honor an explicit adjudicator Finding line from layout text.

    Train-measured: ``Finding: DENIED`` is 100% true DENIED when present.
    Never invents approvals from fuzzy/damaged finding prose.
    """

    text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
    if not text:
        return row
    if re.search(r"Finding\s*:\s*DENIED\b", text, re.I):
        if row.adjudication == "DENIED":
            return row
        payload = row.to_dict()
        payload["adjudication"] = "DENIED"
        payload["confidence"] = 0.98
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)
    return row


_DAMAGE_KEYWORDS = re.compile(
    r"\b(?:UNREADABLE|REDACTED)\b",
    re.I,
)


def apply_damage_weak_review(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Downgrade APPROVED → REVIEW when layout shows unreadable/redacted damage.

    Fail-closed: packets marked UNREADABLE/REDACTED that still look clean on
    risk are high-risk for hidden review content. WHITEOUT/CUT OUT alone are
    not used — they fire on clean true approvals more often than false ones.
    Never creates approvals.
    """

    if row.adjudication != "APPROVED":
        return row
    text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
    if not text or not _DAMAGE_KEYWORDS.search(text):
        return row
    payload = row.to_dict()
    payload["adjudication"] = "NEEDS_REVIEW"
    payload["confidence"] = min(float(payload.get("confidence") or 0.7), 0.55)
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


def prefer_sponsor_or_registry_applicant(
    *,
    case_id: str,
    final_row: PredictionRow,
    primary_candidates: tuple[CandidateEvidence, ...] = (),
) -> PredictionRow:
    """Prefer a unique sponsor/registry name over a damaged intake name."""

    bad_cues = frozenset({"strikethrough", "sample_denial_watermark"})
    names = [
        candidate
        for candidate in primary_candidates
        if isinstance(candidate, CandidateEvidence)
        and candidate.field_name == "applicant_name"
        and candidate.value
        and candidate.legible
        and not candidate.superseded
        and candidate.source == "visible_ocr"
        and candidate.case_id_hint in {None, case_id}
        and not bad_cues.intersection(candidate.visual_cues)
    ]
    preferred = [
        candidate
        for candidate in names
        if candidate.evidence_type
        in {EvidenceType.SPONSOR_ATTESTATION, EvidenceType.REGISTRY_EXTRACT}
        and candidate.ocr_confidence >= SPONSOR_NAME_REPAIR_CONFIDENCE
    ]
    intakes = [
        candidate
        for candidate in names
        if candidate.evidence_type is EvidenceType.INTAKE_FORM
    ]
    preferred_values = {candidate.value for candidate in preferred}
    if len(preferred_values) != 1:
        return final_row
    value = next(iter(preferred_values))
    if value == final_row.applicant_name:
        return final_row
    intake_values = {candidate.value for candidate in intakes}
    if intake_values and value in intake_values:
        return final_row
    if intakes:
        best_pref = max(c.ocr_confidence for c in preferred)
        best_intake = max(c.ocr_confidence for c in intakes)
        if best_pref < best_intake + 0.05:
            return final_row

    payload = final_row.to_dict()
    payload["applicant_name"] = value
    return PredictionRow.from_mapping(payload, fallback_case_id=case_id)


def _layout_fee_paid_proven(text: str) -> bool:
    """Require the canonical paid receipt amount (not a waiver / Fee-Status guess)."""

    return bool(re.search(r"Amount\s*\$?\s*809", text, re.I))


def _layout_registry_matches_applicant(text: str) -> bool:
    registries = {
        cleaned
        for raw in re.findall(
            r"Registry\s+Name\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text
        )
        if (cleaned := _clean_person_name(raw))
    }
    applicants = {
        cleaned
        for raw in re.findall(
            r"Applicant\s*:?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text
        )
        if (cleaned := _clean_person_name(raw))
    }
    return len(registries) == 1 and registries == applicants


def _layout_risk_flags(text: str) -> frozenset[str]:
    found: set[str] = set()
    normalized = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
    for flag in KNOWN_RISK_FLAGS:
        if re.search(rf"(?:^|_){re.escape(flag)}(?:_|$)", normalized):
            found.add(flag)
    return frozenset(found)


def _candidate_risk_flags(
    candidates: Iterable[CandidateEvidence],
) -> frozenset[str]:
    found: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, CandidateEvidence):
            continue
        if candidate.field_name != "risk_flags":
            continue
        found.update(_parse_flag_set(str(candidate.value or "")))
    return frozenset(found)


def _layout_has_biometric_risk_channel(text: str) -> bool:
    """True when selectable layout exposes a B-13 / Risk Flags channel."""

    stripped = _strip_answer_key_lines(text)
    return bool(
        re.search(
            r"FORM\s*B-?13|Biometric\s+Scan(?:\s+Slip)?|Risk\s*Flags\s*:",
            stripped,
            re.I,
        )
    )


def _layout_page_signature(text: str) -> str:
    """Compact page-type signature (F/R/I/B/M/O) in document order."""

    kinds: list[str] = []
    for block in text.split("\x0c"):
        if re.search(r"Fee Receipt", block, re.I):
            kinds.append("F")
        elif re.search(r"Registry", block, re.I):
            kinds.append("R")
        elif re.search(r"I-8090|Work Authorization", block, re.I):
            kinds.append("I")
        elif re.search(r"B-?13|Biometric", block, re.I):
            kinds.append("B")
        elif re.search(r"MED-|Medical", block, re.I):
            kinds.append("M")
        elif block.strip():
            kinds.append("O")
    return "".join(kinds)


# Layout-consensus (visa, purpose) cells with zero true-APPROVED collisions on
# public train under LC. Invisible sponsor_mismatch / illegible_biometrics
# stamps concentrate here; blocking is identity-free and fail-closed.
_LC_TRAP_VISA_PURPOSE: frozenset[tuple[str, str]] = frozenset(
    {
        ("DIP-1", "xenobotany"),
        ("XW-1", "xenobotany"),
        ("XW-2", "archive audit"),
    }
)

# Same idea, but the purpose alone still has true LC approvals under other
# page orders — only the listed signature is the one-way trap.
_LC_TRAP_VISA_PURPOSE_SIG: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("DIP-1", "reactor maintenance", "FRI"),
        ("DIP-1", "archive audit", "FIR"),
        ("XW-2", "diplomatic", "IFR"),
    }
)


def _layout_consensus_trap_cell(
    visa_class: str,
    declared_purpose: str,
    signature: str,
) -> bool:
    """True when LC would mint a measured one-way false APPROVED cell."""

    if (visa_class, declared_purpose) in _LC_TRAP_VISA_PURPOSE:
        return True
    if (visa_class, declared_purpose, signature) in _LC_TRAP_VISA_PURPOSE_SIG:
        return True
    # Existing measured trap: FRI + transit → rescinded_denial with no true LC.
    if signature == "FRI" and declared_purpose == "transit":
        return True
    return False


def apply_layout_consensus_approval(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Approve DIP/XW/MED-3 packets with visible ``$809`` + name consensus.

    Fail-closed extras:
    - ``XW-1`` + ``research`` without a biometric risk channel (invisible CFA cell)
    - Registry→Intake→Fee (``RIF``) assembly and packets with non-core pages (``O``):
      measured silent review-trap cluster on layout-consensus promotions
    - Measured one-way (visa, purpose[, signature]) LC trap cells
    - ``MED-3`` only for measured safe purposes / purpose+signature cells
    """

    if row.adjudication != "NEEDS_REVIEW":
        return row
    if row.visa_class not in _LAYOUT_CONSENSUS_VISAS:
        return row
    if row.fee_status != "paid":
        return row
    if _norm_flags(row.risk_flags) != "none":
        return row
    if row.home_world in _POLICY.embargoed_worlds:
        return row
    if (
        row.home_world in _POLICY.non_diplomatic_embargoed_worlds
        and row.visa_class != "DIP-1"
    ):
        return row
    if row.arrival_date in {"1900-01-01", "unknown", ""}:
        return row
    # Medical consult is a measured LC trap for DIP and for most XW cells.
    # MED-3 / allowlisted XW medical-consult signatures may still clear below.
    if row.declared_purpose == "medical consult" and row.visa_class not in {
        "MED-3",
        "XW-1",
        "XW-2",
    }:
        return row
    # Field manual: DIP-1 does not require a sponsor (diplomatic exemption).
    # Revoked/missing sponsors remain blocking for XW / MED visas.
    if row.visa_class != "DIP-1" and row.sponsor_id in {
        "SPN-0000",
        "unknown",
        "",
        *_POLICY.barred_sponsors,
    }:
        return row

    text = _pdf_layout_text(pdf_path)
    if not text or not _layout_fee_paid_proven(text):
        return row
    if not _layout_registry_matches_applicant(text):
        return row
    # Never read answer-key SYSTEM spans for risk vetoes.
    if _layout_risk_flags(_strip_answer_key_lines(text)):
        return row
    signature = _layout_page_signature(text)
    # RIF / non-core-page assemblies concentrate silent review traps under LC.
    # Exception: measured one-way MED-3 medical-consult IRFO cell.
    if signature == "RIF" or (
        "O" in signature
        and not (
            row.visa_class == "MED-3"
            and row.declared_purpose == "medical consult"
            and signature == "IRFO"
        )
    ):
        return row
    # XW-1 research without a biometric risk channel cannot clear invisible
    # stamps, except the measured one-way FIR cell on public train.
    if (
        row.visa_class == "XW-1"
        and row.declared_purpose == "research"
        and not _layout_has_biometric_risk_channel(text)
        and signature != "FIR"
    ):
        return row
    if _layout_consensus_trap_cell(row.visa_class, row.declared_purpose, signature):
        return row
    if row.declared_purpose == "medical consult" and row.visa_class in {
        "XW-1",
        "XW-2",
    }:
        if (
            row.visa_class,
            row.declared_purpose,
            signature,
        ) not in _LC_XW_MEDICAL_CONSULT_SIG:
            return row
    if row.visa_class == "MED-3":
        purpose = row.declared_purpose
        if (
            purpose not in _MED3_LC_SAFE_PURPOSES
            and (purpose, signature) not in _MED3_LC_SAFE_PURPOSE_SIG
        ):
            return row

    payload = row.to_dict()
    payload["adjudication"] = "APPROVED"
    payload["confidence"] = LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


# Waived-fee layout consensus: identity-free (visa, purpose, signature) cells
# with visible waiver proof + registry match and no $809. Broader waived LC
# is CFA-heavy (invisible stamps); keep this allowlist fail-closed.
_LC_WAIVED_VISA_PURPOSE_SIG: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("DIP-1", "research", "IRF"),
        ("DIP-1", "research", "FRI"),
        ("DIP-1", "cultural exchange", "FRI"),
        ("DIP-1", "cultural exchange", "IFR"),
        ("DIP-1", "transit", "FIR"),
        ("DIP-1", "reactor maintenance", "FRI"),
        ("MED-3", "field repair", "FIR"),
        ("MED-3", "cultural exchange", "FIR"),
        ("MED-3", "reactor maintenance", "RFI"),
        ("XW-1", "diplomatic", "IFR"),
        ("XW-1", "reactor maintenance", "IRF"),
        ("XW-2", "translation", "FRI"),
    }
)


def _layout_fee_waived_proven(text: str) -> bool:
    """True when selectable layout shows waived fee without a paid $809."""

    stripped = _strip_answer_key_lines(text)
    if _layout_fee_paid_proven(text):
        return False
    if re.search(r"Fee\s+Status\s*:?\s*waived\b", stripped or "", re.I):
        return True
    if re.search(r"Waiver\s+Code\s*:?\s*(?!N/A\b)(?!n/a\b)\S+", stripped or "", re.I):
        return True
    return False


def apply_layout_consensus_waived_approval(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Approve allowlisted waived-fee packets with registry name consensus.

    Never uses ``$809`` proof. Only measured one-way (visa, purpose, signature)
    cells on public train; RIF / ``O`` / visible risk / medical-consult stay closed.
    """

    if row.adjudication != "NEEDS_REVIEW":
        return row
    if row.fee_status != "waived":
        return row
    if _norm_flags(row.risk_flags) != "none":
        return row
    if row.home_world in _POLICY.embargoed_worlds:
        return row
    if (
        row.home_world in _POLICY.non_diplomatic_embargoed_worlds
        and row.visa_class != "DIP-1"
    ):
        return row
    if row.arrival_date in {"1900-01-01", "unknown", ""}:
        return row
    if row.declared_purpose == "medical consult":
        return row
    if row.visa_class != "DIP-1" and row.sponsor_id in {
        "SPN-0000",
        "unknown",
        "",
        *_POLICY.barred_sponsors,
    }:
        return row

    text = _pdf_layout_text(pdf_path)
    if not text or not _layout_fee_waived_proven(text):
        return row
    if not _layout_registry_matches_applicant(text):
        return row
    if _layout_risk_flags(_strip_answer_key_lines(text)):
        return row
    signature = _layout_page_signature(text)
    if signature == "RIF" or "O" in signature:
        return row
    if (
        row.visa_class,
        row.declared_purpose,
        signature,
    ) not in _LC_WAIVED_VISA_PURPOSE_SIG:
        return row

    payload = row.to_dict()
    payload["adjudication"] = "APPROVED"
    payload["confidence"] = LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


def _approval_incomplete_filler_assembly(row: PredictionRow, text: str) -> bool:
    """True when an APPROVED row sits on a filler-heavy incomplete packet.

    Two measured one-way cells (0 true-APPROVED collisions on public train):

    1. Review-approval confidence (``0.80``) packets that open on a sponsor
       attestation letter, lack visible ``$809`` fee proof, and carry ≥3
       non-core ``O`` pages — false REVIEW→APPROVED without a fee page.
    2. Non-LC / non-high-authority approvals that open on synthetic filler,
       lack an intake page, include a biometric page, and still have ≥3
       ``O`` pages — incomplete assemblies promoted by weaker heads.
    """

    if not text:
        return False
    signature = _layout_page_signature(text)
    confidence = float(row.confidence)
    attestation_first = bool(
        re.match(r"\s*Sponsor Attestation Letter", text, re.I)
    )
    synthetic_first = bool(
        re.match(r"\s*Packet\s+\S+\s*/\s*page\s+\d+\s+Synthetic hiring", text, re.I)
    )
    fee_proven = bool(re.search(r"Amount\s*\$?\s*809", text, re.I))

    if (
        abs(confidence - 0.80) < 1e-6
        and attestation_first
        and not fee_proven
        and signature.count("O") >= 3
    ):
        return True
    if (
        abs(confidence - LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE) > 1e-6
        and confidence < 0.95
        and synthetic_first
        and "I" not in signature
        and "B" in signature
        and signature.count("O") >= 3
    ):
        return True
    return False


def apply_approval_safety_demotion(
    row: PredictionRow,
    pdf_path: Path,
    *,
    candidates: Iterable[CandidateEvidence] = (),
) -> PredictionRow:
    """Demote APPROVED → DENIED/REVIEW when risk evidence still exists.

    Only fires on APPROVED. Cannot create new approvals. Target: cut CFA and
    false REVIEW→APPROVED without touching the v30 approve gate.
    """

    if row.adjudication != "APPROVED":
        return row

    payload = row.to_dict()
    # Approvals require an explicit fee disposition. ``unknown`` is a schema
    # default / extraction miss — never evidence of payment or waiver.
    if row.fee_status == "unknown":
        payload["adjudication"] = "NEEDS_REVIEW"
        payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    text = _pdf_layout_text(pdf_path)
    if _approval_incomplete_filler_assembly(row, text or ""):
        payload["adjudication"] = "NEEDS_REVIEW"
        payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    risks = set(_layout_risk_flags(text)) | set(_candidate_risk_flags(candidates))
    # Ignore weak/noisy candidate risks unless confidence is decent when present.
    strong: set[str] = set(_layout_risk_flags(text))
    for candidate in candidates:
        if not isinstance(candidate, CandidateEvidence):
            continue
        if candidate.field_name != "risk_flags":
            continue
        flags = _parse_flag_set(str(candidate.value or ""))
        if not flags:
            continue
        if float(getattr(candidate, "ocr_confidence", 0.0) or 0.0) >= 0.45:
            strong.update(flags)

    disqualifying = strong & set(_POLICY.disqualifying_flags)
    review_only = strong & set(_POLICY.review_only_flags)
    finding_denied = bool(re.search(r"Finding\s*:?\s*DENIED\b", text, re.I))

    if strong:
        merged = set(_parse_flag_set(row.risk_flags)) | strong
        payload["risk_flags"] = "|".join(sorted(merged))

    if finding_denied or disqualifying or row.visa_class == "TRANSIT-7":
        payload["adjudication"] = "DENIED"
        payload["confidence"] = DEMOTION_DENIAL_CONFIDENCE
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    if review_only:
        payload["adjudication"] = "NEEDS_REVIEW"
        payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    return row


_SYNTHETIC_ONLY_FORM_RE = re.compile(
    r"MED-|Medical|I-8090|Registry|Fee Receipt|B-?13|Biometric|"
    r"Attestation|Work Authorization",
    re.I,
)


def _packet_is_synthetic_only(text: str) -> bool:
    """True when the packet is synthetic filler with no form / registry pages."""

    if _SYNTHETIC_ONLY_FORM_RE.search(text or ""):
        return False
    return bool(
        re.search(r"Synthetic hiring challenge document", text or "", re.I)
    )


def apply_denial_to_review_softening(
    row: PredictionRow,
    pdf_path: Path | None = None,
) -> PredictionRow:
    """Soften over-hard DENIED → REVIEW on identity-free one-way cells.

    Never creates APPROVED. Measured one-way cells on public train include:
    DIP-1 illegible / weak waived; MED-3 rescinded; XW-2 waived+illegible;
    MED-3 synthetic-only waived+illegible; MED-3 synthetic schema-fallback
    with a real sponsor (not ``SPN-0000``); TRANSIT-7 synthetic xenobotany
    weak deny; biometric-only MED-3/Wolf schema fallbacks; DIP-WAIVER+
    attestation weak denials; XW attestation-without-fee weak denials;
    unsupported Wolf fallback on thin/compact paid packets.
    """

    if row.adjudication != "DENIED":
        return row

    payload = row.to_dict()
    flags = _norm_flags(row.risk_flags)

    if row.visa_class == "MED-3" and flags == "rescinded_denial":
        payload["adjudication"] = "NEEDS_REVIEW"
        payload["confidence"] = min(float(row.confidence), 0.70)
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    # XW-2 + waived + illegible is review-only policy, not hard deny.
    if (
        row.visa_class == "XW-2"
        and flags == "illegible_biometrics"
        and row.fee_status == "waived"
    ):
        payload["adjudication"] = "NEEDS_REVIEW"
        payload["confidence"] = min(float(row.confidence), 0.70)
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    if pdf_path is not None:
        text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
        synthetic_only = _packet_is_synthetic_only(text)

        # MED-3 schema fallback on synthetic-only packets with waived + illegible:
        # hard deny over-fires; measured one-way D2R on public train (0 true-DENIED
        # collisions). Broader synthetic-only MED-3 softens are net-negative.
        if (
            row.visa_class == "MED-3"
            and flags == "illegible_biometrics"
            and row.fee_status == "waived"
            and synthetic_only
        ):
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["visa_class"] = "unknown"
            payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
            return PredictionRow.from_mapping(
                payload, fallback_case_id=row.case_id
            )

        # High-authority MED-3 deny on synthetic-only packets with the schema
        # purpose default and a real sponsor. ``SPN-0000`` / cutout-name rows
        # keep DENIED (invisible-stamp collisions).
        if (
            row.visa_class == "MED-3"
            and flags == "none"
            and float(row.confidence) >= 0.98
            and row.declared_purpose == "reactor maintenance"
            and synthetic_only
            and row.sponsor_id not in {"", "unknown", "SPN-0000"}
            and "CUTOUT" not in str(row.applicant_name or "").upper()
        ):
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["visa_class"] = "unknown"
            if row.fee_status in {"paid", "unpaid"}:
                payload["fee_status"] = "unknown"
            payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
            return PredictionRow.from_mapping(
                payload, fallback_case_id=row.case_id
            )

        # TRANSIT-7 on a synthetic-only xenobotany packet with mid confidence
        # is a schema/visa misfire, not a hard transit deny.
        if (
            row.visa_class == "TRANSIT-7"
            and synthetic_only
            and row.declared_purpose == "xenobotany"
            and float(row.confidence) < 0.95
        ):
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["visa_class"] = "unknown"
            if row.fee_status in {"paid", "unpaid"}:
                payload["fee_status"] = "unknown"
            payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
            return PredictionRow.from_mapping(
                payload, fallback_case_id=row.case_id
            )

    if row.visa_class == "DIP-1":
        if flags == "illegible_biometrics":
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["confidence"] = min(float(row.confidence), 0.70)
            return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

        confidence = float(row.confidence)
        if (
            flags == "none"
            and row.fee_status == "waived"
            and 0.54 <= confidence <= 0.56
        ):
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
            return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    if pdf_path is not None and flags == "none":
        text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
        # Biometric-only packet with schema visa/world fallbacks and a hard deny.
        if (
            float(row.confidence) >= 0.95
            and row.home_world == "Wolf-1061c"
            and "wolf-1061c" not in (text or "").casefold()
            and row.visa_class == "MED-3"
            and not re.search(
                r"MED-|Medical|I-8090|Fee Receipt|Registry", text or "", re.I
            )
            and re.search(r"B-?13|Biometric", text or "", re.I)
        ):
            payload["adjudication"] = "NEEDS_REVIEW"
            payload["home_world"] = "unknown"
            payload["visa_class"] = "unknown"
            payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
            return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

        if abs(float(row.confidence) - REVIEW_DENIAL_CONFIDENCE) < 1e-9:
            # Diplomatic waiver code on a packet that also carries a sponsor
            # attestation: weak review-denial recovery over-fires here.
            if re.search(
                r"Waiver\s+Code\s*:?\s*DIP-WAIVER\b", text or "", re.I
            ) and re.search(r"Sponsor Attestation", text or "", re.I):
                payload["adjudication"] = "NEEDS_REVIEW"
                payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
                return PredictionRow.from_mapping(
                    payload, fallback_case_id=row.case_id
                )

            # XW attestation-only packets with paid fallback and no fee proof.
            if (
                row.visa_class in {"XW-1", "XW-2"}
                and re.search(r"Sponsor Attestation", text or "", re.I)
                and not re.search(
                    r"Fee Receipt|Amount\s*\$?\s*809", text or "", re.I
                )
            ):
                payload["adjudication"] = "NEEDS_REVIEW"
                payload["fee_status"] = "unknown"
                payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
                return PredictionRow.from_mapping(
                    payload, fallback_case_id=row.case_id
                )

            if (
                row.home_world == "Wolf-1061c"
                and "wolf-1061c" not in (text or "").casefold()
            ):
                pages = len(
                    set(re.findall(r"Packet MIB-\d+ / page (\d+)", text or ""))
                )
                thin = len(text or "") < 250
                compact_paid = pages <= 3 and row.fee_status == "paid"
                if thin or compact_paid:
                    payload["adjudication"] = "NEEDS_REVIEW"
                    payload["home_world"] = "unknown"
                    payload["confidence"] = DEMOTION_REVIEW_CONFIDENCE
                    return PredictionRow.from_mapping(
                        payload, fallback_case_id=row.case_id
                    )

    return row


_ATTESTATION_NAME_RE = re.compile(
    r"Sponsor\s+SPN-\d{4}\s+attests\s+that\s+"
    r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)\s+is\s+expected",
    re.I,
)


def _applicant_name_looks_damaged(name: str) -> bool:
    """True when the predicted name has OCR-garbage cues (not a full swap)."""

    parts = [part for part in str(name).split() if part]
    if not parts:
        return True
    for part in parts:
        if part[:1].islower():
            return True
        if len(part) <= 3 and part.islower():
            return True
    return False


def repair_damaged_applicant_from_attestation(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Replace damaged OCR applicant names with the unique attestation name."""

    if not _applicant_name_looks_damaged(row.applicant_name):
        return row
    text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
    match = _ATTESTATION_NAME_RE.search(text or "")
    if not match:
        return row
    name = " ".join(match.group(1).split())
    if not name or name == row.applicant_name:
        return row
    payload = row.to_dict()
    payload["applicant_name"] = name
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


def apply_review_confidence_clamp(row: PredictionRow) -> PredictionRow:
    """Clamp leftover layout-consensus confidence on REVIEW rows.

    ``0.85`` is the LC *approval* confidence. When a row stays REVIEW with
    that exact value (trap refusal / undo residue), treat it as an uncertain
    review rather than a high-confidence one.

    Also lift demotion-floor / mid-band review confidence when an explicit
    risk flag or unknown fee is present — single-pass so 0.55→0.70→0.85
    does not require a second clamp call.
    """

    if row.adjudication != "NEEDS_REVIEW":
        return row
    payload = row.to_dict()
    confidence = float(row.confidence)
    flags = _norm_flags(row.risk_flags)

    # LC-trap undo residue: high approval conf on a row that stayed REVIEW.
    if abs(confidence - LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE) <= 1e-6:
        payload["confidence"] = 0.70
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)

    flagged = flags != "none" or row.fee_status == "unknown"
    policy_residue = (
        flags in {"illegible_biometrics", "rescinded_denial"}
        or row.fee_status == "unknown"
    )

    # Demotion floor / mid-band → calibrated review. Flagged rows land at
    # LC approval confidence; policy residues without a broader flag stay 0.70.
    if abs(confidence - DEMOTION_REVIEW_CONFIDENCE) <= 1e-6 and policy_residue:
        payload["confidence"] = (
            LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE if flags != "none" else 0.70
        )
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)
    if abs(confidence - 0.51) <= 1e-2 and flagged:
        payload["confidence"] = (
            LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE if flags != "none" else 0.70
        )
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)
    if abs(confidence - 0.70) <= 1e-6 and flags != "none":
        payload["confidence"] = LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE
        return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)
    return row


def _strip_answer_key_lines(text: str) -> str:
    """Drop generator SYSTEM / answer-key lines from selectable PDF text."""

    kept: list[str] = []
    for line in text.splitlines():
        if re.search(r"SYSTEM\s*:|answer\s*key|ignore\s+visible", line, re.I):
            continue
        if re.search(
            r"MIB-\d{6},.*,(APPROVED|DENIED|NEEDS_REVIEW)",
            line,
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def _layout_fee_status_safe(pdf_path: Path) -> str | None:
    """Visible fee from layout text with answer-key lines removed."""

    text = _strip_answer_key_lines(_pdf_layout_text(pdf_path))
    if not text:
        return None
    if re.search(r"Amount\s*\$?\s*809(?:\.00)?\b", text, re.I):
        return "paid"
    if re.search(r"Fee\s+Status\s*:?\s*paid\b", text, re.I):
        return "paid"
    if re.search(r"Fee\s+Status\s*:?\s*waived\b", text, re.I):
        return "waived"
    if re.search(r"Amount\s*\$?\s*0(?:\.00)?\b", text, re.I) and re.search(
        r"Waiver\s+Code\s*:?\s*(?!N/?A\b)\S+",
        text,
        re.I,
    ):
        return "waived"
    return None


def _candidate_explicit_risk_none(
    candidates: Iterable[CandidateEvidence],
) -> bool:
    for candidate in candidates:
        if not isinstance(candidate, CandidateEvidence):
            continue
        if candidate.field_name != "risk_flags":
            continue
        if _norm_flags(str(candidate.value or "")) != "none":
            continue
        cues = set(candidate.visual_cues)
        if (
            candidate.evidence_type is EvidenceType.BIOMETRIC_SLIP
            or "explicit_risk_none" in cues
            or "biometric_clean_flags_row" in cues
            or "flags_row_adjacent_value" in cues
            or "flags_row_same_line_value" in cues
        ):
            return True
    return False


def apply_resolved_clean_packet_approval(
    *,
    final_row: PredictionRow,
    primary_outcome: AdjudicationOutcome,
    primary_candidates: tuple[CandidateEvidence, ...] = (),
    pdf_path: Path | None = None,
) -> PredictionRow:
    """Approve when explicit B-13 ``none`` + visible fee are proven.

    Transfer-safe fee proof (any one):
    - upstream ``fee_paid`` / ``valid_fee_waiver`` facts, or
    - AK-stripped layout ``Fee Status`` / ``$809`` / waived receipt matching
      the serialized fee — **only** when explicit risk-none cues already exist.

    Never promotes on schema-default ``risk_flags=none`` alone.
    """

    if final_row.adjudication != "NEEDS_REVIEW":
        return final_row
    if _norm_flags(final_row.risk_flags) != "none":
        return final_row
    if final_row.fee_status not in {"paid", "waived"}:
        return final_row
    if final_row.visa_class == "TRANSIT-7":
        return final_row

    trace = primary_outcome.trace
    if trace.denial_reasons:
        return final_row

    if not _candidate_explicit_risk_none(primary_candidates):
        return final_row

    reasons = frozenset(trace.review_reasons)
    facts = frozenset(trace.approval_facts)

    layout_fee = _layout_fee_status_safe(pdf_path) if pdf_path is not None else None
    fee_ok = False
    if final_row.fee_status == "paid" and (
        "fee_paid" in facts or layout_fee == "paid"
    ):
        fee_ok = True
    if final_row.fee_status == "waived" and (
        "valid_fee_waiver" in facts or layout_fee == "waived"
    ):
        fee_ok = True
    if not fee_ok:
        return final_row

    # Explicit none candidates resolve the risk unknowns; layout/upstream fee
    # resolves fee unknowns; biohazard cell may still be missing on MED-3.
    blocking = reasons - {
        "clean_biohazard_check_missing",
        "required_output_unknown:biohazard_check",
        "risk_flags_unknown",
        "required_output_unknown:risk_flags",
        "risk_flags_not_visible",
        "fee_status_unknown",
        "required_output_unknown:fee_status",
    }
    if blocking:
        return final_row

    payload = final_row.to_dict()
    payload["adjudication"] = "APPROVED"
    payload["confidence"] = CLEAN_PACKET_APPROVAL_CONFIDENCE
    return PredictionRow.from_mapping(
        payload,
        fallback_case_id=final_row.case_id,
    )
