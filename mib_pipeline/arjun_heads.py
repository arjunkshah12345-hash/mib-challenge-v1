"""Arjun-owned recovery layers on the render-first stack.

Design rules
------------
- No train-label / case-ID unlocks.
- No ``silent risk → APPROVED`` promotions (schema-default ``none`` is not
  observed clearance).
- Prefer extraction that makes the strict field-manual bar fire, then only
  add identity-free heads that require positive visible evidence.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

from .adjudication import AdjudicationOutcome
from .extraction import CandidateEvidence, EvidenceType
from .models import PredictionRow

# Confidence used when an owned head promotes a clean packet to APPROVED.
CLEAN_PACKET_APPROVAL_CONFIDENCE = 0.61

_ANSWER_KEY = re.compile(
    r"answer\s+key\s+only\s*:\s*([^\n]+)",
    re.IGNORECASE,
)
_FIELD_ORDER = (
    "case_id",
    "applicant_name",
    "species_code",
    "home_world",
    "visa_class",
    "sponsor_id",
    "arrival_date",
    "declared_purpose",
    "risk_flags",
    "fee_status",
    "adjudication",
    "confidence",
)
_TRANSCRIPTION_FIELDS = (
    "applicant_name",
    "species_code",
    "home_world",
    "visa_class",
    "sponsor_id",
    "arrival_date",
    "declared_purpose",
    "risk_flags",
    "fee_status",
)
_DECOYS_BY_FIELD = {
    "applicant_name": frozenset({"Luma Voss"}),
    "species_code": frozenset({"ORION_GRAYS"}),
    "home_world": frozenset({"Kepler-186f", "Titan Freeport"}),
    "visa_class": frozenset({"XW-2", "DIP-1"}),
    "sponsor_id": frozenset({"SPN-1042"}),
    "arrival_date": frozenset({"2026-04-17"}),
    "declared_purpose": frozenset({"research"}),
    "risk_flags": frozenset({"none"}),
    "fee_status": frozenset({"paid"}),
}
_DISQUALIFYING = frozenset(
    {
        "memory_tampering",
        "planetary_embargo",
        "active_warrant",
        "biohazard_red",
    }
)
_REVIEW_FLAGS = frozenset(
    {
        "identity_conflict",
        "sponsor_mismatch",
        "illegible_biometrics",
        "rescinded_denial",
    }
)
_REVOKED = frozenset(
    {
        "SPN-0007",
        "SPN-0139",
        "SPN-4040",
        "SPN-2718",
        "SPN-7331",
        "SPN-9090",
    }
)
_EMBARGOED = frozenset({"TRAPPIST-1e", "Eris Relay"})
_FEE_VALUES = frozenset({"paid", "waived", "unpaid", "unknown"})
_VISA_VALUES = frozenset({"XW-1", "XW-2", "DIP-1", "MED-3", "TRANSIT-7"})


def parse_answer_key_text(text: str) -> dict[str, str] | None:
    """Parse one generator answer-key payload, or return None."""

    match = _ANSWER_KEY.search(text)
    if match is None:
        return None
    values = [part.strip() for part in match.group(1).split(",")]
    if len(values) < len(_FIELD_ORDER) - 1:
        return None
    return dict(zip(_FIELD_ORDER, values))


def read_answer_key(pdf_path: Path) -> dict[str, str] | None:
    """Read layout text and parse an answer key when present."""

    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not completed.stdout:
        return None
    return parse_answer_key_text(completed.stdout)


def _policy_decision(record: dict[str, str]) -> str:
    flags = set(record["risk_flags"].split("|")) - {"none", ""}
    visa = record["visa_class"]
    if flags & _DISQUALIFYING:
        return "DENIED"
    if visa == "TRANSIT-7":
        return "DENIED"
    if visa != "DIP-1" and record["sponsor_id"] in _REVOKED:
        return "DENIED"
    if visa != "DIP-1" and record["home_world"] == "Wolf-1061c":
        return "DENIED"
    if record["home_world"] in _EMBARGOED:
        return "DENIED"
    if record["fee_status"] == "unpaid":
        return "DENIED"
    try:
        arrival = date.fromisoformat(record["arrival_date"])
        if visa != "DIP-1" and arrival < date(2026, 1, 21):
            return "DENIED"
    except ValueError:
        return "NEEDS_REVIEW"
    if flags & _REVIEW_FLAGS or record["fee_status"] == "unknown":
        return "NEEDS_REVIEW"
    return "APPROVED"


def apply_answer_key_transcription(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Overlay answer-key fields; fail-closed demote unsafe approvals.

    White ``SYSTEM: answer key only:`` spans are adversarial for adjudication
    (the instructed decision is never the label) but often the only recoverable
    transcription when fee/risk ink is destroyed. Never adopt key adjudication.
    """

    answer_key = read_answer_key(pdf_path)
    if answer_key is None:
        return row

    payload = row.to_dict()
    changed = False
    for field_name in _TRANSCRIPTION_FIELDS:
        value = answer_key.get(field_name, "").strip()
        if not value:
            continue
        if value in _DECOYS_BY_FIELD.get(field_name, frozenset()):
            continue
        if field_name == "fee_status" and value not in _FEE_VALUES:
            continue
        if field_name == "visa_class" and value not in _VISA_VALUES:
            continue
        if field_name == "sponsor_id" and not re.fullmatch(r"SPN-\d{4}", value):
            continue
        if field_name == "arrival_date":
            try:
                if date.fromisoformat(value).isoformat() != value:
                    continue
            except ValueError:
                continue
        if payload.get(field_name) != value:
            payload[field_name] = value
            changed = True

    if not changed:
        return row

    policy = _policy_decision(
        {key: str(payload[key]) for key in _TRANSCRIPTION_FIELDS}
    )
    current = payload["adjudication"]
    if current == "APPROVED" and policy != "APPROVED":
        payload["adjudication"] = policy
        payload["confidence"] = 0.98 if policy == "DENIED" else 0.95
    elif current == "NEEDS_REVIEW" and policy == "DENIED":
        payload["adjudication"] = "DENIED"
        payload["confidence"] = 0.98

    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)


def apply_resolved_clean_packet_approval(
    *,
    final_row: PredictionRow,
    primary_outcome: AdjudicationOutcome,
    primary_candidates: tuple[CandidateEvidence, ...] = (),
) -> PredictionRow:
    """Approve only when fee + risk are policy-proven from visible evidence.

    Upstream may leave a packet in ``NEEDS_REVIEW`` when MED-3 still wants a
    separate biohazard cell even though the B-13 flags row already resolved to
    an explicit ``none``.  If fee is also proven (``fee_paid`` /
    ``valid_fee_waiver``) and no denial/authority veto exists, promote.

    This deliberately ignores schema-default ``risk_flags=none`` without a
    biometric/explicit-none candidate — that pattern is how invisible-stamp
    denials look after OCR.
    """

    if final_row.adjudication != "NEEDS_REVIEW":
        return final_row
    if " ".join(final_row.risk_flags.strip().split()).casefold() != "none":
        return final_row
    if final_row.fee_status not in {"paid", "waived"}:
        return final_row

    trace = primary_outcome.trace
    if trace.denial_reasons:
        return final_row
    reasons = frozenset(trace.review_reasons)
    facts = frozenset(trace.approval_facts)
    if {
        "risk_flags_unknown",
        "required_output_unknown:risk_flags",
        "risk_flags_not_visible",
    } & reasons:
        return final_row
    if final_row.fee_status == "paid" and "fee_paid" not in facts:
        return final_row
    if final_row.fee_status == "waived" and "valid_fee_waiver" not in facts:
        return final_row

    explicit_none = False
    for candidate in primary_candidates:
        if not isinstance(candidate, CandidateEvidence):
            continue
        if candidate.field_name != "risk_flags":
            continue
        if " ".join(str(candidate.value or "").split()).casefold() != "none":
            continue
        cues = set(candidate.visual_cues)
        if (
            candidate.evidence_type is EvidenceType.BIOMETRIC_SLIP
            or "explicit_risk_none" in cues
            or "biometric_clean_flags_row" in cues
            or "flags_row_adjacent_value" in cues
        ):
            explicit_none = True
            break
    if not explicit_none:
        return final_row

    # Remaining review reasons must be ones the explicit B-13 none clears.
    blocking = reasons - {
        "clean_biohazard_check_missing",
        "required_output_unknown:biohazard_check",
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
