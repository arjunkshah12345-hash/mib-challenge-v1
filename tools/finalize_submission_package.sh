#!/usr/bin/env bash
# Finalize validation predictions + submissions package when val hits 5000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHALLENGE_SUBMISSIONS="/Users/arjunkshah21/Downloads/mib-doc-challenge/submissions/arjunkshah12345-hash"
VAL_RAW="$ROOT/artifacts/predictions-validation-v36.jsonl"
VAL_FINAL="$ROOT/artifacts/predictions-validation-v53.jsonl"
MANIFEST="/Users/arjunkshah21/Downloads/mib-doc-challenge/data/validation_manifest.csv"
PDF_DIR="$ROOT/data/validation"

cd "$ROOT"
while true; do
  n="$(wc -l < "$VAL_RAW" | tr -d ' ')"
  echo "$(date -Iseconds) val_lines=$n"
  if [[ "$n" -ge 5000 ]]; then
    break
  fi
  sleep 120
done

# Deduplicate by case_id (keep last)
.venv/bin/python3 - <<'PY'
import json
from pathlib import Path
path = Path("artifacts/predictions-validation-v36.jsonl")
by = {}
for line in path.read_text().splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    by[row["case_id"]] = line
lines = [by[k] for k in sorted(by)]
path.write_text("\n".join(lines) + "\n")
print(f"unique={len(lines)}")
PY

.venv/bin/python3 tools/postprocess_owned_heads.py \
  "$PDF_DIR" "$VAL_RAW" "$VAL_FINAL"

.venv/bin/python3 /Users/arjunkshah21/Downloads/mib-doc-challenge/scripts/validate_submission.py \
  --submission "$VAL_FINAL" \
  --manifest "$MANIFEST" \
  --require-complete | tee artifacts/validate-val-v53.txt

cp "$VAL_FINAL" "$CHALLENGE_SUBMISSIONS/predictions.jsonl"
cp "$ROOT/MEMO.md" "$CHALLENGE_SUBMISSIONS/MEMO.md"
cp "$ROOT/SUBMISSION.md" "$CHALLENGE_SUBMISSIONS/SUBMISSION.md"

# Prefer the challenge-folder SUBMISSION.md with form link
cat > "$CHALLENGE_SUBMISSIONS/SUBMISSION.md" << 'EOF'
# Submission

- GitHub username: `arjunkshah12345-hash`
- Public solution repository: https://github.com/arjunkshah12345-hash/mib-challenge-v1
- Mandatory Dockerfile: https://github.com/arjunkshah12345-hash/mib-challenge-v1/blob/main/Dockerfile

Ship build **v53**: locked public-train score **133.83 / 150**, **CFA = 1**
(extraction 46.41, classification 70.38, calibration 17.04). Approach,
failure modes, and next-week plan are in `MEMO.md`.

Validation predictions in this PR: **5,000 / 5,000** records, official
validator clean (see repo `artifacts/validate-val-v53.txt` after finalize).

The solution repository contains the complete offline runtime (Tesseract +
RapidOCR + `poppler-utils`), hashed `requirements.lock`, and pinned
recalibration artifacts. This challenge entry is complete only when this pull
request targets the official repository's `main` branch **and** the mandatory
submission form has also been completed:

https://docs.google.com/forms/d/1ZLkHmTsYd9I87JL1sUyps2rPTe6ohEI_lTZ8Jjts6bw/viewform
EOF

sha="$(shasum -a 256 "$CHALLENGE_SUBMISSIONS/predictions.jsonl" | awk '{print $1}')"
echo "predictions_sha256=$sha" | tee artifacts/val-v53-sha.txt
echo "FINALIZE_DONE"
