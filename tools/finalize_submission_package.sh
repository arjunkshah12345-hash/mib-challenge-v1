#!/usr/bin/env bash
# Package v79 validation predictions locally under mib-challenge-v1.
# Does NOT write into mib-doc-challenge/submissions or open a PR.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/artifacts/submission-package"
VAL_RAW="${VAL_RAW:-$ROOT/artifacts/predictions-validation-v79.jsonl}"
VAL_FINAL="$ROOT/artifacts/predictions-validation-v79.jsonl"
MANIFEST="${MANIFEST:-/Users/arjunkshah21/Downloads/mib-doc-challenge/data/validation_manifest.csv}"
VALIDATE="${VALIDATE:-/Users/arjunkshah21/Downloads/mib-doc-challenge/scripts/validate_submission.py}"

cd "$ROOT"
while true; do
  if [[ ! -f "$VAL_RAW" ]]; then
    echo "$(date -Iseconds) waiting for $VAL_RAW"
    sleep 60
    continue
  fi
  n="$(wc -l < "$VAL_RAW" | tr -d ' ')"
  echo "$(date -Iseconds) val_lines=$n"
  if [[ "$n" -ge 5000 ]]; then
    break
  fi
  sleep 120
done

# Deduplicate by case_id (keep last)
VAL_RAW="$VAL_RAW" VAL_FINAL="$VAL_FINAL" .venv/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

raw = Path(os.environ["VAL_RAW"])
final = Path(os.environ["VAL_FINAL"])
by = {}
for line in raw.read_text().splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    by[row["case_id"]] = line
lines = [by[k] for k in sorted(by)]
final.write_text("\n".join(lines) + "\n")
print(f"unique={len(lines)}")
if len(lines) != 5000:
    raise SystemExit(f"expected 5000 unique case ids, got {len(lines)}")
PY

.venv/bin/python3 "$VALIDATE" \
  --submission "$VAL_FINAL" \
  --manifest "$MANIFEST" \
  --require-complete | tee artifacts/validate-val-v79.txt

mkdir -p "$PKG"
cp "$VAL_FINAL" "$PKG/predictions.jsonl"
cp "$ROOT/MEMO.md" "$PKG/MEMO.md"
cp "$ROOT/SUBMISSION.md" "$PKG/SUBMISSION.md"
cp "$ROOT/TRANSFER_AUDIT.md" "$PKG/TRANSFER_AUDIT.md" 2>/dev/null || true
cp artifacts/validate-val-v79.txt "$PKG/validate-val-v79.txt"

sha="$(shasum -a 256 "$PKG/predictions.jsonl" | awk '{print $1}')"
echo "predictions_sha256=$sha" | tee artifacts/val-v79-sha.txt
echo "$sha" > "$PKG/predictions.sha256"
echo "FINALIZE_DONE package=$PKG"
