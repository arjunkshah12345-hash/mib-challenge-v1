# MIB Doc Challenge — Technical Memo

## Summary

Offline CPU-only pipeline: rasterize each intake PDF, recover fields with
layout-aware OCR + RapidOCR fill-in, resolve conflicting evidence, then
adjudicate under a fail-closed field-manual policy. Confidence comes from
pinned recalibration artifacts (no online learning at score time).

**Measured on the 1,000 public train cases** (official `evaluate.py`):

| | Total / 150 | CFA | Extr / 50 | Cls / 80 | Cal / 20 |
|--|------------:|----:|----------:|---------:|---------:|
| **This build (v53)** | **133.83** | **1** | **46.41** | **70.38** | **17.04** |
| Prior ship (v28, CFA-tight) | 132.50 | 0 | 46.44 | 69.15 | 16.91 |
| strobl baseline (our re-run) | 130.26 | 0 | 44.84 | 68.44 | 16.97 |

Runtime target: ≤6 s/PDF average on 4 vCPU / 8 GiB with 4 workers. Image stays
under the 4 GiB limit. Scoring image installs Tesseract + `poppler-utils`
(`pdftotext`) so layout heads match local measurement.

## Approach

Vendors strobl’s public MIT render-first stack with attribution, then adds
owned recovery layers (identity-free; no train-label / case-ID unlocks):

1. **Rasterize** with pypdfium2. Embedded PDF text never overrides visible OCR
   for adjudication features.
2. **Tesseract** sparse OCR with layout/label recovery and bounded retries.
3. **RapidOCR** fills primary `UNKNOWN` fields only — never a second vote over
   already-resolved values.
4. **Evidence resolution** + deterministic policy (fail closed on silent
   `risk=none`).
5. **Owned post-heads** (in order): sponsor/registry name prefer → visible
   layout field repairs → layout-consensus APPROVED (DIP/XW + visible `$809` +
   registry==applicant) → SYSTEM-span **field** transcription with planted-decoy
   filters and fail-closed demotion (never DENIED→APPROVED) → explicit
   `Finding: DENIED` → damage weak-review (`UNREADABLE`/`REDACTED` → REVIEW) →
   safety demotion + TRANSIT-7 hard deny.

## Failure modes

- **Invisible risk stamps** (no selectable text / OCR) can still produce a
  false APPROVED; one residual CFA remains on public train.
- **Destroyed fee / biometric ink** without a recoverable SYSTEM span stays
  REVIEW or wrong on extraction.
- **MED-3** over-review when biohazard cells are missing — we refuse silent
  clearance (blanket MED-3 approve spiked CFA in ablation).
- Loosening fee proof beyond visible `$809` / corroborated waiver previously
  spiked CFA; those gates stay tight.

## What we would improve with another week

- Targeted high-res / multi-preprocess OCR only on packets with damage markers
  or missing B-13 rows (without blowing the 6 s/PDF budget).
- Stronger fee-crop ensemble for waived vs paid confusion.
- Calibration refresh after the owned heads (small Brier headroom remains).
- Private-test stress on whether SYSTEM-span field recovery remains present;
  keep fail-closed demotion regardless.

## Integrity

No case-ID tables, no `train_labels` at inference, no network at score time.
SYSTEM-span tokens are treated as an optional damaged-ink field channel with
decoy filters and never as an adjudication upgrade path. Layout risk vetoes
strip those spans so they cannot manufacture clearances.
