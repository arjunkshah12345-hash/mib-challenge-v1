from __future__ import annotations

from datetime import date
import re
from typing import Mapping


FIELDS = (
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
)
STRING_FIELDS = FIELDS[:-1]
CASE_ID = re.compile(r"^MIB-\d{6}$")
SPONSOR_ID = re.compile(r"^SPN-\d{4}$")
FEE_VALUES = {"paid", "waived", "unpaid", "unknown"}
ADJUDICATION_VALUES = {"APPROVED", "DENIED", "NEEDS_REVIEW"}


def validate_prediction(prediction: Mapping[str, object]) -> list[str]:
    errors = []
    keys = set(prediction)
    expected = set(FIELDS)
    if missing := expected - keys:
        errors.append(f"missing fields: {sorted(missing)}")
    if extra := keys - expected:
        errors.append(f"unexpected fields: {sorted(extra)}")

    for field in STRING_FIELDS:
        if field in prediction and not isinstance(prediction[field], str):
            errors.append(f"{field} must be a string")

    case_id = prediction.get("case_id")
    if isinstance(case_id, str) and not CASE_ID.fullmatch(case_id):
        errors.append("case_id must match MIB-NNNNNN")
    sponsor_id = prediction.get("sponsor_id")
    if isinstance(sponsor_id, str) and not SPONSOR_ID.fullmatch(sponsor_id):
        errors.append("sponsor_id must match SPN-NNNN")

    arrival_date = prediction.get("arrival_date")
    if isinstance(arrival_date, str):
        try:
            date.fromisoformat(arrival_date)
        except ValueError:
            errors.append("arrival_date must be an ISO calendar date")

    if prediction.get("fee_status") not in FEE_VALUES:
        errors.append("invalid fee_status")
    if prediction.get("adjudication") not in ADJUDICATION_VALUES:
        errors.append("invalid adjudication")

    confidence = prediction.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        errors.append("confidence must be a number between 0 and 1")
    return errors
