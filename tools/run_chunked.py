#!/usr/bin/env python3
"""Checkpointed train/val inference runner for mib-challenge-v1."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from solution import main  # noqa: E402


def _load_done(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            done.add(json.loads(line)["case_id"])
    return done


def run(input_dir: Path, output_path: Path, chunk_size: int = 50) -> int:
    pdfs = sorted(input_dir.glob("MIB-*.pdf"))
    done = _load_done(output_path)
    remaining = [pdf for pdf in pdfs if pdf.stem not in done]
    print(
        f"resume_done={len(done)} remaining={len(remaining)} chunk={chunk_size}",
        flush=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for offset in range(0, len(remaining), chunk_size):
        chunk = remaining[offset : offset + chunk_size]
        first = chunk[0].stem
        last = chunk[-1].stem
        print(
            f"chunk_start={offset:04d} n={len(chunk)} first={first} last={last}",
            flush=True,
        )
        with tempfile.TemporaryDirectory(prefix="mibchunk-") as tmp:
            tmp_in = Path(tmp) / "in"
            tmp_in.mkdir()
            for pdf in chunk:
                (tmp_in / pdf.name).symlink_to(pdf.resolve())
            tmp_out = Path(tmp) / "out.jsonl"
            code = main(["s", str(tmp_in), str(tmp_out)])
            if code != 0 or not tmp_out.exists():
                print(f"chunk_fail={offset:04d} code={code}", flush=True)
                return 1
            produced = [
                line for line in tmp_out.read_text().splitlines() if line.strip()
            ]
            if len(produced) != len(chunk):
                print(
                    f"chunk_incomplete={offset:04d} got={len(produced)} "
                    f"want={len(chunk)} - will retry remaining next resume",
                    flush=True,
                )
            with output_path.open("a") as out_handle:
                for line in produced:
                    out_handle.write(line + "\n")
            done.update(json.loads(line)["case_id"] for line in produced)
            print(
                f"chunk_done={offset:04d} wrote={len(produced)} "
                f"total={len(done)}/{len(pdfs)}",
                flush=True,
            )
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        print(
            "usage: run_chunked.py INPUT_DIR OUTPUT.jsonl [CHUNK]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    chunk = int(sys.argv[3]) if len(sys.argv) == 4 else 50
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2]), chunk))
