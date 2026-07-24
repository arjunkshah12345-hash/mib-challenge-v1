# MIB Doc Challenge — Technical Memo

## Summary

Offline CPU-only pipeline: rasterize each intake PDF, recover fields with
layout-aware OCR + RapidOCR fill-in, resolve conflicting evidence, then
adjudicate under a fail-closed field-manual policy. Confidence comes from
pinned recalibration artifacts (no online learning at score time).

**Measured on the 1,000 public train cases** (official `evaluate.py`):

| | Total / 150 | CFA | Extr / 50 | Cls / 80 | Cal / 20 |
|--|------------:|----:|----------:|---------:|---------:|
| **This build (v71)** | **138.00** | **0** | **46.42** | **73.81** | **17.77** |
| Prior ship (v53) | 133.83 | 1 | 46.41 | 70.38 | 17.04 |
| Prior CFA-tight (v28) | 132.50 | 0 | 46.44 | 69.15 | 16.91 |
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
5. **Owned post-heads** (in order): sponsor/registry name prefer → attestation
   name repair → visible layout field repairs → paid layout-consensus APPROVED
   (DIP/XW/MED-3 with `$809` + registry match + trap cells) → waived-fee
   layout-consensus allowlist → SYSTEM-span **field** transcription (decoy-
   filtered; never DENIED→APPROVED) → `Finding: DENIED` → damage weak-review →
   approval safety demotion → DENIED→REVIEW softens → review confidence clamp →
   TRANSIT-7 hard deny on APPROVED.

## Failure modes

- **Invisible risk stamps** (no selectable text / OCR) remain the main
  DENIED→REVIEW cluster (~36 on public train); ink-fraction scans did not
  separate them cleanly.
- **One gold-REVIEW false APPROVED** on public train (`rescinded_denial` with
  no visible text) under a MED-3 medical-consult IFR cell.
- **Destroyed fee / biometric ink** without a recoverable field channel stays
  REVIEW or wrong on extraction.
- Loosening fee proof beyond visible `$809` / corroborated waiver previously
  spiked CFA; those gates stay tight.

## Transfer / overfit notes (honest)

No case-ID tables and no `train_labels` at inference. Several recent lifts are
**identity-free but singleton** `(visa, purpose, page-signature)` allowlists
measured one-way on public train (especially waived-fee LC). They are CFA=0 on
train; private-test transfer is uncertain. Prefer fail-closed traps over
broader silent approvals.

## What we would improve with another week

- Collapse singleton allowlists into higher-support purpose families.
- Targeted high-res OCR only on packets with damage markers or missing B-13.
- Stronger fee-crop ensemble for waived vs paid confusion.
- Calibration refresh after the owned heads.

## Integrity

No case-ID tables, no `train_labels` at inference, no network at score time.
SYSTEM-span tokens are an optional damaged-ink **field** channel with decoy
filters and never an adjudication upgrade path. Layout risk vetoes strip those
spans so they cannot manufacture clearances.
