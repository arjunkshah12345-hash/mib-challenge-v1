# MIB Doc Challenge — Technical Memo

## Approach

Runtime vendors the public **render-first** offline pipeline from strobl
(`https://github.com/strobl/mib-doc-solution`, MIT), with attribution in
`ATTRIBUTION.md`.

Flow:

1. Rasterize every page (`pypdfium2`) — embedded PDF text is diagnostic only.
2. Tesseract sparse OCR with layout/label recovery and bounded retries.
3. Independent RapidOCR fill for unresolved fields only (never a second vote).
4. Evidence resolution with source authority, strike-through, and conflicts.
5. Identity-free adjudication from `FIELD_MANUAL.md`, plus frozen review
   recovery heads that never invent silent risk.
6. Confidence from pinned isotonic / output recalibration artifacts.

## Leaderboard strategy (anti-overfit)

We optimize for **private-label generalization**, not train-hillclimbing.

- **False approvals are toxic** (−4 raw each). We keep **FA = 0** on train even
  when that leaves true `APPROVED` cases in `NEEDS_REVIEW` (partial credit).
- We **do not** promote complete-looking `NEEDS_REVIEW` rows to `APPROVED`
  based on serialized `risk_flags=none`. That string is often a schema default,
  not a verified biometric observation — promoting it creates invisible-stamp
  false approvals on held-out data.
- No case-ID logic, no validation-label lookups, no per-PDF patches.
- Rules are policy/evidence based so they transfer to validation and the
  post-close private test (which also audits code).

## Local train result (1,000 labeled PDFs)

| Build | Total | FA | Extr | Cls | Cal |
|------:|------:|---:|-----:|----:|----:|
| prior heuristic | ~122.95 | 0 | ~43 | ~64 | ~16 |
| **this submission (strobl-vendored)** | **130.26** | **0** | **44.84** | **68.44** | **16.97** |

Confusion highlights: 117 true `APPROVED` → `NEEDS_REVIEW` (conservative),
47 true `DENIED` → `NEEDS_REVIEW` (mostly missed risk/fee evidence), **0**
`DENIED` → `APPROVED`.

## Failure modes / next week

- Invisible denial stamps (especially `biohazard_red`) remain unreadable by
  OCR; correct behavior is `NEEDS_REVIEW`, not a guessed approval.
- Fee status sometimes absent from visible pixels; we refuse hidden-text fees.
- Further safe gains: better **visible** risk/fee localization, then
  re-adjudicate — never silent risk → `APPROVED`.

## Docker

`Dockerfile` matches the offline contract (`run.sh` → `solution.py`,
`--network none`, CPU-only, hashed `requirements.lock`).
