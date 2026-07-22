from mib.evidence import Evidence, SourceRank, resolve_field


def test_invalid_high_rank_ocr_does_not_mask_valid_lower_source() -> None:
    evidence = [
        Evidence(
            "arrival_date",
            "2028-03-16",
            SourceRank.INTAKE_FORM,
            0,
            True,
            0.9,
            "MIB-000001",
        ),
        Evidence(
            "arrival_date",
            "2026-03-16",
            SourceRank.REGISTRY,
            1,
            True,
            0.99,
            "MIB-000001",
        ),
    ]
    resolution = resolve_field("arrival_date", evidence, active_case_id="MIB-000001")
    assert resolution.value == "2026-03-16"
