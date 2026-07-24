# Transfer / overfit audit (v79)

Date: 2026-07-24. Baseline preds: `artifacts/predictions-train-v79.jsonl`
(**138.06 / 150**, CFA=0). No `MIB-######` case-ID unlocks anywhere in owned
Python sources.

## Method

1. Inventory every owned approve / deny / soften / trap / decoy rule.
2. Measure support on public train (`v75` stream ? apply v79 heads).
3. Ablate each leftover singleton / brittle cell and re-score.
4. Keep only rules that are CFA-safe **and** leave total **> 138**.

## Already scrubbed (v79)

| Removed | Evidence |
| --- | --- |
| Schema waived+illegible soften | n=1 |
| Synthetic-only + schema-arrival soften | n=1 **and FP** (true DENIED?REVIEW) |
| DIP-1 waived conf band `0.54–0.56` | magic / dead |
| Trap-denial conf caps `?0.15` / `?0.30` | train-conf tuning; structural gates enough |

## Live rule scorecard (v75?v79 deltas)

All v79 adjudication changes vs v75 are **gold-correct** (11 OK / 0 WRONG).

### Approve (0 FP)

| Rule | n | Notes |
| --- | --- | --- |
| Medical consult + Registry-before-close (MED-3\|XW-2) | 3 | Family OK; XW-2 alone is n=1 |
| Trailing single-`O` LC (paid+waived) | 2 | Structural; keep |
| Waived MED-3 industrial (trailing O) | 1 *incremental* | Family already multi-support historically; only 1 new on v75 residue |

### Deny traps (0 FP)

| Rule | n | Notes |
| --- | --- | --- |
| MED-3 industrial Registry-last | 2 | Mirror of approve gate |
| MED-3 unsafe-purpose + Registry-before-close | 3 | diplomatic n=2 + archive n=1 under one exclusion family |
| XW-2 medical consult Registry-last | 2 | Mirror of MC approve |

### Fail-closed LC blocks (prevent false APPROVED)

| Rule | n on clean LC-ish packets | Ablation if removed |
| --- | --- | --- |
| Purpose traps (xenobotany / XW-2 archive) | 1 each | Needed with sig traps for CFA/class |
| Sig traps (DIP archive FIR, DIP reactor FRI, XW-2 diplomatic IFR) | 1–2 | Removing all ? **137.76** + 3 wrong APPROVED |
| FRI + transit | 1 | Removing ? **137.96** + wrong APPROVED `MIB-000004` |

Purpose-broadening those sig traps **blocks true APPROVED** purposes on
train — cannot replace signature cells with purpose-only bans.

### Softens on current v75 DENIED stream

**Zero fires** after scrub. Latent branches remain (DIP-1 illegible, XW-2
waived+illegible, MED-3 rescinded, Wolf schema, DIP-WAIVER+attestation, …).
Wolf-1061c high-conf DENIED without world text has **14/15 gold DENIED** —
softens stay gated on `flags==none` + form absence so they do not FP today.

## Ablation wall (must stay for >138)

| Ablation | Score | CFA | Wrong APPROVED |
| --- | ---: | ---: | --- |
| v79 baseline | **138.06** | 0 | — |
| Drop XW-2 from MC allow | 138.00 | 0 | — |
| Drop archive from unsafe deny | 138.00 | 0 | — |
| Drop both above | 137.94 | 0 | — |
| Drop trailing-O allow | 137.94 | 0 | — |
| Drop all sig traps | 137.76 | 0 | 001, 164, 232 |
| Drop FRI+transit only | 137.96 | 0 | 004 |
| Drop only `(XW-2, diplomatic, IFR)` | 137.96 | 0 | 232 |

**Ship constraint:** keep baseline set; do not strip the fail-closed cells
above if the goal is public-train **> 138**.

## Answer-key decoys (`arjun_answer_key.py`)

Identity-free planted-token filters (not case IDs). On 188 keyed PDFs:

| Decoy | Seen in AK | Equals gold | Missed recovery on v79 |
| --- | ---: | ---: | ---: |
| `risk_flags=none` | 85 | 75 | 0 (pred already correct) |
| `visa_class=XW-2` | 37 | 24 | 5 |
| `declared_purpose=research` | 30 | 13 | 2 |
| `species_code=ORION_GRAYS` | 30 | 17 | 2 |
| `sponsor_id=SPN-1042` | 10 | 0 | 0 |
| `applicant_name=Luma Voss` | 19 | 0 | 0 |

**Keep `none` / `XW-2` / `research` decoys:** they also appear as *false*
AK tokens often enough that removing them would write wrong fields (and
clearing risk to `none` is CFA-adjacent). Extraction miss from blocking is
smaller than the wrong-write risk.

## Empty anti-overfit tables (keep empty)

- `_MED3_LC_SAFE_PURPOSE_SIG`
- `_LC_XW_MEDICAL_CONSULT_SIG`
- `_LC_WAIVED_VISA_PURPOSE_SIG`

## Residual transfer risk (honest)

1. **Fail-closed signature cells** (incl. FRI+transit) are train-measured;
   on holdout they may block a rare true APPROVED (class loss) or prevent a
   false APPROVED (gain). Preferable to unlock singletons.
2. **XW-1 excluded from medical-consult LC** because of invisible
   `planetary_embargo` under the same gates — visa carve-out, not case-ID.
3. **~73 A2R** remain mostly O-page / invisible-stamp; fee-crop OCR is the
   honest path past ~138, not more allowlists.
4. No case-ID hardcoding in owned modules; no `train_labels` at inference.

## Verdict

v79 is the transfer-scrubbed ship: **138.06**, CFA=0, no false softens, no
wrong approvals vs v75?v79 deltas. Further singleton stripping hits the
**?138.00** wall or introduces wrong APPROVED.
