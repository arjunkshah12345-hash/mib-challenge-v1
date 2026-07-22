from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
import json
import re

import fitz

from mib.evidence import Evidence, SourceRank, resolve_field
from mib.normalize import canonicalize
from mib.ocr import extract_ocr_evidence
from mib.pdf_text import extract_native_evidence
from mib.policy import (
    EMBARGOED_HOME_WORLDS,
    PUBLIC_REVOKED_SPONSORS,
    PolicyInput,
    adjudicate,
)


OUTPUT_FIELDS = (
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
DEFAULTS = {
    "applicant_name": "unknown",
    "species_code": "unknown",
    "home_world": "unknown",
    "visa_class": "unknown",
    "sponsor_id": "SPN-0000",
    "arrival_date": "1900-01-01",
    "declared_purpose": "unknown",
    "risk_flags": "none",
    "fee_status": "unknown",
}


def resolved_values(case_id: str, evidence: list[Evidence]) -> tuple[dict[str, str | None], bool]:
    values = {}
    has_conflict = False
    for field in OUTPUT_FIELDS:
        resolution = resolve_field(field, evidence, active_case_id=case_id)
        values[field] = canonicalize(field, resolution.value)
        has_conflict = has_conflict or resolution.conflict
    return values, has_conflict


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def packet_receipt_date(path: Path) -> date | None:
    with fitz.open(path) as document:
        raw = document.metadata.get("creationDate", "")
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def source_values(
    field: str,
    evidence: list[Evidence],
    source: SourceRank,
    case_id: str,
) -> set[str]:
    return {
        value
        for item in evidence
        if item.field == field
        and item.source == source
        and item.visible
        and item.confidence >= 0.9
        and item.case_id in {None, case_id}
        and (value := canonicalize(field, item.value)) is not None
    }


def derive_risk_flags(
    values: dict[str, str | None],
    evidence: list[Evidence],
    case_id: str,
) -> frozenset[str]:
    flags = set(
        () if values["risk_flags"] in {None, "none"} else values["risk_flags"].split("|")
    )
    if values["home_world"] in EMBARGOED_HOME_WORLDS:
        flags.add("planetary_embargo")
    return frozenset(flags)


def apply_identity_resolution(
    values: dict[str, str | None],
    evidence: list[Evidence],
    case_id: str,
) -> None:
    for field in ("applicant_name", "species_code", "home_world", "arrival_date"):
        if source_values(field, evidence, SourceRank.MANUAL_NOTE, case_id):
            continue
        registry = source_values(field, evidence, SourceRank.REGISTRY, case_id)
        if len(registry) == 1:
            values[field] = next(iter(registry))
            continue
        biometric = source_values(field, evidence, SourceRank.BIOMETRIC_SLIP, case_id)
        if len(biometric) == 1:
            values[field] = next(iter(biometric))


def has_risk_observation(evidence: list[Evidence], case_id: str) -> bool:
    """True when biometric/manual risk text is present and parseable.

    Uncanonical OCR garbage (e.g. ``troharard``) must not count as a clean
    ``none`` observation — that path previously allowed false APPROVED.
    Parseable ``none`` / ``clear`` counts as an observed clear slip and is the
    only non-note path that may unlock APPROVED (issue #5).
    """
    for item in evidence:
        if item.field != "risk_flags" or not item.visible:
            continue
        if item.source not in {SourceRank.BIOMETRIC_SLIP, SourceRank.MANUAL_NOTE}:
            continue
        if item.case_id not in {None, case_id}:
            continue
        parsed = canonicalize("risk_flags", item.value)
        if parsed is not None:
            return True
    return False


def has_observed_clear_risk(evidence: list[Evidence], case_id: str) -> bool:
    """Biometric/manual slip explicitly reports no risk flags."""
    for item in evidence:
        if item.field != "risk_flags" or not item.visible:
            continue
        if item.source not in {SourceRank.BIOMETRIC_SLIP, SourceRank.MANUAL_NOTE}:
            continue
        if item.case_id not in {None, case_id}:
            continue
        if canonicalize("risk_flags", item.value) == "none":
            return True
    return False


def risk_observation_unparseable(evidence: list[Evidence], case_id: str) -> bool:
    """Biometric/manual risk line exists but could not be canonicalized."""
    saw = False
    for item in evidence:
        if item.field != "risk_flags" or not item.visible:
            continue
        if item.source not in {SourceRank.BIOMETRIC_SLIP, SourceRank.MANUAL_NOTE}:
            continue
        if item.case_id not in {None, case_id}:
            continue
        saw = True
        if canonicalize("risk_flags", item.value) is not None:
            return False
    return saw


@lru_cache(maxsize=1)
def _confidence_table() -> dict[str, object]:
    path = Path(__file__).with_name("confidence_table.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def heuristic_confidence(
    adjudication: str,
    *,
    explicit_note: bool,
    missing_fields: int,
    conflict: bool,
    risk_unobserved: bool = False,
    fee_known: bool = True,
) -> float:
    """Return OOF Laplace-smoothed confidences; fall back to baked priors."""
    if explicit_note and adjudication == "DENIED":
        return 0.98
    if explicit_note and adjudication == "APPROVED":
        return 0.95
    if explicit_note:
        return 0.99
    table = _confidence_table()
    fee_key = "fee" if fee_known else "nofee"
    empirical = table.get(
        "empirical",
        {
            "APPROVED|fee": 0.94,
            "APPROVED|nofee": 0.97,
            "DENIED|fee": 0.94,
            "DENIED|nofee": 0.96,
            "NEEDS_REVIEW|fee": 0.47,
            "NEEDS_REVIEW|nofee": 0.55,
        },
    )
    review_reliability = {
        int(k): float(v)
        for k, v in table.get(
            "review_reliability",
            {
                "0": 0.89,
                "1": 0.38,
                "2": 0.52,
                "3": 0.40,
                "4": 0.26,
                "5": 0.36,
                "6": 0.27,
                "7": 0.11,
                "8": 0.17,
                "9": 0.13,
            },
        ).items()
    }
    risk_unobserved_conf = float(table.get("risk_unobserved", 0.38))

    def emp(adj: str, fee: str) -> float:
        return float(empirical.get(f"{adj}|{fee}", 0.5))

    if adjudication in {"APPROVED", "DENIED"} and not conflict and not risk_unobserved:
        return emp(adjudication, fee_key)
    if adjudication == "APPROVED":
        return 0.90
    if adjudication == "DENIED":
        return 0.91
    if conflict and not risk_unobserved:
        return min(0.50, emp("NEEDS_REVIEW", fee_key))
    if risk_unobserved and missing_fields == 0:
        return risk_unobserved_conf
    base = review_reliability.get(missing_fields, 0.30)
    return round(0.5 * base + 0.5 * emp("NEEDS_REVIEW", fee_key), 4)


def predict_pdf(path: Path) -> dict[str, object]:
    case_id = path.stem.upper()
    evidence = extract_native_evidence(path)
    evidence.extend(extract_ocr_evidence(path))
    values, conflict = resolved_values(case_id, evidence)
    attested = source_values("sponsor_id", evidence, SourceRank.SPONSOR_ATTESTATION, case_id)
    if (
        values["sponsor_id"] in PUBLIC_REVOKED_SPONSORS
        and attested
        and values["sponsor_id"] not in attested
    ):
        values["sponsor_id"] = next(iter(attested))
        conflict = True
    waiver = resolve_field("waiver_code", evidence, active_case_id=case_id)
    waiver_code = waiver.value.strip().upper() if waiver.value else None
    valid_waiver = waiver_code not in {None, "", "N/A", "NA", "NONE", "UNKNOWN"}
    amount = resolve_field("fee_amount", evidence, active_case_id=case_id)
    amount_match = re.search(r"\d+(?:\.\d{2})?", amount.value) if amount.value else None
    amount_value = float(amount_match.group()) if amount_match else None
    # Tiny integers are usually page numbers / case suffixes, not receipt totals.
    if amount_value is not None and amount_value < 10:
        amount_value = None
    # Prefer a definite fee token (paid/waived/unpaid) over a printed "unknown".
    definite_fees: list[str] = []
    for item in evidence:
        if item.field != "fee_status" or not item.visible:
            continue
        parsed = canonicalize("fee_status", item.value)
        if parsed in {"paid", "waived", "unpaid"}:
            definite_fees.append(parsed)
    definite_set = set(definite_fees)
    if {"paid", "unpaid"} <= definite_set:
        # Conflicting receipt OCR — never invent paid (FA path on MIB-000530).
        values["fee_status"] = "unknown"
        conflict = True
    elif definite_fees and values["fee_status"] in {None, "unknown"}:
        # Prefer waived, then unpaid, then paid. Preferring paid over unpaid
        # previously created a false APPROVED when amount OCR hallucinated paid.
        for preferred in ("waived", "unpaid", "paid"):
            if preferred in definite_set:
                values["fee_status"] = preferred
                break
    # Receipt OCR often prints Fee Status: unknown while Amount: $809.00 —
    # only promote unknown→paid on a credible positive amount when unpaid was
    # never observed. Do NOT invent unpaid from $0.00 + N/A.
    # Credible amounts also override a lone "unpaid" token (MIB-000514: status
    # OCR says unpaid while Amount: $809.00 and label is paid). Tiny amounts
    # were already nulled above, so this cannot revive the MIB-000530 FA path.
    if (
        amount_value is not None
        and amount_value >= 50
        and values["fee_status"] in {None, "unknown", "unpaid"}
        and "waived" not in definite_set
    ):
        values["fee_status"] = "paid"
    elif (
        values["fee_status"] in {None, "unknown"}
        and amount_value is not None
        and amount_value > 0
        and "unpaid" not in definite_set
    ):
        values["fee_status"] = "paid"
    elif values["fee_status"] is None and amount_value == 0 and valid_waiver:
        values["fee_status"] = "waived"
    if values["fee_status"] is None:
        for item in evidence:
            if item.field != "fee_status" or not item.visible:
                continue
            parsed = canonicalize("fee_status", item.value)
            if parsed is not None:
                values["fee_status"] = parsed
                break

    explicit = resolve_field("adjudication", evidence, active_case_id=case_id)
    explicit_adjudication = canonicalize("adjudication", explicit.value)
    risk_flags = derive_risk_flags(values, evidence, case_id)
    values["risk_flags"] = "|".join(sorted(risk_flags)) if risk_flags else "none"
    if "identity_conflict" in risk_flags:
        apply_identity_resolution(values, evidence, case_id)
    required = (
        "applicant_name",
        "species_code",
        "home_world",
        "visa_class",
        "arrival_date",
        "declared_purpose",
        "fee_status",
    )
    missing_fields = sum(values[field] is None for field in OUTPUT_FIELDS)
    risk_unobserved = not has_risk_observation(evidence, case_id)
    risk_garbled = risk_observation_unparseable(evidence, case_id)
    sponsor_resolution = resolve_field("sponsor_id", evidence, active_case_id=case_id)
    # Ignore low-confidence OCR hallucinations of revoked sponsors — but trust
    # attestation/registry confirmation, or solid OCR (>=0.90) of a real SPN id.
    attested_revoked = values["sponsor_id"] in (
        source_values("sponsor_id", evidence, SourceRank.SPONSOR_ATTESTATION, case_id)
        | source_values("sponsor_id", evidence, SourceRank.REGISTRY, case_id)
        | source_values("sponsor_id", evidence, SourceRank.MANUAL_NOTE, case_id)
    )
    winner = sponsor_resolution.winning_evidence
    ocr_only_revoked = (
        values["sponsor_id"] in PUBLIC_REVOKED_SPONSORS
        and not attested_revoked
        and winner is not None
        and winner.confidence < 0.90
    )
    policy_decision = adjudicate(
        PolicyInput(
            visa_class=values["visa_class"],
            sponsor_id=None if ocr_only_revoked else values["sponsor_id"],
            arrival_date=parse_date(values["arrival_date"]),
            receipt_date=packet_receipt_date(path),
            fee_status=values["fee_status"],
            home_world=values["home_world"],
            risk_flags=risk_flags,
            hardship_waiver=valid_waiver,
            required_field_missing=any(values[field] is None for field in required)
            or ocr_only_revoked,
            unresolved_conflict=conflict or risk_unobserved or risk_garbled or ocr_only_revoked,
        )
    )
    final_adjudication = explicit_adjudication or policy_decision.adjudication
    # Never approve from policy alone without observed clear biometrics or an
    # explicit APPROVED note (issue #5). Any other risk state → NEEDS_REVIEW.
    observed_clear = has_observed_clear_risk(evidence, case_id)
    if (
        final_adjudication == "APPROVED"
        and explicit_adjudication != "APPROVED"
        and not observed_clear
    ):
        final_adjudication = "NEEDS_REVIEW"
        conflict = True
    # If the only blocker was risk_unobserved conflict and we now have observed
    # clear biometrics, re-run policy without that conflict bit.
    elif (
        final_adjudication == "NEEDS_REVIEW"
        and explicit_adjudication is None
        and observed_clear
        and "unresolved_conflict" in policy_decision.reasons
        and not [r for r in policy_decision.reasons if r != "unresolved_conflict"]
    ):
        cleared = adjudicate(
            PolicyInput(
                visa_class=values["visa_class"],
                sponsor_id=None if ocr_only_revoked else values["sponsor_id"],
                arrival_date=parse_date(values["arrival_date"]),
                receipt_date=packet_receipt_date(path),
                fee_status=values["fee_status"],
                home_world=values["home_world"],
                risk_flags=risk_flags,
                hardship_waiver=valid_waiver,
                required_field_missing=any(values[field] is None for field in required)
                or ocr_only_revoked,
                unresolved_conflict=False,
            )
        )
        if cleared.adjudication == "APPROVED":
            final_adjudication = "APPROVED"
            conflict = False
    # False-approval kill: DIP-style waiver + non-DIP visa corroborated only by
    # intake (no sponsor/registry/manual visa) is a known adversarial pattern
    # (MIB-000865: labeled TRANSIT-7, intake prints XW-2 + DIP-WAIVER).
    if final_adjudication == "APPROVED" and explicit_adjudication != "APPROVED":
        visa_sources_present = {
            item.source
            for item in evidence
            if item.field == "visa_class"
            and item.visible
            and canonicalize("visa_class", item.value) is not None
        }
        intake_only_visa = visa_sources_present == {SourceRank.INTAKE_FORM}
        dip_style_waiver = bool(waiver_code) and "DIP" in waiver_code
        if (
            values["fee_status"] == "waived"
            and values["visa_class"] not in {None, "DIP-1"}
            and dip_style_waiver
            and intake_only_visa
        ):
            final_adjudication = "NEEDS_REVIEW"
            conflict = True
    prediction: dict[str, object] = {"case_id": case_id}
    prediction.update(
        {
            field: values[field] if values[field] is not None else DEFAULTS[field]
            for field in OUTPUT_FIELDS
        }
    )
    prediction["adjudication"] = final_adjudication
    fee_known = values["fee_status"] not in {None, "unknown"}
    prediction["confidence"] = heuristic_confidence(
        final_adjudication,
        explicit_note=explicit_adjudication is not None
        and final_adjudication == explicit_adjudication,
        missing_fields=missing_fields,
        conflict=conflict,
        risk_unobserved=risk_unobserved and final_adjudication == "NEEDS_REVIEW",
        fee_known=fee_known,
    )
    return prediction
