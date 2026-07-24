# Solution repository

Public solution repository (must include a `Dockerfile`):

**https://github.com/arjunkshah12345-hash/mib-challenge-v1**

## Run contract

```bash
docker build -t mib-submission .
docker run --rm --network none \
  --cpus 4 --memory 8g --pids-limit 512 --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=2g \
  --mount type=bind,source=/path/to/pdfs,destination=/input,readonly \
  --mount type=bind,source=/path/to/output,destination=/output \
  mib-submission /input /output/predictions.jsonl
```

Entrypoint accepts exactly two arguments: input PDF directory and output
predictions path (JSONL). Image includes Tesseract + `poppler-utils`.

## Local train score (reference)

Measured **138.06 / 150** on public train (**CFA = 0**, v79 transfer-scrubbed). See `MEMO.md`.
Breakdown: extraction 46.42 · classification 73.74 · calibration 17.91.
Singleton softens / magic conf bands from v77–v78 were removed (one was a false soften).

## Validation package (this repo)

```bash
# Full 5k inference (resumable shards) → artifacts/predictions-validation-v79.jsonl
./tools/run_validation_v79.sh

# Deduplicate, official validate_submission.py, local package only:
./tools/finalize_submission_package.sh
# → artifacts/submission-package/{predictions.jsonl,MEMO.md,SUBMISSION.md}
```

GitHub username for the form: `arjunkshah12345-hash`.
Challenge-repo PR and Google form are separate steps (not automated here).
