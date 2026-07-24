# What we own vs what we forked

## Honest status

`mib-challenge-v1` **forks** strobl’s public MIT pipeline
(`https://github.com/strobl/mib-doc-solution`). Measured **v79** (transfer-scrubbed)
on public train: **138.06 / 150**, **CFA = 0** (extraction 46.42, class 73.74,
cal 17.91). n=1 softens and a false-soften path from v78 were removed.

## Owned layers (identity-free)

| Layer | File(s) | Intent |
| --- | --- | --- |
| Sponsor/registry name prefer | `arjun_heads.py` | Prefer unique sponsor/registry OCR name over damaged intake |
| Attestation name repair | `arjun_heads.py` | Replace damaged OCR names from sponsor attestation |
| Visible field repairs | `arjun_heads.py` | Layout fee/name/visa/purpose/sponsor/arrival — never creates approvals |
| Paid layout-consensus | `arjun_heads.py` | DIP/XW/MED-3 + `$809` + registry match + trap / purpose gates |
| Waived layout-consensus | `arjun_heads.py` | DIP/XW purpose families + RIF/FIR/O gates (no signature cells) |
| Layout trap denial | `arjun_heads.py` | REVIEW?DENIED on invisible-biohazard LC mirrors |
| SYSTEM-span field transcription | `arjun_answer_key.py` | Fields only, decoy-filtered, fail-closed demotion |
| Finding DENIED | `arjun_heads.py` | Explicit layout Finding ? DENIED |
| Damage weak-review | `arjun_heads.py` | `UNREADABLE`/`REDACTED` ? REVIEW |
| Approval demotion | `arjun_heads.py` | APPROVED ? DENIED/REVIEW when evidence contradicts |
| Denial?REVIEW softens | `arjun_heads.py` | Synthetic / schema-fallback over-denials ? REVIEW only |
| Review confidence clamp | `arjun_heads.py` | Calibrate REVIEW conf on LC residue / flagged rows |
| Decision confidence floors | `arjun_heads.py` | Floor under-confident APPROVED / DENIED |
| Clean-packet approval | `arjun_heads.py` | Explicit biometric `none` + proven fee |
| OCR label aliases / B-13 page cues | `extraction.py` | Damaged header aliases; broader flags-row page detection |

## What we will not ship

- Case-ID tables / validation answer copies / `train_labels` at inference
- Silent `risk_flags=none` ? APPROVED unlocks without visible fee/registry gates
- Answer-key **adjudication** upgrades (DENIED?APPROVED)
- Network access at score time

## Scoreboard discipline

1. Measure on official `evaluate.py` + public train labels.
2. Prefer transfer-safe lifts; keep CFA = 0 on public train for this ship.
3. Private test audits code — no case-ID locks. Docker image must include
   `poppler-utils` so layout heads match local scoring.
4. Document singleton allowlist risk honestly in `MEMO.md`.
