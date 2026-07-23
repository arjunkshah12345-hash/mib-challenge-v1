"""Arjun-owned recovery layers on the render-first stack.

Design rules
------------
- No train-label / case-ID unlocks.
- No embedded PDF answer-key transcription (generator leakage / audit risk).
- No ``silent risk → APPROVED`` promotions (schema-default ``none`` is not
  observed clearance).
- Visible field repairs never create approvals by themselves.
- Layout consensus uses visible ``$809`` + registry==applicant only.
- Demotion may only move APPROVED → REVIEW/DENIED (never creates approvals).
- v31 lesson: Fee-Status-alone / OCR-fee-alone / loose identity spiked CFA.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from .adjudication import AdjudicationOutcome, PolicyRuleSet
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
_LAYOUT_CONSENSUS_VISAS = frozenset({"DIP-1", "XW-1", "XW-2"})
_POLICY = PolicyRuleSet()


def _pdf_layout_text(pdf_path: Path) -> str:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout or ""


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


def apply_layout_consensus_approval(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Approve DIP/XW packets with visible ``$809`` + cross-form name consensus.

    Exact v30-safe gate (measured **131.01**, CFA=1). Do not loosen fee proof.
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
    if row.declared_purpose == "medical consult":
        return row
    # Field manual: DIP-1 does not require a sponsor (diplomatic exemption).
    # Revoked/missing sponsors remain blocking for XW visas.
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

    payload = row.to_dict()
    payload["adjudication"] = "APPROVED"
    payload["confidence"] = LAYOUT_CONSENSUS_APPROVAL_CONFIDENCE
    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


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

    text = _pdf_layout_text(pdf_path)
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

    payload = row.to_dict()
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
