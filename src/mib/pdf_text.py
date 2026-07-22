from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import fitz

from mib.evidence import Evidence, SourceRank
from mib.normalize import RISK_FLAGS


LABELS = {
    "case id": "case_id",
    "applicant": "applicant_name",
    "registry name": "applicant_name",
    "subject name": "applicant_name",
    "species code": "species_code",
    "home world": "home_world",
    "visa class": "visa_class",
    "sponsor id": "sponsor_id",
    "arrival date": "arrival_date",
    "arrival date / time": "arrival_date",
    "declared purpose": "declared_purpose",
    "fee status": "fee_status",
    "amount": "fee_amount",
    "waiver code": "waiver_code",
    "risk flags": "risk_flags",
}
INLINE_LABELS = {
    "case id": "case_id",
    "applicant": "applicant_name",
    "registry name": "applicant_name",
    "subject name": "applicant_name",
    "species code": "species_code",
    "species match": "species_code",
    "home world": "home_world",
    "visa class": "visa_class",
    "sponsor id": "sponsor_id",
    "arrival date": "arrival_date",
    "declared purpose": "declared_purpose",
    "fee status": "fee_status",
    "amount": "fee_amount",
    "waiver code": "waiver_code",
    "observed flags": "risk_flags",
    "risk flags": "risk_flags",
}
MANUAL_CORRECTION = re.compile(
    r"^manual correction:\s*(?P<label>applicant|species code|home world|visa class|"
    r"sponsor(?: id)?|arrival date|declared purpose|fee status)\s+is\s+(?P<value>.+?)[.]?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    bbox: fitz.Rect
    color: int
    alpha: int
    size: float


def near_white(color: int) -> bool:
    channels = ((color >> 16) & 255, (color >> 8) & 255, color & 255)
    return min(channels) >= 240


def visible_spans(page: fitz.Page) -> list[TextSpan]:
    spans = []
    crop = page.cropbox
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for raw in line.get("spans", []):
                text = raw.get("text", "").strip()
                bbox = fitz.Rect(raw["bbox"])
                alpha = int(raw.get("alpha", 255))
                color = int(raw.get("color", 0))
                if (
                    text
                    and alpha >= 128
                    and not near_white(color)
                    and bbox.intersects(crop)
                    and bbox.y1 < page.rect.height - 25
                ):
                    spans.append(TextSpan(text, bbox, color, alpha, float(raw["size"])))
    return sorted(spans, key=lambda span: (round(span.bbox.y0, 1), span.bbox.x0))


def source_rank(spans: Iterable[TextSpan]) -> SourceRank:
    text = " ".join(span.text for span in spans).casefold()
    if "manual adjudicator note" in text or "adjudicator stamp" in text:
        return SourceRank.MANUAL_NOTE
    if "form i-8090" in text or "intake record" in text or "fee receipt" in text:
        return SourceRank.INTAKE_FORM
    if "biometric" in text:
        return SourceRank.BIOMETRIC_SLIP
    if "sponsor attestation" in text or "sponsor letter" in text:
        return SourceRank.SPONSOR_ATTESTATION
    if "registry" in text:
        return SourceRank.REGISTRY
    return SourceRank.TEXT_LAYER


def value_to_right(label: TextSpan, spans: list[TextSpan]) -> TextSpan | None:
    vertical_tolerance = max(4.0, label.bbox.height * 0.65)
    candidates = [
        span
        for span in spans
        if span is not label
        and span.bbox.x0 >= label.bbox.x1 - 2
        and abs(span.bbox.y0 - label.bbox.y0) <= vertical_tolerance
    ]
    return min(candidates, key=lambda span: span.bbox.x0, default=None)


def extract_native_evidence(path: Path) -> list[Evidence]:
    evidence = []
    with fitz.open(path) as document:
        for page_number, page in enumerate(document):
            spans = visible_spans(page)
            rank = source_rank(spans)
            if rank == SourceRank.TEXT_LAYER:
                continue
            page_case_ids = [span.text for span in spans if span.text.startswith("MIB-")]
            page_case_id = page_case_ids[0].split()[0].rstrip("|") if page_case_ids else None
            page_text = " ".join(span.text for span in spans)
            if rank == SourceRank.SPONSOR_ATTESTATION:
                sponsor = re.search(r"\bSponsor\s+(SPN-\d{4})\s+attests", page_text, re.IGNORECASE)
                applicant = re.search(
                    r"\battests\s+that\s+(.+?)\s+is\s+expected\s+on\s+Earth", page_text, re.IGNORECASE
                )
                purpose = re.search(
                    r"\bexpected\s+on\s+Earth\s+for\s+(.+?)\.\s+The\s+sponsor",
                    page_text,
                    re.IGNORECASE,
                )
                visa = re.search(r"\bclass\s+([A-Z]+-\d)\s+compliance", page_text, re.IGNORECASE)
                prose_fields = {
                    "sponsor_id": sponsor.group(1) if sponsor else None,
                    "applicant_name": applicant.group(1) if applicant else None,
                    "declared_purpose": purpose.group(1) if purpose else None,
                    "visa_class": visa.group(1) if visa else None,
                }
                for field, value in prose_fields.items():
                    if value:
                        evidence.append(
                            Evidence(field, value, rank, page_number, True, 0.995, page_case_id)
                        )
            if rank == SourceRank.MANUAL_NOTE:
                mentioned_flags = sorted(flag for flag in RISK_FLAGS if flag in page_text.casefold())
                if mentioned_flags:
                    evidence.append(
                        Evidence(
                            "risk_flags",
                            "|".join(mentioned_flags),
                            rank,
                            page_number,
                            True,
                            0.995,
                            page_case_id,
                        )
                    )
            for span in spans:
                adjudication_text = span.text.strip().upper()
                if rank == SourceRank.MANUAL_NOTE and adjudication_text in {
                    "APPROVED",
                    "DENIED",
                    "REVIEW",
                    "NEEDS_REVIEW",
                }:
                    evidence.append(
                        Evidence(
                            field="adjudication",
                            value="NEEDS_REVIEW" if adjudication_text == "REVIEW" else adjudication_text,
                            source=rank,
                            page=page_number,
                            visible=True,
                            confidence=0.995,
                            case_id=page_case_id,
                        )
                    )
                    continue
                correction = MANUAL_CORRECTION.match(span.text)
                if correction:
                    label = correction.group("label").casefold()
                    field = "sponsor_id" if label == "sponsor" else INLINE_LABELS[label]
                    evidence.append(
                        Evidence(
                            field=field,
                            value=correction.group("value").strip(),
                            source=SourceRank.MANUAL_NOTE,
                            page=page_number,
                            visible=True,
                            confidence=0.995,
                            case_id=page_case_id,
                        )
                    )
                    continue

                if ":" in span.text:
                    label, value = (part.strip() for part in span.text.split(":", 1))
                    field = INLINE_LABELS.get(label.casefold())
                    if field and value:
                        evidence.append(
                            Evidence(
                                field=field,
                                value=value,
                                source=rank,
                                page=page_number,
                                visible=True,
                                confidence=0.995,
                                case_id=page_case_id,
                            )
                        )
                        continue

                field = LABELS.get(span.text.rstrip(":").casefold())
                if field is None:
                    continue
                value = value_to_right(span, spans)
                if value is None:
                    continue
                evidence.append(
                    Evidence(
                        field=field,
                        value=value.text,
                        source=rank,
                        page=page_number,
                        visible=True,
                        confidence=0.995,
                        case_id=page_case_id,
                    )
                )
    return evidence
