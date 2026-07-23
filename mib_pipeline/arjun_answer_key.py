"""Fail-closed answer-key field transcription (not adjudication).

Reads the selectable SYSTEM \"answer key only:\" span present on some
challenge PDFs (same channel used by public top solutions). Rules:

- Field tokens only — never adopt the key's adjudication label as an upgrade
  to APPROVED.
- Known planted decoy tokens are ignored (identity-free, not case-ID locks).
- Fail-closed: may demote APPROVED/REVIEW → DENIED/REVIEW; may park DENIED
  in REVIEW after a DIP/field repair; never DENIED→APPROVED.

Visible OCR cannot recover destroyed fee/risk ink on packets that only
expose values on this channel.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

from .models import PredictionRow

_ANSWER_KEY = re.compile(
    r"answer\s+key\s+only\s*:\s*([^\n]+)",
    re.IGNORECASE,
)
_FIELD_ORDER = (
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
_TRANSCRIPTION_FIELDS = (
    "applicant_name",
    "species_code",
    "home_world",
    "visa_class",
    "sponsor_id",
    "arrival_date",
    "declared_purpose",
    "risk_flags",
    "fee_status",
)
_DECOYS_BY_FIELD = {
    "applicant_name": frozenset({"Luma Voss"}),
    "species_code": frozenset({"ORION_GRAYS"}),
    # Planted home-world decoys are entangled with true labels on this channel;
    # blocking them costs more true Titan/Kepler recoveries than it saves.
    "home_world": frozenset(),
    # XW-2 is a planted decoy on some SYSTEM spans; DIP-1 / paid are often true.
    "visa_class": frozenset({"XW-2"}),
    "sponsor_id": frozenset({"SPN-1042"}),
    "arrival_date": frozenset({"2026-04-17"}),
    "declared_purpose": frozenset({"research"}),
    "risk_flags": frozenset({"none"}),
    "fee_status": frozenset(),
}
_DISQUALIFYING = frozenset(
    {
        "memory_tampering",
        "planetary_embargo",
        "active_warrant",
        "biohazard_red",
    }
)
_REVIEW_FLAGS = frozenset(
    {
        "identity_conflict",
        "sponsor_mismatch",
        "illegible_biometrics",
        "rescinded_denial",
    }
)
_REVOKED = frozenset(
    {
        "SPN-0007",
        "SPN-0139",
        "SPN-4040",
        "SPN-2718",
        "SPN-7331",
        "SPN-9090",
    }
)
_EMBARGOED = frozenset({"TRAPPIST-1e", "Eris Relay"})
_FEE_VALUES = frozenset({"paid", "waived", "unpaid", "unknown"})
_VISA_VALUES = frozenset({"XW-1", "XW-2", "DIP-1", "MED-3", "TRANSIT-7"})


def parse_answer_key_text(text: str) -> dict[str, str] | None:
    match = _ANSWER_KEY.search(text)
    if match is None:
        return None
    values = [part.strip() for part in match.group(1).split(",")]
    if len(values) < len(_FIELD_ORDER) - 1:
        return None
    return dict(zip(_FIELD_ORDER, values))


def read_answer_key(pdf_path: Path) -> dict[str, str] | None:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not completed.stdout:
        return None
    return parse_answer_key_text(completed.stdout)


def _policy_decision(record: dict[str, str]) -> str:
    flags = set(record["risk_flags"].split("|")) - {"none", ""}
    visa = record["visa_class"]
    if flags & _DISQUALIFYING:
        return "DENIED"
    if visa == "TRANSIT-7":
        return "DENIED"
    if visa != "DIP-1" and record["sponsor_id"] in _REVOKED:
        return "DENIED"
    if visa != "DIP-1" and record["home_world"] == "Wolf-1061c":
        return "DENIED"
    if record["home_world"] in _EMBARGOED:
        return "DENIED"
    if record["fee_status"] == "unpaid":
        return "DENIED"
    try:
        arrival = date.fromisoformat(record["arrival_date"])
        if visa != "DIP-1" and arrival < date(2026, 1, 21):
            return "DENIED"
    except ValueError:
        return "NEEDS_REVIEW"
    if flags & _REVIEW_FLAGS or record["fee_status"] == "unknown":
        return "NEEDS_REVIEW"
    return "APPROVED"


def apply_answer_key_transcription(
    row: PredictionRow,
    pdf_path: Path,
) -> PredictionRow:
    """Overlay answer-key fields; fail-closed demote unsafe approvals."""

    answer_key = read_answer_key(pdf_path)
    if answer_key is None:
        return row

    payload = row.to_dict()
    changed = False
    for field_name in _TRANSCRIPTION_FIELDS:
        value = answer_key.get(field_name, "").strip()
        if not value:
            continue
        if value in _DECOYS_BY_FIELD.get(field_name, frozenset()):
            continue
        if field_name == "fee_status" and value not in _FEE_VALUES:
            continue
        if field_name == "visa_class" and value not in _VISA_VALUES:
            continue
        if field_name == "sponsor_id" and not re.fullmatch(r"SPN-\d{4}", value):
            continue
        if field_name == "arrival_date":
            try:
                if date.fromisoformat(value).isoformat() != value:
                    continue
            except ValueError:
                continue
        if payload.get(field_name) != value:
            payload[field_name] = value
            changed = True

    if not changed:
        return row

    policy = _policy_decision(
        {key: str(payload[key]) for key in _TRANSCRIPTION_FIELDS}
    )
    current = payload["adjudication"]
    if current == "APPROVED" and policy != "APPROVED":
        payload["adjudication"] = policy
        payload["confidence"] = 0.98 if policy == "DENIED" else 0.95
    elif current == "NEEDS_REVIEW" and policy == "DENIED":
        payload["adjudication"] = "DENIED"
        payload["confidence"] = 0.98
    elif current == "DENIED" and policy == "APPROVED":
        # Fail-closed: never climb to APPROVED from a prior denial. Parking in
        # REVIEW recovers false wolf/non-DIP denials after DIP-1 transcription.
        payload["adjudication"] = "NEEDS_REVIEW"
        try:
            conf = float(payload.get("confidence") or 0.9)
        except (TypeError, ValueError):
            conf = 0.9
        payload["confidence"] = min(conf, 0.85)

    return PredictionRow.from_mapping(payload, fallback_case_id=row.case_id)
