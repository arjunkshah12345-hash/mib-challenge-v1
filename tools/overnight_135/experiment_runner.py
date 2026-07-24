#!/usr/bin/env python3
"""Measured overnight experiment runner with CFA hard-fail.

Applies post-hoc demotion / LC simulations against the current best preds,
scores with official evaluate.py, appends to leaderboard.jsonl. Rejects CFA>0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mib_pipeline.arjun_heads import (  # noqa: E402
    DEMOTION_REVIEW_CONFIDENCE,
    _layout_page_signature,
    _pdf_layout_text,
    apply_approval_safety_demotion,
    apply_layout_consensus_approval,
)
from mib_pipeline.models import PredictionRow  # noqa: E402

OUT = ROOT / "artifacts" / "overnight_135"
OUT.mkdir(parents=True, exist_ok=True)
LEADERBOARD = OUT / "leaderboard.jsonl"
# Current measured best (LC traps + fee-unknown + filler demotion).
BASE = ROOT / "artifacts" / "predictions-train-v79.jsonl"
EVAL = Path("/Users/arjunkshah21/Downloads/mib-doc-challenge/scripts/evaluate.py")
LABELS = ROOT / "data" / "train_labels.csv"


def _score(rows: list[dict], tag: str) -> dict:
    path = OUT / f"preds-{tag}.jsonl"
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    cp = subprocess.run(
        [
            sys.executable,
            str(EVAL),
            "--truth",
            str(LABELS),
            "--submission",
            str(path),
        ],
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


def _baseline_rows() -> list[dict]:
    return [json.loads(line) for line in BASE.read_text().splitlines()]


def exp_baseline_verify() -> list[dict]:
    return _baseline_rows()


def exp_demote_conf08_oboro_pattern() -> list[dict]:
    """Demote REVIEW_APPROVAL (conf?0.8) with ?3 non-core pages - measured probe."""

    rows: list[dict] = []
    for pred in _baseline_rows():
        row = dict(pred)
        if (
            row["adjudication"] == "APPROVED"
            and abs(float(row["confidence"]) - 0.8) < 1e-6
        ):
            text = _pdf_layout_text(ROOT / "data" / "train" / f"{row['case_id']}.pdf")
            sig = _layout_page_signature(text or "")
            if sig.count("O") >= 3:
                row["adjudication"] = "NEEDS_REVIEW"
                row["confidence"] = DEMOTION_REVIEW_CONFIDENCE
        rows.append(row)
    return rows


def exp_demote_approved_unpaid() -> list[dict]:
    """Probe: demote APPROVED with fee_status unpaid (may hurt true unpaid A)."""

    rows: list[dict] = []
    for pred in _baseline_rows():
        row = dict(pred)
        if row["adjudication"] == "APPROVED" and row["fee_status"] == "unpaid":
            row["adjudication"] = "NEEDS_REVIEW"
            row["confidence"] = DEMOTION_REVIEW_CONFIDENCE
        rows.append(row)
    return rows


def exp_lower_overconf_denied() -> list[dict]:
    """Calibration: clamp DENIED confidence to ?0.92 when risk_flags is none."""

    rows: list[dict] = []
    for pred in _baseline_rows():
        row = dict(pred)
        if (
            row["adjudication"] == "DENIED"
            and str(row.get("risk_flags", "none")).casefold() == "none"
            and float(row["confidence"]) > 0.92
        ):
            row["confidence"] = 0.92
        rows.append(row)
    return rows


def exp_reapply_heads() -> list[dict]:
    """Re-run LC + safety demotion on every row (sanity / regression)."""

    rows: list[dict] = []
    for pred in _baseline_rows():
        row = dict(pred)
        if row["adjudication"] == "APPROVED" and abs(float(row["confidence"]) - 0.85) < 1e-9:
            row["adjudication"] = "NEEDS_REVIEW"
        typed = PredictionRow.from_mapping(row, fallback_case_id=row["case_id"])
        pdf = ROOT / "data" / "train" / f"{row['case_id']}.pdf"
        typed = apply_layout_consensus_approval(typed, pdf)
        typed = apply_approval_safety_demotion(typed, pdf)
        rows.append(typed.to_dict())
    return rows


EXPERIMENTS = {
    "v63_verify": exp_baseline_verify,
    "demote_conf08_O3": exp_demote_conf08_oboro_pattern,
    "demote_unpaid": exp_demote_approved_unpaid,
    "cal_denied_none_cap": exp_lower_overconf_denied,
    "reapply_heads": exp_reapply_heads,
}


def main() -> int:
    best_path = OUT / "best.json"
    best = {"score": 0.0, "cfa": 99, "tag": None}
    if best_path.exists():
        best = json.loads(best_path.read_text())

    for tag, fn in EXPERIMENTS.items():
        print(f"RUN {tag}", flush=True)
        rows = fn()
        result = _score(rows, tag)
        print(result.get("score"), "CFA", result.get("cfa"), flush=True)
        with LEADERBOARD.open("a") as fh:
            fh.write(json.dumps(result) + "\n")
        if result.get("cfa", 99) == 0 and result.get("score", 0) > best.get("score", 0):
            best = {
                "score": result["score"],
                "cfa": 0,
                "tag": tag,
                "extraction": result.get("extraction"),
                "classification": result.get("classification"),
                "calibration": result.get("calibration"),
            }
            best_path.write_text(json.dumps(best, indent=2) + "\n")
            print("NEW BEST", best, flush=True)
    print("BEST", best, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
