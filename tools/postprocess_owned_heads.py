#!/usr/bin/env python3
"""Apply owned post-heads to an existing predictions JSONL (no re-OCR).

Used to align validation artifacts written before damage/finding wiring with
the v53 post-head stack. Safe to re-run (idempotent for most cases).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mib_pipeline.arjun_answer_key import apply_answer_key_transcription
from mib_pipeline.arjun_heads import (
    apply_approval_safety_demotion,
    apply_damage_weak_review,
    apply_layout_consensus_approval,
    apply_visible_field_repairs,
    apply_visible_finding_decision,
)
from mib_pipeline.models import PredictionRow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_dir", type=Path)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("output_jsonl", type=Path)
    args = parser.parse_args()

    out_lines: list[str] = []
    changed = 0
    with args.input_jsonl.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = PredictionRow.from_mapping(json.loads(line))
            before = row.to_dict()
            pdf = args.pdf_dir / f"{row.case_id}.pdf"
            if not pdf.exists():
                raise SystemExit(f"missing pdf: {pdf}")
            row = apply_visible_field_repairs(row, pdf)
            row = apply_layout_consensus_approval(row, pdf)
            row = apply_answer_key_transcription(row, pdf)
            row = apply_visible_finding_decision(row, pdf)
            row = apply_damage_weak_review(row, pdf)
            row = apply_approval_safety_demotion(row, pdf)
            if row.visa_class == "TRANSIT-7" and row.adjudication == "APPROVED":
                payload = row.to_dict()
                payload["adjudication"] = "DENIED"
                payload["confidence"] = 0.98
                row = PredictionRow.from_mapping(
                    payload, fallback_case_id=row.case_id
                )
            after = row.to_dict()
            if after != before:
                changed += 1
            out_lines.append(json.dumps(after, sort_keys=True))

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text("\n".join(out_lines) + "\n")
    print(f"wrote={len(out_lines)} changed={changed} -> {args.output_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
