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

Entrypoint accepts exactly two arguments: input PDF directory and output predictions path (JSONL).

## Local train score (reference)

Measured **133.83 / 150** on public train (**CFA = 1**). Includes visible field
repairs, fail-closed SYSTEM-span field transcription, and damage weak-review
(`UNREADABLE`/`REDACTED` → REVIEW). See `MEMO.md`.
