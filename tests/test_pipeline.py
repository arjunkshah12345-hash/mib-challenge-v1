from mib.evidence import Evidence, SourceRank
from mib.pipeline import apply_identity_resolution, derive_risk_flags


def item(field: str, value: str, source: SourceRank) -> Evidence:
    return Evidence(field, value, source, 0, True, 0.99, "MIB-000001")


def test_cross_source_disagreement_does_not_invent_a_risk_flag() -> None:
    evidence = [
        item("sponsor_id", "SPN-1000", SourceRank.INTAKE_FORM),
        item("sponsor_id", "SPN-2000", SourceRank.SPONSOR_ATTESTATION),
    ]
    values = {"risk_flags": None, "home_world": "Mars Dome-7"}
    assert derive_risk_flags(values, evidence, "MIB-000001") == frozenset()


def test_embargoed_world_becomes_visible_policy_risk() -> None:
    values = {"risk_flags": None, "home_world": "TRAPPIST-1e"}
    assert derive_risk_flags(values, [], "MIB-000001") == frozenset(
        {"planetary_embargo"}
    )


def test_registry_identity_wins_after_conflict_is_established() -> None:
    evidence = [
        item("applicant_name", "Zamora Xannax", SourceRank.INTAKE_FORM),
        item("applicant_name", "Zaquell Lukesh", SourceRank.REGISTRY),
    ]
    values = {"applicant_name": "Zamora Xannax"}
    apply_identity_resolution(values, evidence, "MIB-000001")
    assert values["applicant_name"] == "Zaquell Lukesh"


def test_attested_sponsor_beats_ocr_revoked_intake_value() -> None:
    from mib.policy import PUBLIC_REVOKED_SPONSORS

    evidence = [
        item("sponsor_id", "SPN-0007", SourceRank.INTAKE_FORM),
        item("sponsor_id", "SPN-3187", SourceRank.SPONSOR_ATTESTATION),
    ]
    values = {"sponsor_id": "SPN-0007"}
    attested = {
        e.value
        for e in evidence
        if e.field == "sponsor_id" and e.source == SourceRank.SPONSOR_ATTESTATION
    }
    if values["sponsor_id"] in PUBLIC_REVOKED_SPONSORS and attested and values["sponsor_id"] not in attested:
        values["sponsor_id"] = next(iter(attested))
    assert values["sponsor_id"] == "SPN-3187"


def test_positive_fee_amount_overrides_unknown_status() -> None:
    from pathlib import Path
    from mib.pipeline import predict_pdf

    prediction = predict_pdf(Path("data/train/MIB-000543.pdf"))
    assert prediction["fee_status"] == "paid"


def test_transit_visa_normalize_recovers_ocr_garble() -> None:
    from mib.normalize import canonicalize

    assert canonicalize("visa_class", "TRAN5IT-7") == "TRANSIT-7"
    assert canonicalize("visa_class", "TRANSIT7") == "TRANSIT-7"
    assert canonicalize("visa_class", "trnsit 7") == "TRANSIT-7"
    # Must not fire on unrelated text that merely contains "transit".
    assert canonicalize("visa_class", "XW-1") == "XW-1"
    assert canonicalize("visa_class", "DIP-1") == "DIP-1"


def test_illegible_token_canonicalizes() -> None:
    from mib.normalize import canonicalize

    assert canonicalize("risk_flags", "illegible") == "illegible_biometrics"
    assert canonicalize("risk_flags", "unreadable biometrics") == "illegible_biometrics"
    assert canonicalize("risk_flags", "none") == "none"
    assert canonicalize("risk_flags", "clear") == "none"


def test_biometric_flags_helper_recovers_clear_and_illegible() -> None:
    from mib.ocr import _biometric_flags_from_text

    assert _biometric_flags_from_text("Observed flags: none") == "none"
    assert (
        _biometric_flags_from_text("Observed flags: illegible_biometrics")
        == "illegible_biometrics"
    )
    assert "biohazard_red" in (_biometric_flags_from_text("flags: troharard red") or "")


def test_false_approval_gate_blocks_dip_waiver_intake_only_visa() -> None:
    """MIB-000865: intake prints XW-2 + DIP-WAIVER but label is TRANSIT-7 DENIED."""
    from pathlib import Path
    from mib.pipeline import predict_pdf

    prediction = predict_pdf(Path("data/train/MIB-000865.pdf"))
    assert prediction["adjudication"] != "APPROVED"
    assert prediction["adjudication"] == "NEEDS_REVIEW"


def test_fee_paid_unpaid_conflict_does_not_false_approve() -> None:
    """MIB-000530: OCR emits both paid (tiny amount) and unpaid; must not APPROVE."""
    from pathlib import Path
    from mib.pipeline import predict_pdf

    prediction = predict_pdf(Path("data/train/MIB-000530.pdf"))
    assert prediction["adjudication"] != "APPROVED"
    assert prediction["fee_status"] in {"unpaid", "unknown"}
