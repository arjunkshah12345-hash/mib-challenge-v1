from datetime import date

from mib.evidence import Evidence, SourceRank, resolve_field
from mib.policy import (
    APPROVED,
    DENIED,
    NEEDS_REVIEW,
    PolicyInput,
    adjudicate,
    choose_for_score,
)


def clean_packet(**overrides: object) -> PolicyInput:
    values = {
        "visa_class": "XW-2",
        "sponsor_id": "SPN-1234",
        "arrival_date": date(2026, 4, 17),
        "receipt_date": date(2026, 4, 20),
        "fee_status": "paid",
    }
    values.update(overrides)
    return PolicyInput(**values)


def test_clean_packet_is_approved() -> None:
    assert adjudicate(clean_packet()).adjudication == APPROVED


def test_disqualifying_flag_overrides_review_flag() -> None:
    decision = adjudicate(
        clean_packet(risk_flags=frozenset({"identity_conflict", "active_warrant"}))
    )
    assert decision.adjudication == DENIED
    assert "disqualifying_flags:active_warrant" in decision.reasons


def test_unknown_fee_is_reviewed() -> None:
    assert adjudicate(clean_packet(fee_status="unknown")).adjudication == NEEDS_REVIEW


def test_embargoed_home_world_is_denied() -> None:
    assert adjudicate(clean_packet(home_world="TRAPPIST-1e")).adjudication == DENIED


def test_diplomat_does_not_require_a_valid_sponsor() -> None:
    packet = clean_packet(visa_class="DIP-1", sponsor_id="SPN-4040")
    assert adjudicate(packet).adjudication == APPROVED


def test_diplomat_is_exempt_from_stale_arrival() -> None:
    stale = {
        "visa_class": "DIP-1",
        "sponsor_id": None,
        "arrival_date": date(2025, 1, 1),
        "receipt_date": date(2026, 1, 1),
        "fee_status": "waived",
    }
    assert adjudicate(PolicyInput(**stale)).adjudication == APPROVED
    # Non-DIP still denied when stale.
    assert (
        adjudicate(PolicyInput(**{**stale, "visa_class": "XW-2", "sponsor_id": "SPN-1234", "fee_status": "paid"})).adjudication
        == DENIED
    )


def test_score_utility_is_conservative_near_denial_risk() -> None:
    assert choose_for_score({APPROVED: 0.45, DENIED: 0.35, NEEDS_REVIEW: 0.20}) != APPROVED


def test_visible_higher_rank_evidence_wins() -> None:
    evidence = [
        Evidence("fee_status", "unpaid", SourceRank.TEXT_LAYER, 0, False, 1.0),
        Evidence("fee_status", "paid", SourceRank.INTAKE_FORM, 0, True, 0.8),
        Evidence("fee_status", "waived", SourceRank.SPONSOR_ATTESTATION, 1, True, 0.9),
    ]
    resolved = resolve_field("fee_status", evidence, active_case_id=None)
    assert resolved.value == "paid"
    assert not resolved.conflict


def test_same_rank_disagreement_is_a_conflict() -> None:
    evidence = [
        Evidence("sponsor_id", "SPN-1111", SourceRank.INTAKE_FORM, 0, True, 0.8),
        Evidence("sponsor_id", "SPN-2222", SourceRank.INTAKE_FORM, 1, True, 0.9),
    ]
    assert resolve_field("sponsor_id", evidence, active_case_id=None).conflict
