#!/usr/bin/env bash
# Durable v79 validation runner for mib-challenge-v1 only.
set -euo pipefail
ROOT="/Users/arjunkshah21/Downloads/mib-challenge-v1"
OUT="$ROOT/artifacts/val-v79-shards"
LOG="$ROOT/artifacts/val-v79-run.log"
FINAL="$ROOT/artifacts/predictions-validation-v79.jsonl"
PY="$ROOT/.venv/bin/python"
export MIB_MAX_WORKERS="${MIB_MAX_WORKERS:-2}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT"
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2

mkdir -p "$OUT" "$ROOT/artifacts"
echo "SUPERVISOR_START $(date -Iseconds) workers=$MIB_MAX_WORKERS" | tee -a "$LOG"

"$PY" - <<'PY'
from pathlib import Path
root = Path("/Users/arjunkshah21/Downloads/mib-challenge-v1")
val = root / "data" / "validation"
out = root / "artifacts" / "val-v79-shards"
pdfs = sorted(val.glob("MIB-*.pdf"))
assert len(pdfs) == 5000, len(pdfs)
for i in range(5):
    d = out / f"in-{i:02d}"
    d.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in d.glob("MIB-*.pdf")}
    chunk = pdfs[i * 1000 : (i + 1) * 1000]
    wanted = {p.name for p in chunk}
    if existing != wanted:
        for old in d.glob("MIB-*.pdf"):
            old.unlink()
        for p in chunk:
            (d / p.name).symlink_to(p.absolute())
    print(f"shard {i:02d}: {len(chunk)} pdfs")
PY

for i in 0 1 2 3 4; do
  ii="$(printf '%02d' "$i")"
  pred="$OUT/preds-${ii}.jsonl"
  slog="$OUT/shard${ii}.log"
  if [[ -f "$pred" ]] && [[ "$(wc -l < "$pred" | tr -d ' ')" == "1000" ]]; then
    echo "skip shard $ii already complete $(date -Iseconds)" | tee -a "$LOG"
    continue
  fi
  rm -f "$pred"
  echo "START shard $ii $(date -Iseconds)" | tee -a "$LOG"
  # Heartbeat file so we can monitor without incremental JSONL writes.
  : > "$OUT/heartbeat-${ii}.txt"
  (
    while true; do
      date -Iseconds > "$OUT/heartbeat-${ii}.txt"
      sleep 30
    done
  ) &
  hb=$!
  set +e
  "$PY" -I -B "$ROOT/solution.py" "$OUT/in-${ii}" "$pred" >"$slog" 2>&1
  rc=$?
  set -e
  kill "$hb" 2>/dev/null || true
  wait "$hb" 2>/dev/null || true
  lines=0
  [[ -f "$pred" ]] && lines="$(wc -l < "$pred" | tr -d ' ')"
  echo "DONE shard $ii rc=$rc lines=$lines $(date -Iseconds)" | tee -a "$LOG"
  tail -20 "$slog" | tee -a "$LOG" || true
  if [[ "$rc" != "0" ]] || [[ "$lines" != "1000" ]]; then
    echo "error: shard $ii failed rc=$rc lines=$lines" | tee -a "$LOG"
    exit 1
  fi
done

cat "$OUT"/preds-00.jsonl "$OUT"/preds-01.jsonl "$OUT"/preds-02.jsonl \
    "$OUT"/preds-03.jsonl "$OUT"/preds-04.jsonl > "$FINAL"
echo "MERGED lines=$(wc -l < "$FINAL" | tr -d ' ') -> $FINAL" | tee -a "$LOG"
"$ROOT/tools/finalize_submission_package.sh" 2>&1 | tee -a "$LOG"
echo "SUPERVISOR_DONE $(date -Iseconds)" | tee -a "$LOG"
