#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test whether the 'Registry Status EMBARGO REVIEW' text field (rendered
page text, not a case-ID lookup) can safely demote NEEDS_REVIEW rows to
DENIED with planetary_embargo evidence, without hurting CFA / classification.

This is an ANALYSIS experiment: it scores with the official evaluate.py and
never writes over the shipped best.json unless it truly improves the score
with CFA == 0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "overnight_135"
BASE = OUT / "preds-rif_rofi_lc.jsonl"  # current best (134.5 CFA=0)
EVAL = Path("/Users/arjunkshah21/Downloads/mib-doc-challenge/scripts/evaluate.py")
LABELS = ROOT / "data" / "train_labels.csv"

sys.path.insert(0, str(ROOT))
import pypdfium2 as pdfium  # noqa: E402


def full_text(cid: str) -> str:
    pdf = pdfium.PdfDocument(str(ROOT / "data" / "train" / f"{cid}.pdf"))
    try:
        parts = []
        for i in range(len(pdf)):
            page = pdf[i]
            parts.append(page.get_textpage().get_text_range())
            page.close()
        return "\n".join(parts)
    finally:
        pdf.close()


def build_rows() -> list[dict]:
    rows = [json.loads(line) for line in BASE.read_text().splitlines()]
    n_touched = 0
    for row in rows:
        if row["adjudication"] != "NEEDS_REVIEW":
            continue
        text = full_text(row["case_id"])
        m = re.search(r"Registry Status\s+([A-Z][A-Z \-]*)", text)
        status = m.group(1).strip() if m else None
        if status and "EMBARGO" in status:
            n_touched += 1
            flags = set(row["risk_flags"].split("|")) - {"", "none"}
            flags.add("planetary_embargo")
            row["risk_flags"] = "|".join(sorted(flags))
            row["adjudication"] = "DENIED"
            row["confidence"] = 0.75
    print(f"touched {n_touched} rows", file=sys.stderr)
    return rows


def score(rows: list[dict], tag: str) -> dict:
    path = OUT / f"preds-{tag}.jsonl"
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    cp = subprocess.run(
        [sys.executable, str(EVAL), "--truth", str(LABELS), "--submission", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    result = {"tag": tag, "ok": cp.returncode == 0, "stdout": cp.stdout}
    for line in cp.stdout.splitlines():
        if "Deterministic score:" in line:
            result["score"] = float(line.split(":")[1].strip().split()[0])
        if "Catastrophic false approvals:" in line:
            result["cfa"] = int(line.split(":")[1].strip())
        if "Field extraction:" in line:
            result["extraction"] = line.split(":")[1].strip()
        if "Classification:" in line:
            result["classification"] = line.split(":")[1].strip()
        if "Calibration:" in line:
            result["calibration"] = line.split(":")[1].strip()
    return result


def main() -> int:
    rows = build_rows()
    result = score(rows, "embargo_status_demote")
    print(json.dumps(result, indent=2))
    with (OUT / "leaderboard.jsonl").open("a") as fh:
        fh.write(json.dumps(result) + "\n")

    best_path = OUT / "best.json"
    best = json.loads(best_path.read_text()) if best_path.exists() else {"score": 0.0, "cfa": 99}
    if result.get("cfa", 99) == 0 and result.get("score", 0) > best.get("score", 0):
        best = {
            "score": result["score"],
            "cfa": 0,
            "tag": "embargo_status_demote",
            "extraction": result.get("extraction"),
            "classification": result.get("classification"),
            "calibration": result.get("calibration"),
        }
        best_path.write_text(json.dumps(best, indent=2) + "\n")
        print("NEW BEST", best)
    else:
        print("NOT AN IMPROVEMENT - best.json left unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
