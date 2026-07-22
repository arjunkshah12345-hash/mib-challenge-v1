# Attribution

## Upstream

This repository **forks** the public offline MIB pipeline published by **strobl**
at https://github.com/strobl/mib-doc-solution (MIT License; challenge context:
8090-inc/mib-doc-challenge).

Upstream provides the render-first OCR/evidence/adjudication stack that scores
approximately **130.26/150 with 0 catastrophic false approvals** on the public
1,000-case training split.

## Our work

We do **not** submit upstream unchanged. See `CONTRIBUTIONS.md` for owned
layers:

- Fee/purpose OCR hardening
- B-13 flags-row binder (adjacent-line `none` / positive risk recovery)
- Clean-packet approval head (requires explicit biometric `none` + proven fee)

We do **not** use embedded PDF answer-key spans, case-ID tables, or silent
risk→approve unlocks.

Prior original heuristic work in this org topped out near **~122.95/150, FA=0**
before adopting the render-first stack as a base to extend.
