from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from mib.worker import predict_one


CASE_ID = re.compile(r"^MIB-\d{6}$")


def baseline_prediction(pdf: Path) -> dict[str, object]:
    """Return a schema-valid conservative baseline prediction."""
    case_id = pdf.stem.upper()
    if not CASE_ID.fullmatch(case_id):
        raise ValueError(f"cannot derive a valid case ID from {pdf.name}")

    return {
        "case_id": case_id,
        "applicant_name": "unknown",
        "species_code": "unknown",
        "home_world": "unknown",
        "visa_class": "unknown",
        "sponsor_id": "SPN-0000",
        "arrival_date": "1900-01-01",
        "declared_purpose": "unknown",
        "risk_flags": "none",
        "fee_status": "unknown",
        "adjudication": "NEEDS_REVIEW",
        "confidence": 0.28,
    }


def _write_predictions(path: Path, predictions: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def process_directory(input_dir: Path, output_path: Path, workers: int = 1) -> int:
    pdfs = sorted(p for p in input_dir.glob("*.pdf") if not p.name.startswith("._"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    predictions: list[dict[str, object]] = []
    total = len(pdfs)
    if workers <= 1:
        for index, pdf in enumerate(pdfs, start=1):
            predictions.append(predict_one(pdf))
            if index == 1 or index % 10 == 0 or index == total:
                print(f"progress={index}/{total}", flush=True)
            if index % 50 == 0:
                _write_predictions(output_path, predictions)
    else:
        # spawn + as_completed: avoid ONNX fork deadlocks and ordered-map stalls
        # where one slow PDF hides throughput from other workers.
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as executor:
            futures = {executor.submit(predict_one, pdf): pdf for pdf in pdfs}
            done = 0
            for future in as_completed(futures):
                pdf = futures[future]
                try:
                    prediction = future.result()
                except Exception:
                    prediction = baseline_prediction(pdf)
                predictions.append(prediction)
                done += 1
                if done == 1 or done % 10 == 0 or done == total:
                    print(f"progress={done}/{total}", flush=True)
                if done % 50 == 0:
                    # Checkpoint unsorted; final write sorts by case_id.
                    _write_predictions(output_path, predictions)

    predictions.sort(key=lambda row: str(row.get("case_id", "")))
    _write_predictions(output_path, predictions)
    return len(predictions)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("MIB_WORKERS", "4")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"input directory does not exist: {args.input_dir}")
    written = process_directory(args.input_dir, args.output_path, max(1, args.workers))
    print(f"wrote={written}")


if __name__ == "__main__":
    main()
