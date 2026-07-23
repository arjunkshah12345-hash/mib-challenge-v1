# What we own vs what we forked

## Honest status

`mib-challenge-v1` **forks** strobl’s public MIT pipeline
(`https://github.com/strobl/mib-doc-solution`). Measured **v36** on public
train: **133.37 / 150**, **CFA = 1** (extraction 46.41, class 70.03, cal 16.93).

## Owned layers (identity-free)

| Layer | File(s) | Intent |
| --- | --- | --- |
| Sponsor/registry name prefer | `arjun_heads.py` | Prefer unique sponsor/registry OCR name over damaged intake |
| Visible field repairs | `arjun_heads.py` | Layout fee/name/visa/purpose/sponsor/arrival — never creates approvals |
| Layout-consensus approval | `arjun_heads.py` | DIP/XW + `$809` + registry==applicant (v30-safe gate) |
| AK field transcription | `arjun_answer_key.py` | SYSTEM span **fields only**, decoy-filtered, fail-closed demotion |
| Approval demotion | `arjun_heads.py` | APPROVED?DENIED/REVIEW when risk evidence contradicts |
| Clean-packet approval | `arjun_heads.py` | Explicit biometric `none` + proven fee |
| OCR label aliases / B-13 page cues | `extraction.py` | Damaged header aliases; broader flags-row page detection |

## What we will not ship

- Train-tuned page-count gates or purpose FA laundry lists
- Silent `risk_flags=none` ? APPROVED unlocks
- Case-ID tables / validation answer copies
- Answer-key **adjudication** upgrades (DENIED?APPROVED)

## Scoreboard discipline

1. Measure on official `evaluate.py` + public train labels.
2. Prefer transfer-safe lifts; keep CFA as low as possible without wiping true approvals.
3. Private test audits code — no case-ID locks.
