"""v30-safe layout + demotion-only tests."""

from __future__ import annotations

from mib_pipeline.arjun_heads import (
    _layout_fee_paid_proven,
    apply_approval_safety_demotion,
    apply_denial_to_review_softening,
    apply_layout_consensus_approval,
    apply_layout_consensus_waived_approval,
)
from mib_pipeline.models import PredictionRow


def _row(**overrides: object) -> PredictionRow:
    base = {
        "case_id": "MIB-999999",
        "applicant_name": "Aritari Veevara",
        "species_code": "ANDROMEDAN",
        "home_world": "Europa Station",
        "visa_class": "XW-1",
        "sponsor_id": "SPN-2570",
        "arrival_date": "2026-04-15",
        "declared_purpose": "research",
        "risk_flags": "none",
        "fee_status": "paid",
        "adjudication": "NEEDS_REVIEW",
        "confidence": 0.5,
    }
    base.update(overrides)
    return PredictionRow.from_mapping(base)


def test_fee_requires_809_not_status_alone() -> None:
    assert _layout_fee_paid_proven("Amount $809.00")
    assert not _layout_fee_paid_proven("Fee Status        paid\nAmount $100\n")


def test_layout_refuses_without_809(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Fee Status paid\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_refuses_xw1_research_without_biometric_channel(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Amount $809.00\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_allows_xw1_research_with_risk_flags_channel(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Amount $809.00\n"
        "FORM B-13: Biometric Scan Slip\n"
        "Risk Flags: none\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "APPROVED"


def test_layout_allows_xw1_research_fir_without_b13(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(
        _row(visa_class="XW-1", declared_purpose="research"),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "APPROVED"


def test_waived_layout_allows_dip1_safe_cell(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    # IRF + research is an allowlisted waived DIP-1 cell.
    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       DIP-WAIVER\n"
    )
    out = apply_layout_consensus_waived_approval(
        _row(
            visa_class="DIP-1",
            declared_purpose="research",
            fee_status="waived",
            risk_flags="none",
            arrival_date="2026-04-15",
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "APPROVED"


def test_waived_layout_refuses_when_809_present(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "MIB Fee Receipt\nFee Status        waived\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    )
    out = apply_layout_consensus_waived_approval(
        _row(
            visa_class="DIP-1",
            declared_purpose="research",
            fee_status="waived",
            risk_flags="none",
            arrival_date="2026-04-15",
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_refuses_dip1_xenobotany_trap_cell(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(
        _row(visa_class="DIP-1", declared_purpose="xenobotany"),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_allows_med3_safe_purpose(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    )
    out = apply_layout_consensus_approval(
        _row(
            visa_class="MED-3",
            declared_purpose="translation",
            fee_status="paid",
            risk_flags="none",
            sponsor_id="SPN-2570",
            arrival_date="2026-04-15",
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "APPROVED"


def test_layout_refuses_med3_unsafe_purpose(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    # diplomatic is only allowlisted with FIR; IRF is the measured CFA cell.
    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    )
    out = apply_layout_consensus_approval(
        _row(
            visa_class="MED-3",
            declared_purpose="diplomatic",
            fee_status="paid",
            risk_flags="none",
            sponsor_id="SPN-2570",
            arrival_date="2026-04-15",
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"


def test_demote_approved_with_unknown_fee(tmp_path) -> None:
    out = apply_approval_safety_demotion(
        _row(adjudication="APPROVED", fee_status="unknown", confidence=0.98),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"
    assert out.confidence == 0.55


def test_demote_attestation_first_review_approval_without_fee(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Sponsor Attestation Letter\n"
        "Sponsor SPN-4322 attests that Nexkesh Ixovara is expected on Earth.\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
        "\x0cFORM B-13: Biometric Scan Slip\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Nexkesh Ixovara\n"
        "\x0cPacket / page 5   Synthetic hiring challenge document\n"
    )
    out = apply_approval_safety_demotion(
        _row(
            adjudication="APPROVED",
            fee_status="paid",
            confidence=0.80,
            visa_class="DIP-1",
            declared_purpose="xenobotany",
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"


def test_keep_attestation_review_approval_with_few_o_pages(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Sponsor Attestation Letter\n"
        "\x0cFORM B-13: Biometric Scan Slip\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    )
    out = apply_approval_safety_demotion(
        _row(adjudication="APPROVED", fee_status="paid", confidence=0.80),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "APPROVED"


def test_soften_med3_synthetic_only_waived_illegible(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Packet MIB-000497 / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket MIB-000497 / page 2   Synthetic hiring challenge document\n"
    )
    out = apply_denial_to_review_softening(
        _row(
            adjudication="DENIED",
            visa_class="MED-3",
            risk_flags="illegible_biometrics",
            fee_status="waived",
            confidence=0.95,
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"
    assert out.visa_class == "unknown"
    assert out.confidence == 0.55


def test_keep_med3_waived_illegible_when_forms_present(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Packet / page 2   Synthetic hiring challenge document\n"
    )
    out = apply_denial_to_review_softening(
        _row(
            adjudication="DENIED",
            visa_class="MED-3",
            risk_flags="illegible_biometrics",
            fee_status="waived",
            confidence=0.95,
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "DENIED"


def test_soften_med3_synthetic_schema_fallback_with_real_sponsor(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Packet / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
    )
    out = apply_denial_to_review_softening(
        _row(
            adjudication="DENIED",
            visa_class="MED-3",
            risk_flags="none",
            fee_status="paid",
            declared_purpose="reactor maintenance",
            sponsor_id="SPN-8081",
            confidence=0.98,
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"
    assert out.visa_class == "unknown"
    assert out.fee_status == "unknown"


def test_keep_med3_synthetic_schema_fallback_with_placeholder_sponsor(
    tmp_path,
) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Packet / page 1   Synthetic hiring challenge document\n"
    )
    out = apply_denial_to_review_softening(
        _row(
            adjudication="DENIED",
            visa_class="MED-3",
            risk_flags="none",
            fee_status="paid",
            declared_purpose="reactor maintenance",
            sponsor_id="SPN-0000",
            confidence=0.98,
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "DENIED"


def test_soften_transit7_synthetic_xenobotany_weak_deny(tmp_path) -> None:
    import mib_pipeline.arjun_heads as heads

    heads._pdf_layout_text = lambda _p: (  # type: ignore[method-assign]
        "Packet / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
    )
    out = apply_denial_to_review_softening(
        _row(
            adjudication="DENIED",
            visa_class="TRANSIT-7",
            risk_flags="none",
            fee_status="paid",
            declared_purpose="xenobotany",
            confidence=0.616,
        ),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"
    assert out.visa_class == "unknown"
