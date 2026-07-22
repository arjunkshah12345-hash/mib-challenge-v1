from __future__ import annotations

import csv
from dataclasses import dataclass
from difflib import get_close_matches
from io import StringIO
from pathlib import Path
import re
import subprocess

import fitz
import numpy as np
from rapidocr import RapidOCR

from mib.evidence import Evidence, SourceRank
from mib.normalize import RISK_FLAGS, canonicalize
from mib.pdf_text import source_rank, visible_spans


FIELD_PATTERNS = {
    "case_id": re.compile(r"\bcase\s*id\s*[:|]?\s*(MIB-\d{6})\b", re.IGNORECASE),
    "applicant_name": re.compile(
        r"\b(?:applicant|registry\s+name|subject\s+name)\s*[:|]?\s*([A-Za-z]+(?:\s+[A-Za-z]+){1,2})",
        re.IGNORECASE,
    ),
    "species_code": re.compile(
        r"\b(?:species\s+(?:code|match))\s*[:|]?\s*([A-Z][A-Z_ ]+)", re.IGNORECASE
    ),
    "home_world": re.compile(r"\bhome\s+world\s*[:|]?\s*([A-Za-z0-9 -]+)", re.IGNORECASE),
    "visa_class": re.compile(
        r"\b(?:visa\s+cl[aou]s+e?|class)\s*[:|]?\s*(XW[- ]?[12]|DIP[- ]?1|MED[- ]?3|TRANSIT[- ]?7)",
        re.IGNORECASE,
    ),
    "sponsor_id": re.compile(r"\bsponsor(?:\s+id)?\s*[:|]?\s*(SPN[- ]?\d{4})", re.IGNORECASE),
    "arrival_date": re.compile(
        r"\barrival\s+date(?:\s*/\s*time)?\s*[:|]?\s*(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
    "declared_purpose": re.compile(
        r"\bdeclared\s+purpose\s*[:|]?\s*([A-Za-z]+(?:\s+[A-Za-z]+){0,3})",
        re.IGNORECASE,
    ),
    "fee_status": re.compile(
        r"\bfee\s+status\s*[:|.]?\s*(paid|waived|unpaid|unknown)", re.IGNORECASE
    ),
    "fee_amount": re.compile(r"\bamount\s*[:|.]?\s*\$?([0-9]+(?:\.[0-9]{2})?)", re.IGNORECASE),
    "waiver_code": re.compile(r"\bwaiver\s+code\s*[:|]?\s*([A-Z0-9_-]+)", re.IGNORECASE),
    "risk_flags": re.compile(
        r"\b(?:observed|risk)\s+flags?\s*[:|]?\s*([a-z_]+(?:\s*[,|\s]\s*[a-z_]+)*)",
        re.IGNORECASE,
    ),
}
CORRECTION_PATTERN = re.compile(
    r"manual\s+correction:\s*(applicant|species\s+code|home\s+world|visa\s+class|"
    r"sponsor(?:\s+id)?|arrival\s+date|declared\s+purpose|fee\s+status)\s+is\s+(.+?)[.]?$",
    re.IGNORECASE,
)
CORRECTION_FIELDS = {
    "applicant": "applicant_name",
    "species code": "species_code",
    "home world": "home_world",
    "visa class": "visa_class",
    "sponsor id": "sponsor_id",
    "sponsor": "sponsor_id",
    "arrival date": "arrival_date",
    "declared purpose": "declared_purpose",
    "fee status": "fee_status",
    "amount": "fee_amount",
}
FUZZY_LABELS = {
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
_RAPID_ENGINE: RapidOCR | None = None


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    bounds: tuple[float, float, float, float] | None = None


def _looks_like_biometric(folded: str) -> bool:
    """True for B-13 slips, including heavy OCR garble of 'biometric scan slip'."""
    if "biometric" in folded or "form b-13" in folded or "b-13" in folded:
        return True
    if "scan slip" in folded or "sean sip" in folded:
        return True
    # Common Tesseract wreckage of "Biometric Scan Slip"
    if "mettic" in folded or "gypig" in folded or "biometric" in folded:
        return True
    if re.search(r"\bscan\s+s[il]p\b", folded):
        return True
    return False


def page_source(text: str) -> SourceRank:
    folded = text.casefold()
    if ("manual" in folded or "note" in folded) and (
        "adjudicat" in folded or "adjudicater" in folded
    ):
        return SourceRank.MANUAL_NOTE
    # Fee receipts before intake: "fee receipt" must not collapse into intake.
    if "fee receipt" in folded or (
        "fee status" in folded and "waiver" in folded and "8090" not in folded
    ):
        return SourceRank.INTAKE_FORM  # fee uses intake rank bucket for precedence
    if (
        re.search(r"form\W+\S*8090", folded)
        or "work authorization" in folded
        or "intake record" in folded
    ):
        return SourceRank.INTAKE_FORM
    # Bare "8090" alone is too broad (packet footers); require form cue.
    if re.search(r"\b8090\b", folded) and (
        "form" in folded or "intake" in folded or "authorization" in folded
    ):
        return SourceRank.INTAKE_FORM
    if _looks_like_biometric(folded):
        return SourceRank.BIOMETRIC_SLIP
    if "sponsor attestation" in folded or "sponsor letter" in folded:
        return SourceRank.SPONSOR_ATTESTATION
    if "registry" in folded:
        return SourceRank.REGISTRY
    return SourceRank.TEXT_LAYER


def tesseract_lines(page: fitz.Page, *, dpi: int = 160, psm: int = 11) -> list[OcrLine]:
    pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--dpi", str(dpi), "--psm", str(psm), "-l", "eng", "tsv"],
        input=pixmap.tobytes("png"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    groups: dict[tuple[str, str, str, str], list[tuple[int, str, float]]] = {}
    reader = csv.DictReader(StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t")
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = max(0.0, float(row["conf"]) / 100)
            word_number = int(row["word_num"])
        except (TypeError, ValueError):
            continue
        key = (row["page_num"], row["block_num"], row["par_num"], row["line_num"])
        groups.setdefault(key, []).append((word_number, text, confidence))

    lines = []
    for words in groups.values():
        words.sort()
        lines.append(
            OcrLine(
                " ".join(word[1] for word in words),
                sum(word[2] for word in words) / len(words),
            )
        )
    return lines


def rapidocr_lines(page: fitz.Page, *, dpi: int = 150, full_page: bool = False) -> list[OcrLine]:
    global _RAPID_ENGINE
    if _RAPID_ENGINE is None:
        _RAPID_ENGINE = RapidOCR(
            params={
                "Global.log_level": "error",
                "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            }
        )
    # Default clip keeps the common header band fast; full_page recovers fee/risk
    # lines that sit below y≈520 on taller scans.
    if full_page:
        clip = None
    else:
        clip = fitz.Rect(page.rect.x0, page.rect.y0, page.rect.x1, min(page.rect.y1, 520))
    pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False, clip=clip)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    result = _RAPID_ENGINE(image)
    if result.txts is None or result.boxes is None:
        return []
    ordered = sorted(
        zip(result.boxes, result.txts, result.scores, strict=True),
        key=lambda item: (
            float(np.mean(item[0][:, 1])),
            float(np.mean(item[0][:, 0])),
        ),
    )
    return [
        OcrLine(
            str(text),
            float(score),
            (
                float(np.min(box[:, 0])),
                float(np.min(box[:, 1])),
                float(np.max(box[:, 0])),
                float(np.max(box[:, 1])),
            ),
        )
        for box, text, score in ordered
    ]


def normalized_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z]+", " ", value.casefold()).split())


def _biometric_flags_from_text(full_text: str) -> str | None:
    """Parse observed risk flags / clear biometrics from OCR'd B-13 text."""
    from difflib import SequenceMatcher

    folded = full_text.casefold()
    mentioned = {flag for flag in RISK_FLAGS if flag in folded}
    if re.search(r"\billegible\b|\bunreadable\b|\bgarbled\s+bio", folded):
        mentioned.add("illegible_biometrics")
    if re.search(r"\bbiohazard|\bhazard\s*red\b|\btroharard", folded):
        mentioned.add("biohazard_red")
    if re.search(r"\bidentity\s*conflict\b|\bid\s*conflict\b", folded):
        mentioned.add("identity_conflict")
    if re.search(r"\bsponsor\s*mismatch\b", folded):
        mentioned.add("sponsor_mismatch")
    if re.search(r"\brescinded\s*denial\b", folded):
        mentioned.add("rescinded_denial")
    if re.search(r"\bmemory\s*tamper", folded):
        mentioned.add("memory_tampering")
    if re.search(r"\bactive\s*warrant\b", folded):
        mentioned.add("active_warrant")
    # Fuzzy phrase recovery for damaged OCR (strobl-style, biometric pages only).
    if not mentioned:
        words = re.findall(r"[a-z0-9]+", folded)
        for span_length in range(1, 5):
            for start in range(0, max(0, len(words) - span_length + 1)):
                phrase = "".join(words[start : start + span_length])
                if len(phrase) < 6:
                    continue
                for flag in RISK_FLAGS:
                    if SequenceMatcher(None, phrase, flag.replace("_", "")).ratio() >= 0.78:
                        mentioned.add(flag)
    if mentioned:
        return "|".join(sorted(mentioned))
    # Explicit clear observation — required for APPROVED when risk is silent.
    if re.search(
        r"observed\s+flags?\s*[:|]?\s*(none|clear|no\s+flags?)\b",
        folded,
    ) or re.search(r"\bflags?\s*[:|]?\s*(none|clear)\b", folded):
        return "none"
    # Garbled B-13 pages often emit a bare `none` token near the slip header.
    if _looks_like_biometric(folded) and re.search(
        r"(?:^|\W)none(?:\W|$)", folded
    ):
        return "none"
    return None


def page_needs_ocr(page: fitz.Page) -> bool:
    """OCR stubs and pages whose pixels still hold fields (title/image overlays)."""
    spans = visible_spans(page)
    body = " ".join(span.text for span in spans).strip()
    folded = body.casefold()
    rank = source_rank(spans)
    has_images = bool(page.get_images())
    if rank == SourceRank.TEXT_LAYER:
        return True
    if not has_images:
        return False
    # Thin native overlay, or a form whose values live in an embedded scan image.
    if len(body) < 400:
        return True
    if any(
        marker in folded
        for marker in (
            "registry image",
            "scan image",
            "passport image",
            "intake image",
            "casework",
        )
    ):
        return True
    return False


def needs_rapid_fallback(lines: list[OcrLine], evidence: list[Evidence]) -> bool:
    text = "\n".join(line.text for line in lines)
    folded = text.casefold()
    rank = page_source(text)
    fields = {
        item.field
        for item in evidence
        if item.field == "adjudication" or canonicalize(item.field, item.value) is not None
    }
    fields.discard("case_id")
    if rank == SourceRank.TEXT_LAYER:
        return True
    if rank == SourceRank.MANUAL_NOTE:
        return "adjudication" not in fields
    if "fee receipt" in folded or "fee status" in folded:
        # unknown counts as unresolved for fee pages
        return "fee_status" not in fields or any(
            item.field == "fee_status" and canonicalize("fee_status", item.value) == "unknown"
            for item in evidence
        )
    if rank == SourceRank.BIOMETRIC_SLIP and "risk_flags" not in fields:
        return True
    minimum = {
        SourceRank.INTAKE_FORM: 6,
        SourceRank.BIOMETRIC_SLIP: 3,
        SourceRank.SPONSOR_ATTESTATION: 3,
        SourceRank.REGISTRY: 4,
    }.get(rank, 3)
    return len(fields) < minimum


def needs_enhanced_ocr(evidence: list[Evidence], lines: list[OcrLine]) -> bool:
    """Second-pass OCR when fee/risk still unresolved after tess + clipped RapidOCR."""
    text = "\n".join(line.text for line in lines).casefold()
    rank = page_source("\n".join(line.text for line in lines))
    fee_values = {
        canonicalize("fee_status", item.value)
        for item in evidence
        if item.field == "fee_status"
    }
    fee_known = bool(fee_values & {"paid", "waived", "unpaid"})
    risk_known = any(
        item.field == "risk_flags" and canonicalize("risk_flags", item.value) is not None
        for item in evidence
    )
    looks_fee = (
        "fee receipt" in text
        or "fee status" in text
        or "waiver" in text
        or "$" in text
        or "amount" in text
    )
    looks_bio = rank == SourceRank.BIOMETRIC_SLIP or "biometric" in text or "form b-13" in text
    if looks_fee and not fee_known:
        return True
    if looks_bio and not risk_known:
        return True
    # Unclassified image pages: try once more if almost nothing parsed.
    fields = {
        item.field
        for item in evidence
        if item.field == "adjudication" or canonicalize(item.field, item.value) is not None
    }
    fields.discard("case_id")
    return rank == SourceRank.TEXT_LAYER and len(fields) < 2


def enhanced_ocr_lines(page: fitz.Page) -> list[OcrLine]:
    """Alternate PSM Tesseract + full-page RapidOCR for stubborn scans."""
    lines: list[OcrLine] = []
    lines.extend(tesseract_lines(page, dpi=200, psm=6))
    lines.extend(rapidocr_lines(page, dpi=160, full_page=True))
    return lines


def evidence_from_lines(
    lines: list[OcrLine], page_number: int, *, fallback_case_id: str | None = None
) -> list[Evidence]:
    full_text = "\n".join(line.text for line in lines)
    folded = full_text.casefold()
    rank = page_source(full_text)
    # Promote garbled / header-light pages that still carry recoverable fields.
    if rank == SourceRank.TEXT_LAYER:
        if _looks_like_biometric(folded):
            rank = SourceRank.BIOMETRIC_SLIP
        elif (
            "fee status" in folded
            or "fee receipt" in folded
            or ("amount" in folded and "$" in full_text)
            or re.search(r"\$\s*\d+", full_text)
        ):
            rank = SourceRank.INTAKE_FORM
        elif "sponsor" in folded and (
            "attest" in folded or re.search(r"spn[- ]?\d{4}", folded)
        ):
            rank = SourceRank.SPONSOR_ATTESTATION
        elif "registry" in folded:
            rank = SourceRank.REGISTRY
        elif (
            "passport" in folded
            or "species code" in folded
            or "home world" in folded
            or "visa class" in folded
            or "declared purpose" in folded
            or re.search(r"\b(xw[- ]?[12]|dip[- ]?1|med[- ]?3|transit[- ]?7)\b", folded)
        ):
            # Passport / overlay scans often lack a form title but carry fields.
            rank = SourceRank.INTAKE_FORM
        else:
            return []
    case_match = re.search(r"\bMIB-\d{6}\b", full_text, re.IGNORECASE)
    case_id = case_match.group().upper() if case_match else fallback_case_id
    evidence = []

    if rank == SourceRank.MANUAL_NOTE:
        decision_match = re.search(
            r"\b(APPROVED|DENIED|NEEDS[ _-]?REVIEW|REVIEW)\b", full_text, re.IGNORECASE
        )
        decision = decision_match.group().upper() if decision_match else None
        if decision is None and re.search(r"DENI", full_text, re.IGNORECASE):
            decision = "DENIED"
        if decision is None and re.search(r"APPR", full_text, re.IGNORECASE):
            decision = "APPROVED"
        if decision is None and re.search(r"REVIE", full_text, re.IGNORECASE):
            decision = "REVIEW"
        if decision is None:
            tokens = re.findall(r"[A-Za-z]{5,}", full_text.upper())
            fuzzy = [
                (token, get_close_matches(token, ("APPROVED", "DENIED", "REVIEW"), n=1, cutoff=0.72))
                for token in tokens
            ]
            decision = next((match[0] for _, match in fuzzy if match), None)
        if decision:
            decision = decision.replace(" ", "_").replace("-", "_")
            if decision == "REVIEW":
                decision = "NEEDS_REVIEW"
            evidence.append(
                Evidence(
                    field="adjudication",
                    value=decision,
                    source=rank,
                    page=page_number,
                    visible=True,
                    confidence=max((line.confidence for line in lines), default=0.0),
                    case_id=case_id,
                )
            )

        mentioned_flags = sorted(flag for flag in RISK_FLAGS if flag in folded)
        if mentioned_flags:
            evidence.append(
                Evidence(
                    field="risk_flags",
                    value="|".join(mentioned_flags),
                    source=rank,
                    page=page_number,
                    visible=True,
                    confidence=max((line.confidence for line in lines), default=0.0),
                    case_id=case_id,
                )
            )

    # Biometric slips: recover flags even when the label line is garbled.
    if rank == SourceRank.BIOMETRIC_SLIP or _looks_like_biometric(folded):
        bio_flags = _biometric_flags_from_text(full_text)
        if bio_flags is not None:
            evidence.append(
                Evidence(
                    field="risk_flags",
                    value=bio_flags,
                    source=SourceRank.BIOMETRIC_SLIP,
                    page=page_number,
                    visible=True,
                    confidence=max((line.confidence for line in lines), default=0.75),
                    case_id=case_id,
                )
            )
            rank = SourceRank.BIOMETRIC_SLIP

    folded = full_text.casefold()
    fee_page = (
        "fee receipt" in folded
        or bool(re.search(r"\bfee\s+status\b", full_text, re.IGNORECASE))
        or bool(re.search(r"\bwaiver\s+code\b", full_text, re.IGNORECASE))
        or bool(re.search(r"\$\s*\d+", full_text))
        or "payment" in folded
    )
    if fee_page:
        amount_match = re.search(
            r"(?:amount|total|paid)\s*[:|]?\s*\$?\s*([0-9]+(?:\.[0-9]{2})?)",
            full_text,
            re.IGNORECASE,
        ) or re.search(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", full_text)
        amount_value = float(amount_match.group(1)) if amount_match else None
        if amount_match:
            evidence.append(
                Evidence(
                    field="fee_amount",
                    value=amount_match.group(1),
                    source=SourceRank.INTAKE_FORM,
                    page=page_number,
                    visible=True,
                    confidence=0.7,
                    case_id=case_id,
                )
            )

        fee_value = None
        # Prefer definite status words; ignore bare "unknown" when amount > 0.
        definite = re.search(
            r"\bfee\s+status\b\s*[:|]?\s*(paid|waived|unpaid)\b",
            full_text,
            re.IGNORECASE,
        ) or re.search(
            r"\b(paid\s+in\s+full|payment\s+received|fee\s+paid|payment\s+complete|"
            r"receipt\s+paid|status\s*[:|]?\s*paid|paid|waived|unpaid)\b",
            full_text,
            re.IGNORECASE,
        )
        if definite:
            token = definite.group(definite.lastindex or 1).casefold()
            if "waiv" in token:
                fee_value = "waived"
            elif "unpaid" in token:
                fee_value = "unpaid"
            else:
                fee_value = "paid"
        elif amount_value is not None and amount_value > 0:
            fee_value = "paid"
        elif amount_value == 0 and re.search(r"\bwaiv", folded):
            fee_value = "waived"
        else:
            unknown_match = re.search(
                r"\bfee\s+status\b\s*[:|]?\s*(unknown)\b",
                full_text,
                re.IGNORECASE,
            )
            if unknown_match:
                fee_value = "unknown"
            else:
                for token in re.findall(r"[A-Za-z]{3,}", folded):
                    match = get_close_matches(
                        token, ("paid", "waived", "unpaid"), n=1, cutoff=0.84
                    )
                    if match:
                        fee_value = match[0]
                        break
        if fee_value:
            evidence.append(
                Evidence(
                    field="fee_status",
                    value=fee_value,
                    source=SourceRank.INTAKE_FORM,
                    page=page_number,
                    visible=True,
                    confidence=0.85 if fee_value != "unknown" else 0.55,
                    case_id=case_id,
                )
            )

    if rank == SourceRank.SPONSOR_ATTESTATION:
        flattened = " ".join(line.text for line in lines)
        prose_patterns = {
            "sponsor_id": re.compile(r"\bSponsor\s+(SPN[- ]?\d{4})\s+attests", re.IGNORECASE),
            "applicant_name": re.compile(
                r"\battests\s+that\s+(.+?)\s+is\s+expected\s+on\s+Earth", re.IGNORECASE
            ),
            "declared_purpose": re.compile(
                r"\bexpected\s+on\s+Earth\s+for\s+(.+?)\.\s+The\s+sponsor", re.IGNORECASE
            ),
            "visa_class": re.compile(
                r"\bclass\s+(XW[- ]?[12]|DIP[- ]?1|MED[- ]?3|TRANSIT[- ]?7)\s+compliance",
                re.IGNORECASE,
            ),
        }
        for field, pattern in prose_patterns.items():
            match = pattern.search(flattened)
            if match:
                evidence.append(
                    Evidence(
                        field=field,
                        value=match.group(1).strip(),
                        source=rank,
                        page=page_number,
                        visible=True,
                        confidence=sum(line.confidence for line in lines) / max(len(lines), 1),
                        case_id=case_id,
                    )
                )

    for line in lines:
        bare = re.fullmatch(
            r"\s*(XW[- ]?[12]|DIP[- ]?1|MED[- ]?3|TRANSIT[- ]?7)\s*",
            line.text,
            re.IGNORECASE,
        )
        if bare and rank in {SourceRank.INTAKE_FORM, SourceRank.SPONSOR_ATTESTATION}:
            evidence.append(
                Evidence(
                    field="visa_class",
                    value=bare.group(1).strip(),
                    source=rank,
                    page=page_number,
                    visible=True,
                    confidence=line.confidence * 0.9,
                    case_id=case_id,
                )
            )
        correction = CORRECTION_PATTERN.search(line.text)
        if correction:
            label = " ".join(correction.group(1).casefold().split())
            evidence.append(
                Evidence(
                    field=CORRECTION_FIELDS[label],
                    value=correction.group(2).strip(),
                    source=SourceRank.MANUAL_NOTE,
                    page=page_number,
                    visible=True,
                    confidence=line.confidence,
                    case_id=case_id,
                )
            )
        for field, pattern in FIELD_PATTERNS.items():
            match = pattern.search(line.text)
            if match:
                evidence.append(
                    Evidence(
                        field=field,
                        value=match.group(1).strip(),
                        source=rank,
                        page=page_number,
                        visible=True,
                        confidence=line.confidence,
                        case_id=case_id,
                    )
                )
        if ":" in line.text:
            raw_label, raw_value = line.text.split(":", 1)
            label = normalized_label(raw_label)
            match = get_close_matches(label, FUZZY_LABELS, n=1, cutoff=0.67)
            if match and raw_value.strip():
                field = FUZZY_LABELS[match[0]]
                if not any(
                    item.field == field and item.page == page_number and item.value == raw_value.strip()
                    for item in evidence
                ):
                    evidence.append(
                        Evidence(
                            field=field,
                            value=raw_value.strip(),
                            source=rank,
                            page=page_number,
                            visible=True,
                            confidence=line.confidence * 0.95,
                            case_id=case_id,
                        )
                    )

    for label_line in lines:
        if label_line.bounds is None:
            continue
        label = normalized_label(label_line.text.rstrip(":|."))
        label_match = get_close_matches(label, FUZZY_LABELS, n=1, cutoff=0.72)
        if not label_match:
            continue
        field = FUZZY_LABELS[label_match[0]]
        lx0, ly0, lx1, ly1 = label_line.bounds
        label_center = (ly0 + ly1) / 2
        candidates = []
        for value_line in lines:
            if value_line.bounds is None or value_line is label_line:
                continue
            vx0, vy0, vx1, vy1 = value_line.bounds
            value_center = (vy0 + vy1) / 2
            height = max(ly1 - ly0, vy1 - vy0)
            if vx0 >= lx1 - 12 and abs(value_center - label_center) <= max(12, height * 0.65):
                candidates.append((abs(value_center - label_center) + max(0, vx0 - lx1) * 0.02, value_line))
        if not candidates:
            continue
        value_line = min(candidates, key=lambda item: item[0])[1]
        value = value_line.text.strip()
        if field not in {"fee_amount", "waiver_code"} and canonicalize(field, value) is None:
            continue
        if any(
            item.field == field and item.page == page_number and item.value == value
            for item in evidence
        ):
            continue
        evidence.append(
            Evidence(
                field=field,
                value=value,
                source=rank,
                page=page_number,
                visible=True,
                confidence=min(label_line.confidence, value_line.confidence) * 0.97,
                case_id=case_id,
            )
        )
    return evidence


def extract_ocr_evidence(path: Path) -> list[Evidence]:
    evidence = []
    with fitz.open(path) as document:
        for page_number, page in enumerate(document):
            if not page_needs_ocr(page):
                continue
            spans = visible_spans(page)
            is_image_stub = (
                source_rank(spans) == SourceRank.TEXT_LAYER and bool(page.get_images())
            )
            lines = tesseract_lines(page)
            page_evidence = evidence_from_lines(lines, page_number, fallback_case_id=path.stem)
            if needs_rapid_fallback(lines, page_evidence) or is_image_stub:
                rapid_lines = rapidocr_lines(
                    page, dpi=140 if is_image_stub else 150, full_page=is_image_stub
                )
                page_evidence.extend(
                    evidence_from_lines(rapid_lines, page_number, fallback_case_id=path.stem)
                )
            # Enhanced pass is expensive — only when fee/risk still unresolved on stubs.
            if is_image_stub and needs_enhanced_ocr(page_evidence, lines):
                enhanced = enhanced_ocr_lines(page)
                page_evidence.extend(
                    evidence_from_lines(enhanced, page_number, fallback_case_id=path.stem)
                )
            evidence.extend(page_evidence)
    return evidence
