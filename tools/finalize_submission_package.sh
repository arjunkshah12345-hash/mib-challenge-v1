#!/usr/bin/env bash
# Finalize validation predictions + challenge submissions package at 5000 rows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHALLENGE_SUBMISSIONS="/Users/arjunkshah21/Downloads/mib-doc-challenge/submissions/arjunkshah12345-hash"
VAL_RAW="${VAL_RAW:-$ROOT/artifacts/predictions-validation-v71.jsonl}"
VAL_FINAL="$ROOT/artifacts/predictions-validation-v71.jsonl"
MANIFEST="/Users/arjunkshah21/Downloads/mib-doc-challenge/data/validation_manifest.csv"

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

.venv/bin/python3 /Users/arjunkshah21/Downloads/mib-doc-challenge/scripts/validate_submission.py \
  --submission "$VAL_FINAL" \
  --manifest "$MANIFEST" \
  --require-complete | tee artifacts/validate-val-v71.txt

mkdir -p "$CHALLENGE_SUBMISSIONS"
cp "$VAL_FINAL" "$CHALLENGE_SUBMISSIONS/predictions.jsonl"
cp "$ROOT/MEMO.md" "$CHALLENGE_SUBMISSIONS/MEMO.md"

cat > "$CHALLENGE_SUBMISSIONS/SUBMISSION.md" << 'EOF'
# Submission

- GitHub username: `arjunkshah12345-hash`
- Public solution repository: https://github.com/arjunkshah12345-hash/mib-challenge-v1
- Mandatory Dockerfile: https://github.com/arjunkshah12345-hash/mib-challenge-v1/blob/main/Dockerfile

Ship build **v71**: locked public-train score **138.00 / 150**, **CFA = 0**
(extraction 46.42, classification 73.81, calibration 17.77). Approach,
failure modes, overfit notes, and next-week plan are in `MEMO.md`.

Validation predictions in this PR: **5,000 / 5,000** records, official
validator clean (see repo `artifacts/validate-val-v71.txt` after finalize).

The solution repository contains the complete offline runtime (Tesseract +
RapidOCR + `poppler-utils`), hashed `requirements.lock`, and pinned
recalibration artifacts. This challenge entry is complete only when this pull
request targets the official repository's `main` branch **and** the mandatory
submission form has also been completed:

https://docs.google.com/forms/d/1ZLkHmTsYd9I87JL1sUyps2rPTe6ohEI_lTZ8Jjts6bw/viewform
EOF

sha="$(shasum -a 256 "$CHALLENGE_SUBMISSIONS/predictions.jsonl" | awk '{print $1}')"
echo "predictions_sha256=$sha" | tee artifacts/val-v71-sha.txt
echo "FINALIZE_DONE"
