"""v30-safe layout + demotion-only tests."""

from __future__ import annotations

from mib_pipeline.arjun_heads import _layout_fee_paid_proven, apply_layout_consensus_approval
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
