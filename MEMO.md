# MIB Doc Challenge — Technical Memo

## Approach

We **fork** strobl’s public render-first offline pipeline (MIT) and add owned
layers documented in `CONTRIBUTIONS.md` / `ATTRIBUTION.md`. The goal is to
**beat** that baseline on held-out labels — not to resubmit it unchanged.

Base stack:

1. Rasterize pages (`pypdfium2`); embedded text is diagnostic only.
2. Tesseract sparse OCR + bounded retries.
3. RapidOCR fill for unresolved fields only.
4. Evidence resolution (authority, strike-through, conflicts).
5. Identity-free field-manual adjudication + frozen recovery heads.
6. Pinned confidence recalibration.

Owned extensions:

- Hardened fee/purpose OCR (fuzzy receipt headings, waived repair, fee cells).
- Biometric clean-risk recovery (explicit `none` only from a clean B-13 flags row).
- Anti-FA gate on statistical `REVIEW→APPROVED` (fee must be policy-proven).

## Leaderboard / anti-overfit

- Optimize for private validation labels + post-close private test / code audit.
- Keep **FA = 0** preferred over train-hillclimbing approvals.
- No case-ID logic, no validation-label copies, no silent-risk → APPROVED unlocks.

## Local train reference

| Build | Total | FA |
|------:|------:|---:|
| Our prior heuristic | ~122.95 | 0 |
| Upstream strobl (reproduced) | **130.26** | **0** |
| This fork (owned layers) | measuring vs upstream on same split | target ≥130.26, FA=0 |

## Failure modes / next week

Invisible denial stamps remain the hard ceiling for OCR-only systems. Further
owned work targets visible risk/fee recovery and re-adjudication when those
facts are actually observed — never inventing risk clearance.
