# MIB Doc Challenge — Technical Memo

## Summary

Offline CPU-only pipeline: rasterize each intake PDF, recover fields with
layout-aware OCR + RapidOCR fill-in, resolve conflicting evidence, then
adjudicate under a fail-closed field-manual policy. Confidence comes from
pinned recalibration artifacts (no online learning at score time).

**Measured on the 1,000 public train cases** (official `evaluate.py`):

| | Total / 150 | CFA | Extr / 50 | Cls / 80 | Cal / 20 |
|--|------------:|----:|----------:|---------:|---------:|
| **This build (v79, transfer-scrubbed)** | **138.06** | **0** | **46.42** | **73.74** | **17.91** |
| Prior peak (v78, pre-scrub) | 138.20 | 0 | 46.42 | 73.82 | 17.96 |
| Prior (v77) | 138.04 | 0 | 46.42 | 73.70 | 17.93 |
| Prior transfer-safe (v75) | 137.18 | 0 | 46.42 | 73.08 | 17.68 |
| Overfit peak (v71, not shipping) | 138.00 | 0 | 46.42 | 73.81 | 17.77 |
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
   (DIP/XW/MED-3 with `$809` + registry match + trap cells; MED-3 purpose
   family `research` / `translation` / `cultural exchange`, industrial
   `reactor maintenance` / `field repair` when Registry is not last among
   core I/R/F pages, and `medical consult` for MED-3/XW-2 under the same
   Registry-before-close gate) → waived-fee layout-consensus for DIP/XW mission
   purposes and XW/MED-3 industrial (same Registry-before-close gate) with
   RIF/FIR/O bans → layout trap DENIED (industrial Registry-last; non-approveable
   MED-3 purposes with Registry-before-close; XW-2 medical consult Registry-last)
   → SYSTEM-span **field** transcription (decoy-filtered; never
   DENIED→APPROVED) → `Finding: DENIED` → damage weak-review → approval safety
   demotion → DENIED→REVIEW softens → review confidence clamp → decision
   confidence floors (APPROVED/DENIED at 0.95) → TRANSIT-7 hard deny on APPROVED.

Paid/waived LC allow a **single trailing** non-core ``O`` page after form
pages; leading/mid/multi-``O`` and ``RIF`` (waived also ``FIR``) still fail closed.

## Failure modes

- **Invisible risk stamps** (no selectable text / OCR) remain the main
  DENIED→REVIEW cluster (~36 on public train) and block ~131 gold-risk cases
  that look like `risk=none` in layout.
- **Filler-heavy O-page packets** (~61 true APPROVED stuck in REVIEW): fee /
  registry text is missing from selectable layout; page-level Tesseract did
  not recover `$809` / registry names on a 20-case probe.
- Expanding MED-3 paid purposes without the Registry-before-close gate, or
  XW-1 medical consult under paid LC, collides with invisible biohazard /
  embargo cells — those stay closed.
- Loosening fee proof beyond visible `$809` / corroborated waiver previously
  spiked CFA; those gates stay tight.

## Transfer / overfit notes (honest)

## Transfer / overfit scrub (v79)

No case-ID tables and no `train_labels` at inference. **Stripped in v79**
(train-only / harmful on holdout):

| Removed | Why |
| --- | --- |
| Schema waived+illegible soften (`SPN-0000` + `1900-01-01`) | n=1 unlock |
| Synthetic-only weak deny + schema arrival soften | n=1 and **FP** (`MIB-000134` true DENIED→REVIEW) |
| DIP-1 waived confidence band `0.54–0.56` | magic band / dead n=1 |
| Trap-denial confidence ceilings (`≤0.15` / `≤0.30`) | train-conf tuning; structural gates suffice |

**Kept (fail-closed or multi-support):** purpose-family LC + Registry-before-close;
single trailing-``O`` allow; REVIEW→DENIED trap mirrors (industrial / unsafe
purpose / XW-2 MC); purpose traps + a few signature fail-closed cells (cannot
broaden to purpose without blocking true APPROVED); FRI+transit fail-closed;
0.95 decision confidence floors.

v78’s 138.20 included the FP soften — **not** the ship path. v79 is **138.06**
with CFA=0 and zero false softens on public train.

Full rule-by-rule support / ablation table: ``TRANSFER_AUDIT.md``.

Honest leaderboard expectation: **~137–138** if val matches train density of
invisible stamps / O-pages; further gains need stamp/fee OCR, not more cells.

## What we would improve with another week

- High-res fee-crop + B-13 stamp OCR targeted at O-page / missing-channel
  packets (the real path past ~138 without CFA).
- Stronger fee-crop ensemble for waived vs paid confusion.
- Calibration refresh after the owned heads.

## Integrity

No case-ID tables, no `train_labels` at inference, no network at score time.
SYSTEM-span tokens are an optional damaged-ink **field** channel with decoy
filters and never an adjudication upgrade path. Layout risk vetoes strip those
spans so they cannot manufacture clearances.
