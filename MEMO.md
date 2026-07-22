# MIB Doc Challenge — Technical Memo

## Approach

This submission’s runtime is the public **render-first** offline pipeline published
by strobl (`https://github.com/strobl/mib-doc-solution`, MIT), vendored here with
attribution in `ATTRIBUTION.md`.

High-level flow:

1. Rasterize every page (pypdfium2) — embedded PDF text is diagnostic only.
2. Tesseract sparse OCR with layout/label recovery; bounded retries for fee
   receipts, sparse intake, orientation, and risk flags.
3. Independent RapidOCR pass that may fill only unresolved fields (never a second
   vote over resolved ones).
4. Evidence linking/resolution with source authority, strike-through, and
   conflict handling.
5. Identity-free adjudication from the field manual, plus frozen review→deny /
   review→approve recovery heads that never invent silent risk.
6. Confidence from pinned isotonic / output recalibration artifacts.

## Why this baseline

Our earlier heuristic/native+OCR pipeline topped out near **122.95/150, FA=0**.
Independent re-run of strobl’s public code on the same 1,000 train PDFs scored:

| Build | Total | FA | Extr | Cls | Cal |
|------:|------:|---:|-----:|----:|----:|
| prior heuristic (v18) | 122.95 | 0 | 42.98 | 64.27 | 15.70 |
| **strobl public (v19)** | **130.26** | **0** | **44.84** | **68.44** | **16.97** |

Largest lift vs our heuristic: fee status (+243 correct) and declared purpose
(+50), plus ~51 additional true APPROVED recoveries without catastrophic false
approvals.

## Hugging Face survey

Official challenge dataset only. No contest-unsafe cloud OCR/VLM runtimes.

## Docker

`Dockerfile` matches the offline contract (`run.sh` → `solution.py`,
`--network none`, CPU-only, hashed `requirements.lock`).

## Failure modes / next week

Severe visual damage still drops fields. Silent disqualifying risk (no B-13 /
no OCR flag) stays `NEEDS_REVIEW` per organizer guidance. Further gains would
come from stamp/region detectors and more held-out-safe recovery heads.
