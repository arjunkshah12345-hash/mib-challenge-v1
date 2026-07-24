# MIB document solution

Offline document extraction and adjudication for the
[MIB Doc Challenge](https://github.com/8090-inc/mib-doc-challenge).

Runtime vendors the public **strobl** render-first pipeline
(`mib_pipeline/`) with attribution in `ATTRIBUTION.md`. Local train
reproduction: **138.00 / 150**, **0** catastrophic false approvals.

## Pipeline

1. Rasterize every page (`pypdfium2`); embedded PDF text is diagnostic only
2. Tesseract sparse OCR with layout/label recovery + bounded retries
3. Independent RapidOCR fill for unresolved fields only
4. Evidence resolution (authority, strike-through, conflicts)
5. Identity-free adjudication + owned post-heads (layout consensus, softens, cal)
6. Pinned isotonic / output confidence recalibration

## Local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock  # or matching deps
PYTHONPATH=. MIB_MAX_WORKERS=4 python solution.py /path/to/pdfs /tmp/predictions.jsonl
```

## Docker (scoring contract)

```bash
docker build -t mib-solution .
docker run --rm \
  --network none \
  --cpus 4 \
  --memory 8g \
  --pids-limit 512 \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=2g \
  --mount type=bind,src=/path/to/pdfs,dst=/input,readonly \
  --mount type=bind,src=/path/to/output,dst=/output \
  mib-solution /input /output/predictions.jsonl
```

`MIB_MAX_WORKERS` defaults to `4` (scoring vCPU budget).
