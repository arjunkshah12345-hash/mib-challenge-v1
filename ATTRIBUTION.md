# Attribution

## Upstream

This repository **forks** the public offline MIB pipeline published by **strobl**
at https://github.com/strobl/mib-doc-solution (MIT License; challenge context:
8090-inc/mib-doc-challenge).

Upstream provides the render-first OCR/evidence/adjudication stack that scores
approximately **130.26/150 with 0 catastrophic false approvals** on the public
1,000-case training split.

## Our work

We do **not** submit upstream unchanged. See `CONTRIBUTIONS.md` for the owned
layers (fee/purpose OCR hardening, biometric clean-risk recovery, and an
anti-false-approval gate on statistical approval heads).

Prior original heuristic work in this org topped out near **~122.95/150, FA=0**
before adopting the render-first stack as a base to extend.

All validation packaging, Docker contract glue, and owned heads are our
responsibility. Organizer anti-cheat rules still apply: no case-ID answers,
no private-label leakage.
