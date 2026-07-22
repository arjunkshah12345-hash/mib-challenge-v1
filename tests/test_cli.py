import json
from pathlib import Path

import pytest

from mib.cli import baseline_prediction, process_directory


EXPECTED_KEYS = {
    "case_id",
    "applicant_name",
    "species_code",
    "home_world",
    "visa_class",
    "sponsor_id",
    "arrival_date",
    "declared_purpose",
    "risk_flags",
    "fee_status",
    "adjudication",
    "confidence",
}


def test_baseline_prediction_is_schema_shaped(tmp_path: Path) -> None:
    prediction = baseline_prediction(tmp_path / "MIB-123456.pdf")
    assert set(prediction) == EXPECTED_KEYS
    assert prediction["case_id"] == "MIB-123456"
    assert prediction["adjudication"] == "NEEDS_REVIEW"
    assert 0 <= prediction["confidence"] <= 1


def test_invalid_filename_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        baseline_prediction(tmp_path / "packet.pdf")


def test_directory_processing_is_sorted_and_atomic(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "MIB-000002.pdf").touch()
    (input_dir / "MIB-000001.pdf").touch()
    (input_dir / "notes.txt").touch()
    output = tmp_path / "output" / "predictions.jsonl"

    assert process_directory(input_dir, output) == 2
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [row["case_id"] for row in rows] == ["MIB-000001", "MIB-000002"]
    assert not list(output.parent.glob("*.tmp"))
