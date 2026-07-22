# Attribution

This solution vendors and runs the public offline MIB pipeline published by
**strobl** at https://github.com/strobl/mib-doc-solution (challenge fork of
8090-inc/mib-doc-challenge, MIT License).

We use that implementation as the primary runtime because independent local
evaluation on the public 1,000-case training set reproduced **~130.26/150 with
0 catastrophic false approvals**, materially ahead of our prior heuristic
pipeline (~122.95).

Modifications in this repository, if any, and the validation submission package
are our responsibility. See `MEMO.md` for approach notes and measured scores.
