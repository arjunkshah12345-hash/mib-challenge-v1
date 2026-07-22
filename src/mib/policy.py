from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


APPROVED = "APPROVED"
DENIED = "DENIED"
NEEDS_REVIEW = "NEEDS_REVIEW"

DISQUALIFYING_FLAGS = {
    "memory_tampering",
    "planetary_embargo",
    "active_warrant",
    "biohazard_red",
}
REVIEW_FLAGS = {
    "identity_conflict",
    "sponsor_mismatch",
    "illegible_biometrics",
    "rescinded_denial",
}
PUBLIC_REVOKED_SPONSORS = {
    "SPN-0007",
    "SPN-0139",
    "SPN-2718",
    "SPN-4040",
    "SPN-7331",
    "SPN-9090",
}
EMBARGOED_HOME_WORLDS = {"TRAPPIST-1e", "Eris Relay"}


@dataclass(frozen=True, slots=True)
class PolicyInput:
    visa_class: str | None
    sponsor_id: str | None
    arrival_date: date | None
    receipt_date: date | None
    fee_status: str | None
    home_world: str | None = None
    risk_flags: frozenset[str] = field(default_factory=frozenset)
    hardship_waiver: bool = False
    diplomatic_note: bool = False
    required_field_missing: bool = False
    unresolved_conflict: bool = False
    revoked_sponsors: frozenset[str] = field(
        default_factory=lambda: frozenset(PUBLIC_REVOKED_SPONSORS)
    )


@dataclass(frozen=True, slots=True)
class Decision:
    adjudication: str
    reasons: tuple[str, ...]
    approval_gate_passed: bool


def adjudicate(packet: PolicyInput) -> Decision:
    denial_reasons = []
    review_reasons = []

    disqualifying = sorted(packet.risk_flags & DISQUALIFYING_FLAGS)
    if disqualifying:
        denial_reasons.append(f"disqualifying_flags:{'|'.join(disqualifying)}")

    if packet.visa_class == "TRANSIT-7":
        denial_reasons.append("transit_class")
    if packet.visa_class != "DIP-1" and packet.sponsor_id in packet.revoked_sponsors:
        denial_reasons.append("revoked_sponsor")
    if packet.home_world in EMBARGOED_HOME_WORLDS:
        denial_reasons.append("embargoed_home_world")
    if packet.fee_status == "unpaid" and not packet.hardship_waiver:
        denial_reasons.append("unpaid_fee")

    if packet.required_field_missing:
        review_reasons.append("required_field_missing")
    if packet.unresolved_conflict:
        review_reasons.append("unresolved_conflict")
    if packet.risk_flags & REVIEW_FLAGS:
        review_reasons.append("review_only_risk_flag")
    if packet.fee_status in {None, "unknown"}:
        review_reasons.append("fee_unknown")
    if packet.arrival_date is None:
        review_reasons.append("arrival_date_missing")
    if packet.visa_class != "DIP-1" and not packet.sponsor_id:
        review_reasons.append("sponsor_missing")
    if packet.fee_status == "waived" and packet.visa_class != "DIP-1" and not packet.hardship_waiver:
        review_reasons.append("unsupported_fee_waiver")

    if packet.arrival_date is not None and packet.receipt_date is not None:
        age_days = (packet.receipt_date - packet.arrival_date).days
        # DIP-1 is exempt from the 180-day stale-arrival denial (diplomatic channel).
        if age_days > 180 and packet.visa_class != "DIP-1":
            denial_reasons.append("stale_arrival")

    approval_gate_passed = not denial_reasons and not review_reasons
    if denial_reasons:
        return Decision(DENIED, tuple(denial_reasons), False)
    if review_reasons:
        return Decision(NEEDS_REVIEW, tuple(review_reasons), False)
    return Decision(APPROVED, ("all_known_checks_passed",), approval_gate_passed)


def choose_for_score(probabilities: dict[str, float]) -> str:
    approved = probabilities.get(APPROVED, 0.0)
    denied = probabilities.get(DENIED, 0.0)
    review = probabilities.get(NEEDS_REVIEW, 0.0)
    utilities = {
        APPROVED: 8 * approved - 4 * denied + review,
        DENIED: 8 * denied + review,
        NEEDS_REVIEW: 8 * review + 2 * (approved + denied),
    }
    return max(utilities, key=utilities.get)
