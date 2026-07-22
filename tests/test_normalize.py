from mib.normalize import canonicalize


def test_damage_markers_are_missing() -> None:
    assert canonicalize("species_code", "[SPECIES WHITEOUT]") is None
    assert canonicalize("sponsor_id", "[SPONSOR ID BLANK]") is None


def test_constrained_fields_are_canonicalized() -> None:
    assert canonicalize("species_code", "VENUSIAN MYCELIAL") == "VENUSIAN_MYCELIAL"
    assert canonicalize("visa_class", "XW 1") == "XW-1"
    assert canonicalize("home_world", "Barnard-c") == "Barnard-c"


def test_flags_are_sorted_and_pipe_delimited() -> None:
    assert (
        canonicalize("risk_flags", "planetary_embargo, illegible_biometrics")
        == "illegible_biometrics|planetary_embargo"
    )


def test_ocr_garbled_biohazard_is_recovered() -> None:
    assert canonicalize("risk_flags", "troharard red") == "biohazard_red"
    assert canonicalize("risk_flags", "troharard") == "biohazard_red"


def test_synthetic_name_tokens_correct_small_ocr_errors() -> None:
    assert canonicalize("applicant_name", "Tekquell Veezarm") == "Tekquell Veezarn"
    assert canonicalize("applicant_name", "Tekdane Ixokx") == "Tekdane Ixoix"
