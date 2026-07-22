"""Arjun-owned guards layered on the referenced render-first stack.

Overfit note
------------
An earlier review→approve head used a train-slice correlation
(\"silent-risk packets often lack a sponsor attestation page\") to promote
``risk_flags_unknown`` cases to ``APPROVED``. That is label-leakage / train
overfit and conflicts with organizer guidance that unobserved disqualifying
risk must stay ``NEEDS_REVIEW``. That head was removed.

What remains here is only a **fail-closed** gate on the upstream statistical
approval head: never approve when fee is still unresolved in policy. That is
anti-false-approval conservatism, not a train-tuned unlock.
"""

from __future__ import annotations

from .adjudication import AdjudicationOutcome
from .models import PredictionRow


def tighten_statistical_approval_gate(
    *,
    final_row: PredictionRow,
    primary_outcome: AdjudicationOutcome,
) -> bool:
    """Return False when the statistical head must abstain (FA guard).

    Identity-free: uses only serialized fee status and policy review/approval
    facts. Requires a fee approval fact so schema-default ``paid`` alone cannot
    unlock an approval.
    """

    if final_row.fee_status not in {"paid", "waived"}:
        return False
    reasons = frozenset(primary_outcome.trace.review_reasons)
    facts = frozenset(primary_outcome.trace.approval_facts)
    if {
        "fee_status_unknown",
        "required_output_unknown:fee_status",
    } & reasons:
        return False
    if final_row.fee_status == "paid" and "fee_paid" not in facts:
        return False
    if final_row.fee_status == "waived" and "valid_fee_waiver" not in facts:
        return False
    return True
