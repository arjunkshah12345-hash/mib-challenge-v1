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

from .adjudication import AdjudicationOutcome
from .extraction import CandidateEvidence, EvidenceType
from .models import PredictionRow

# Confidence used when an owned head promotes a clean packet to APPROVED.
CLEAN_PACKET_APPROVAL_CONFIDENCE = 0.61


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
