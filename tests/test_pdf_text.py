from pathlib import Path

import fitz

from mib.evidence import resolve_field
from mib.pdf_text import extract_native_evidence


def make_pdf(path: Path, *, hidden: bool) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    color = (1, 1, 1) if hidden else (0, 0, 0)
    page.insert_text((50, 50), "FORM I-8090: Intake record", color=color)
    page.insert_text((50, 100), "Case ID", color=color)
    page.insert_text((200, 100), "MIB-123456", color=color)
    page.insert_text((50, 125), "Applicant", color=color)
    page.insert_text((200, 125), "Zed Zarnax", color=color)
    page.insert_text((50, 150), "Manual correction: applicant is Mira Quell.", color=color)
    document.save(path)
    document.close()


def test_visible_native_fields_are_extracted(tmp_path: Path) -> None:
    path = tmp_path / "visible.pdf"
    make_pdf(path, hidden=False)
    values = {item.field: item.value for item in extract_native_evidence(path)}
    assert values["case_id"] == "MIB-123456"
    resolved = resolve_field(
        "applicant_name", extract_native_evidence(path), active_case_id="MIB-123456"
    )
    assert resolved.value == "Mira Quell"


def test_hidden_white_answer_key_is_not_evidence(tmp_path: Path) -> None:
    path = tmp_path / "hidden.pdf"
    make_pdf(path, hidden=True)
    assert extract_native_evidence(path) == []
