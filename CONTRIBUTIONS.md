# What we own vs what we forked

## Honest status

`mib-challenge-v1` **forks** strobl’s public MIT pipeline
(`https://github.com/strobl/mib-doc-solution`). That baseline scores
**~130.26/150 with FA=0** on the public train split.

Shipping upstream unchanged would be attribution-legal but **not** a
differentiated entry. This file tracks **our** deltas. The goal is to
**beat** that baseline on held-out labels without case-ID overfit and
without catastrophic false approvals.

## Measured lesson (do not regress)

An earlier “FA gate” on strobl’s statistical approval head **blocked a true
APPROVED recovery** (e.g. `MIB-000051`) and **lowered** a 100-case hard-slice
score vs upstream. That gate was removed.

A competing local patch that read embedded PDF `answer key only:` spans was
**deleted** — that is generator leakage, not OCR, and fails a code audit.

## Our layers (identity-free)

| Layer | File(s) | Intent |
| --- | --- | --- |
| Fee/purpose OCR hardening | `mib_pipeline/extraction.py` | Fuzzy fee-receipt headings, waived OCR repair, purpose regex, fee-cell normalization |
| B-13 flags-row binder | `mib_pipeline/extraction.py` (`_biometric_flags_row_evidence`) | Bind `flags:` to same-line / next-line `none` or positive risks (incl. `illegible`); do not treat bare `flags:` as clean |
| Clean-packet approval head | `mib_pipeline/arjun_heads.py` | Promote REVIEW?APPROVED only when fee is policy-proven **and** risk `none` comes from explicit biometric evidence (not schema default) |
| Wiring | `mib_pipeline/rapid_recovery.py` | Run clean-packet head after upstream XW-1 + statistical heads |

## What we will not ship

- Train-tuned “silent risk ? APPROVED” unlocks
- Case-ID tables / validation answer copies
- Embedded PDF answer-key transcription
- Claiming strobl’s 130.26 as an original result

## Scoreboard discipline

1. Measure **our fork** vs **upstream strobl (v19, 130.26)** on the same train preds.
2. Only promote a build that is ? strobl on train **and** FA ? 0.
3. Leaderboard target = validation private labels; private test audits code.
