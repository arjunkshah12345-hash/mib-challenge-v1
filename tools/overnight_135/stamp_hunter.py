#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exhaustive stamp/risk OCR hunt on hard D2R and R2A packets.

Writes hits to artifacts/overnight_135/stamp_hits.jsonl. Never changes
predictions by itself - analysis only.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

OUT_DIR = ROOT / "artifacts" / "overnight_135"
OUT_DIR.mkdir(parents=True, exist_ok=True)
HITS = OUT_DIR / "stamp_hits.jsonl"
PROGRESS = OUT_DIR / "stamp_progress.json"

KEYWORDS = (
    "biohazard",
    "warrant",
    "embargo",
    "memory",
    "tamper",
    "illegible",
    "rescind",
    "mismatch",
    "identity",
    "denied",
    "stamp",
    "flags",
    "risk",
    "clean",
    "clear",
    "red",
)

DISQ = {"memory_tampering", "planetary_embargo", "active_warrant", "biohazard_red"}
REVIEW = {
    "illegible_biometrics",
    "rescinded_denial",
    "sponsor_mismatch",
    "identity_conflict",
}


def _targets() -> list[tuple[str, str]]:
    labels = {
        r["case_id"]: r
        for r in csv.DictReader((ROOT / "data" / "train_labels.csv").open())
    }
    preds_path = ROOT / "artifacts" / "predictions-train-v54-cfa0.jsonl"
    if not preds_path.exists():
        preds_path = ROOT / "artifacts" / "predictions-train-v55-rif.jsonl"
    preds = {
        json.loads(line)["case_id"]: json.loads(line)
        for line in preds_path.read_text().splitlines()
    }
    out: list[tuple[str, str]] = []
    for cid, gold in labels.items():
        pred = preds.get(cid)
        if pred is None:
            continue
        flags = set(gold["risk_flags"].split("|")) - {""}
        if gold["adjudication"] == "DENIED" and pred["adjudication"] == "NEEDS_REVIEW":
            if flags & DISQ:
                out.append((cid, "d2r_disq"))
        if (
            gold["adjudication"] == "NEEDS_REVIEW"
            and pred["adjudication"] == "APPROVED"
            and flags & REVIEW
        ):
            out.append((cid, "r2a_review"))
    return out


def _variants(im: Image.Image) -> dict[str, Image.Image]:
    gray = ImageOps.grayscale(im)
    return {
        "raw": gray,
        "auto": ImageOps.autocontrast(gray),
        "c5": ImageEnhance.Contrast(gray).enhance(5),
        "c8": ImageEnhance.Contrast(gray).enhance(8),
        "inv": ImageOps.invert(ImageOps.autocontrast(gray)),
        "sharp": ImageEnhance.Sharpness(ImageEnhance.Contrast(gray).enhance(4)).enhance(
            2
        ),
    }


def _ocr(path: Path) -> str:
    chunks: list[str] = []
    for psm in ("4", "6", "11"):
        try:
            cp = subprocess.run(
                ["tesseract", str(path), "stdout", "--psm", psm],
                capture_output=True,
                text=True,
                timeout=40,
                check=False,
            )
            chunks.append(cp.stdout or "")
        except (OSError, subprocess.TimeoutExpired):
            continue
    return "\n".join(chunks)


def hunt(cid: str, tag: str) -> list[dict]:
    pdf = pdfium.PdfDocument(str(ROOT / "data" / "train" / f"{cid}.pdf"))
    hits: list[dict] = []
    for page_index in range(len(pdf)):
        im = pdf[page_index].render(scale=3).to_pil().convert("RGB")
        for name, variant in _variants(im).items():
            path = OUT_DIR / f"ocr-{cid}-p{page_index}-{name}.png"
            variant.save(path)
            text = _ocr(path)
            found = [k for k in KEYWORDS if k in text.casefold()]
            if found:
                hits.append(
                    {
                        "case_id": cid,
                        "tag": tag,
                        "page": page_index,
                        "variant": name,
                        "hits": found,
                        "snippet": re.sub(r"\s+", " ", text)[:240],
                    }
                )
    return hits


def main() -> int:
    targets = _targets()
    done: set[str] = set()
    if HITS.exists():
        for line in HITS.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["case_id"])
    remaining = [(cid, tag) for cid, tag in targets if cid not in done]
    PROGRESS.write_text(
        json.dumps(
            {"total": len(targets), "done": len(done), "remaining": len(remaining)},
            indent=2,
        )
        + "\n"
    )
    print(f"stamp_hunter targets={len(targets)} remaining={len(remaining)}", flush=True)
    with HITS.open("a") as fh:
        for i, (cid, tag) in enumerate(remaining, 1):
            print(f"[{i}/{len(remaining)}] {cid} {tag}", flush=True)
            for hit in hunt(cid, tag):
                fh.write(json.dumps(hit) + "\n")
                fh.flush()
                print(" HIT", hit["hits"], hit["snippet"][:80], flush=True)
            done.add(cid)
            PROGRESS.write_text(
                json.dumps(
                    {
                        "total": len(targets),
                        "done": len(done),
                        "remaining": len(targets) - len(done),
                        "last": cid,
                    },
                    indent=2,
                )
                + "\n"
            )
    print("stamp_hunter DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
