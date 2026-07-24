"""Transfer-safe layout + demotion tests (no leaked monkeypatches)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from mib_pipeline.arjun_heads import (
    _layout_fee_paid_proven,
    apply_approval_safety_demotion,
    apply_decision_confidence_floors,
    apply_denial_to_review_softening,
    apply_layout_consensus_approval,
    apply_layout_consensus_waived_approval,
    apply_layout_trap_denial,
)
from mib_pipeline.models import PredictionRow


@contextmanager
def _fake_layout(text: str) -> Iterator[None]:
    """Patch layout text and always restore (avoids leaking into later runs)."""

    import mib_pipeline.arjun_heads as heads

    original = heads._pdf_layout_text
    heads._pdf_layout_text = lambda _p: text  # type: ignore[method-assign]
    try:
        yield
    finally:
        heads._pdf_layout_text = original


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
    with _fake_layout(
        "Fee Status paid\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_refuses_xw1_research_without_biometric_channel(tmp_path) -> None:
    with _fake_layout(
        "Amount $809.00\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_allows_xw1_research_with_risk_flags_channel(tmp_path) -> None:
    with _fake_layout(
        "Amount $809.00\n"
        "FORM B-13: Biometric Scan Slip\n"
        "Risk Flags: none\n"
        "Registry Name        Aritari Veevara\n"
        "Applicant               Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(_row(), tmp_path / "x.pdf")
    assert out.adjudication == "APPROVED"


def test_layout_refuses_xw1_research_fir_without_b13(tmp_path) -> None:
    with _fake_layout(
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(
            _row(visa_class="XW-1", declared_purpose="research"),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_waived_layout_allows_dip1_research_family(tmp_path) -> None:
    # IRF assembly + research is in the DIP-1 waived purpose family (n>=2).
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       DIP-WAIVER\n"
    ):
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


def test_waived_layout_allows_xw2_translation_family(tmp_path) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       XW-WAIVER\n"
    ):
        out = apply_layout_consensus_waived_approval(
            _row(
                visa_class="XW-2",
                declared_purpose="translation",
                fee_status="waived",
                risk_flags="none",
                arrival_date="2026-04-15",
                sponsor_id="SPN-1234",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_waived_layout_refuses_med3_even_safe_purpose(tmp_path) -> None:
    """MED-3 waived stays closed (warrant/biohazard collisions on train)."""
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       MED-WAIVER\n"
    ):
        out = apply_layout_consensus_waived_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="translation",
                fee_status="waived",
                risk_flags="none",
                arrival_date="2026-04-15",
                sponsor_id="SPN-1234",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_waived_layout_refuses_dip1_fir_assembly(tmp_path) -> None:
    # FIR is a fee-first trap even for an otherwise-safe purpose family.
    with _fake_layout(
        "MIB Fee Receipt\nFee Status        waived\nWaiver Code       DIP-WAIVER\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
        out = apply_layout_consensus_waived_approval(
            _row(
                visa_class="DIP-1",
                declared_purpose="cultural exchange",
                fee_status="waived",
                risk_flags="none",
                arrival_date="2026-04-15",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_waived_layout_refuses_when_809_present(tmp_path) -> None:
    with _fake_layout(
        "MIB Fee Receipt\nFee Status        waived\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
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
    with _fake_layout(
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(
            _row(visa_class="DIP-1", declared_purpose="xenobotany"),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_layout_allows_med3_safe_purpose(tmp_path) -> None:
    with _fake_layout(
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
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


def test_layout_allows_med3_industrial_with_registry_before_close(tmp_path) -> None:
    # IRF: Registry before Fee close — industrial MED-3 OK.
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="field repair",
                fee_status="paid",
                risk_flags="none",
                sponsor_id="SPN-2570",
                arrival_date="2026-04-15",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_layout_refuses_med3_industrial_when_registry_last(tmp_path) -> None:
    # IFR: Registry last — invisible biohazard cluster for industrial purposes.
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="reactor maintenance",
                fee_status="paid",
                risk_flags="none",
                sponsor_id="SPN-2570",
                arrival_date="2026-04-15",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_waived_layout_allows_med3_industrial(tmp_path) -> None:
    # RFI: Registry not last — MED-3 waived industrial OK.
    with _fake_layout(
        "Planetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       MED-WAIVER\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
    ):
        out = apply_layout_consensus_waived_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="reactor maintenance",
                fee_status="waived",
                risk_flags="none",
                arrival_date="2026-04-15",
                sponsor_id="SPN-1234",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_demote_approved_with_unknown_fee(tmp_path) -> None:
    out = apply_approval_safety_demotion(
        _row(adjudication="APPROVED", fee_status="unknown", confidence=0.98),
        tmp_path / "x.pdf",
    )
    assert out.adjudication == "NEEDS_REVIEW"
    assert out.confidence == 0.55


def test_demote_attestation_first_review_approval_without_fee(tmp_path) -> None:
    with _fake_layout(
        "Sponsor Attestation Letter\n"
        "Sponsor SPN-4322 attests that Nexkesh Ixovara is expected on Earth.\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
        "\x0cFORM B-13: Biometric Scan Slip\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Nexkesh Ixovara\n"
        "\x0cPacket / page 5   Synthetic hiring challenge document\n"
    ):
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
    with _fake_layout(
        "Sponsor Attestation Letter\n"
        "\x0cFORM B-13: Biometric Scan Slip\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
        out = apply_approval_safety_demotion(
            _row(adjudication="APPROVED", fee_status="paid", confidence=0.80),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_keep_med3_synthetic_waived_illegible_denied(tmp_path) -> None:
    """Singleton waived+illegible soften removed for transfer safety."""
    with _fake_layout(
        "Packet MIB-000497 / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket MIB-000497 / page 2   Synthetic hiring challenge document\n"
    ):
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


def test_keep_med3_waived_illegible_when_forms_present(tmp_path) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Packet / page 2   Synthetic hiring challenge document\n"
    ):
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
    with _fake_layout(
        "Packet / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
    ):
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
    with _fake_layout(
        "Packet / page 1   Synthetic hiring challenge document\n"
    ):
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


def test_keep_transit7_synthetic_xenobotany_denied(tmp_path) -> None:
    """Synthetic TRANSIT-7 xenobotany stays DENIED (n=1 soften removed)."""
    with _fake_layout(
        "Packet / page 1   Synthetic hiring challenge document\n"
        "\x0cPacket / page 2   Synthetic hiring challenge document\n"
    ):
        out = apply_denial_to_review_softening(
            _row(
                adjudication="DENIED",
                visa_class="TRANSIT-7",
                risk_flags="none",
                fee_status="paid",
                declared_purpose="xenobotany",
                arrival_date="1900-01-01",
                confidence=0.616,
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "DENIED"


def test_keep_schema_waived_illegible_denied(tmp_path) -> None:
    """n=1 schema-placeholder waived+illegible soften removed."""
    with _fake_layout(
        "Packet / page 1   Synthetic hiring challenge document\n"
    ):
        out = apply_denial_to_review_softening(
            _row(
                adjudication="DENIED",
                visa_class="MED-3",
                risk_flags="illegible_biometrics",
                fee_status="waived",
                declared_purpose="diplomatic",
                sponsor_id="SPN-0000",
                arrival_date="1900-01-01",
                confidence=0.98,
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "DENIED"


def test_layout_approves_med3_medical_consult_when_registry_before_close(
    tmp_path,
) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="medical consult",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_layout_refuses_xw1_medical_consult(tmp_path) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="XW-1",
                declared_purpose="medical consult",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_trap_denies_med3_industrial_registry_last(tmp_path) -> None:
    with _fake_layout(
        "MIB Fee Receipt\nAmount $809.00\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
    ):
        out = apply_layout_trap_denial(
            _row(
                visa_class="MED-3",
                declared_purpose="reactor maintenance",
                confidence=0.07,
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "DENIED"


def test_trap_denies_med3_diplomatic_registry_before_close(tmp_path) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    ):
        out = apply_layout_trap_denial(
            _row(
                visa_class="MED-3",
                declared_purpose="diplomatic",
                confidence=0.07,
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "DENIED"


def test_decision_confidence_floors_approved_and_denied() -> None:
    approved = apply_decision_confidence_floors(
        _row(adjudication="APPROVED", confidence=0.85)
    )
    denied = apply_decision_confidence_floors(
        _row(adjudication="DENIED", confidence=0.55)
    )
    assert approved.confidence == 0.95
    assert denied.confidence == 0.95


def test_layout_allows_paid_trailing_single_o(tmp_path) -> None:
    with _fake_layout(
        "FORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
        "\x0cPacket filler page   Synthetic hiring challenge document\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="medical consult",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"


def test_layout_refuses_paid_leading_o(tmp_path) -> None:
    with _fake_layout(
        "Packet filler page   Synthetic hiring challenge document\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPlanetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nAmount $809.00\n"
    ):
        out = apply_layout_consensus_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="medical consult",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "NEEDS_REVIEW"


def test_waived_layout_allows_trailing_single_o(tmp_path) -> None:
    with _fake_layout(
        "Planetary Registry Extract\nRegistry Name        Aritari Veevara\n"
        "\x0cMIB Fee Receipt\nFee Status        waived\nWaiver Code       MED-WAIVER\n"
        "\x0cFORM I-8090: Extraterrestrial Work Authorization Intake\n"
        "Applicant               Aritari Veevara\n"
        "\x0cPacket filler page   Synthetic hiring challenge document\n"
    ):
        out = apply_layout_consensus_waived_approval(
            _row(
                visa_class="MED-3",
                declared_purpose="field repair",
                fee_status="waived",
                risk_flags="none",
                arrival_date="2026-04-15",
                sponsor_id="SPN-1234",
            ),
            tmp_path / "x.pdf",
        )
    assert out.adjudication == "APPROVED"

