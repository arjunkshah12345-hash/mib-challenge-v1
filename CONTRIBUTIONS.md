# What we own vs what we forked

## Honest status

`mib-challenge-v1` started as a **fork of strobl’s public MIT pipeline**
(`https://github.com/strobl/mib-doc-solution`). That baseline scores
**~130.26/150 with FA=0** on the public train split. Shipping it unchanged
would be attribution-legal but **not** a differentiated competitive entry.

This file tracks **our** deltas. The goal is to **beat** that baseline on
held-out labels without case-ID overfit and without catastrophic false
approvals.

## Our layers (identity-free)

| Layer | File(s) | Intent |
| --- | --- | --- |
| Fee/purpose OCR hardening | `mib_pipeline/extraction.py` | Fuzzy fee-receipt headings, waived OCR repair, purpose regex, fee-cell normalization (`$809` / `$0` / DIP-WAIVER) |
| Biometric clean-risk recovery | `mib_pipeline/extraction.py` (`_biometric_clean_none_evidence`) | Emit explicit `risk_flags=none` only when a B-13 page shows a clean flags row (not silent default) |
| FA gate on statistical approve | `mib_pipeline/arjun_heads.py` | Block upstream statistical `REVIEW?APPROVED` unless fee is policy-proven (`fee_paid` / `valid_fee_waiver`) |
| Wiring | `mib_pipeline/rapid_recovery.py` | Call the FA gate before the statistical approval head |

## What we will not ship

- Train-tuned “silent risk ? APPROVED” unlocks
- Case-ID tables / validation answer copies
- Claiming strobl’s score as an original result

## Scoreboard discipline

1. Measure **our fork** vs **upstream strobl** on the same train preds.
2. Only promote a build that is ? strobl on train **and** FA ? strobl’s FA (0).
3. Leaderboard target = validation private labels; private test audits code.
