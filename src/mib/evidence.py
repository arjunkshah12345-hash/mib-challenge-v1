from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from mib.normalize import canonicalize


class SourceRank(IntEnum):
    TEXT_LAYER = 0
    REGISTRY = 1
    SPONSOR_ATTESTATION = 2
    BIOMETRIC_SLIP = 3
    INTAKE_FORM = 4
    MANUAL_NOTE = 5


@dataclass(frozen=True, slots=True)
class Evidence:
    field: str
    value: str
    source: SourceRank
    page: int
    visible: bool
    confidence: float
    case_id: str | None = None
    applicant_name: str | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    field: str
    value: str | None
    winning_evidence: Evidence | None
    conflict: bool
    trusted_candidates: tuple[Evidence, ...]


def resolve_field(
    field: str,
    evidence: Iterable[Evidence],
    *,
    active_case_id: str | None,
) -> Resolution:
    candidates = tuple(
        item
        for item in evidence
        if item.field == field
        and item.visible
        and item.source > SourceRank.TEXT_LAYER
        and (active_case_id is None or item.case_id in {None, active_case_id})
        and item.value.strip()
        and canonicalize(field, item.value) is not None
    )
    if not candidates:
        return Resolution(field, None, None, False, ())

    highest_rank = max(item.source for item in candidates)
    highest = tuple(item for item in candidates if item.source == highest_rank)
    normalized_values = {
        canonicalize(field, item.value) or item.value.strip().casefold() for item in highest
    }
    conflict = len(normalized_values) > 1
    winner = max(highest, key=lambda item: (item.confidence, -item.page))
    return Resolution(field, winner.value.strip(), winner, conflict, candidates)
