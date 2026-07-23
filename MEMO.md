# MIB Doc Challenge — Technical Memo

## Approach

Fork of strobl render-first MIT pipeline + owned recovery heads.

**Measured (v53 stack on public train):**

| Total / 150 | CFA | Extr / 50 | Cls / 80 | Cal / 20 |
|------------:|----:|----------:|---------:|---------:|
| **133.83** | **1** | **46.41** | **70.38** | **17.04** |

Pipeline order after primary OCR / Rapid fill-in:

1. Prefer sponsor/registry name over damaged intake.
2. Visible layout field repairs (never create approvals).
3. Layout-consensus APPROVED for DIP/XW when `$809` + registry==applicant.
4. SYSTEM “answer key only:” **field** transcription (decoy-filtered, fail-closed).
5. Explicit `Finding: DENIED` → DENIED.
6. Damage weak-review: APPROVED → REVIEW on `UNREADABLE`/`REDACTED` layout markers.
7. Safety demotion + TRANSIT-7 hard deny.

## Rejected / unsafe (from howtoget1.md and ablations)

- MED-3 biohazard blanket approve (13 CFA).
- Fee-Status / unpaid layout without corroboration (hurts true approvals).
- Global vocab overwrite, output-only train-mode fallbacks.
- Dual-PSM/page-count/purpose laundry (already covered or overfit).
- High-res/invert OCR on invisible stamps (0/50 layout FAs recovered).

## Residual CFA

`MIB-000068`: invisible `memory_tampering` (not in text/OCR/high-res).
