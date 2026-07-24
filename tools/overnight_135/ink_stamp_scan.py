#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan every train PDF for colored 'ink stamp' pixels (red/purple rubber
stamps like COPY/MIB/FILED) and correlate presence with gold risk flags.

Analysis-only script: reads train_labels.csv purely to VALIDATE whether a
transfer-safe visual signal exists. It does not feed labels into any
detector used at inference time.

Writes artifacts/overnight_135/ink_stamp_scan.jsonl (per-case ink stats) and
prints a correlation summary against risk_flags / adjudication.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

OUT = ROOT / "artifacts" / "overnight_135" / "ink_stamp_scan.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)


def red_ink_fraction(arr: np.ndarray) -> tuple[float, float]:
    """Fraction of pixels that look like red rubber-stamp ink vs purple ink.

    Red ink: R substantially higher than G and B, and G,B close to each
    other (rules out warm skin-tone photo pixels which usually have
    G > B by a fair margin, and rules out anti-aliased black text edges).
    Purple ink: R and B elevated vs G, roughly balanced R/B.
    """

    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)

    red_mask = (r - g > 40) & (r - b > 40) & (np.abs(g - b) < 25) & (r > 120)
    purple_mask = (r - g > 25) & (b - g > 25) & (np.abs(r - b) < 40) & (r > 90) & (b > 90)

    n = arr.shape[0] * arr.shape[1]
    return float(red_mask.sum()) / n, float(purple_mask.sum()) / n


def scan_case(cid: str) -> dict:
    path = ROOT / "data" / "train" / f"{cid}.pdf"
    pdf = pdfium.PdfDocument(str(path))
    red_max = 0.0
    purple_max = 0.0
    n_pages = len(pdf)
    try:
        for i in range(n_pages):
            page = pdf[i]
            bitmap = page.render(scale=2)
            im = bitmap.to_pil().convert("RGB")
            arr = np.array(im)
            red_f, purple_f = red_ink_fraction(arr)
            red_max = max(red_max, red_f)
            purple_max = max(purple_max, purple_f)
            del bitmap
            im.close()
            page.close()
    finally:
        pdf.close()
    return {
        "case_id": cid,
        "pages": n_pages,
        "red_ink_frac": round(red_max, 6),
        "purple_ink_frac": round(purple_max, 6),
    }


def main() -> int:
    labels = {
        r["case_id"]: r
        for r in csv.DictReader((ROOT / "data" / "train_labels.csv").open())
    }
    cases = sorted(labels)
    done: dict[str, dict] = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["case_id"]] = rec
    with OUT.open("a") as fh:
        for i, cid in enumerate(cases, 1):
            if cid in done:
                continue
            rec = scan_case(cid)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[cid] = rec
            if i % 50 == 0:
                print(f"[{i}/{len(cases)}] {cid}", flush=True)
    print("SCAN DONE", len(done), flush=True)

    # Correlation summary.
    RED_THRESH = 0.0008
    PURPLE_THRESH = 0.0004
    DISQ = {"memory_tampering", "planetary_embargo", "active_warrant", "biohazard_red"}
    buckets: dict[str, list[int]] = {
        "disq_flag": [],
        "any_risk_flag": [],
        "no_risk_flag": [],
    }
    for cid, rec in done.items():
        gold = labels.get(cid)
        if not gold:
            continue
        flags = set(gold["risk_flags"].split("|")) - {"", "none"}
        has_ink = 1 if (rec["red_ink_frac"] > RED_THRESH or rec["purple_ink_frac"] > PURPLE_THRESH) else 0
        if flags & DISQ:
            buckets["disq_flag"].append(has_ink)
        elif flags:
            buckets["any_risk_flag"].append(has_ink)
        else:
            buckets["no_risk_flag"].append(has_ink)

    print("\n=== Ink-stamp presence rate by label bucket ===")
    for name, vals in buckets.items():
        if vals:
            rate = sum(vals) / len(vals)
            print(f"{name}: n={len(vals)} ink_rate={rate:.3f}")
        else:
            print(f"{name}: n=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
