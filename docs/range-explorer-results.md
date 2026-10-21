# Local range exploration: measured evidence

Supplied-model conditioning only; no solver, action EV or population calibration.
The first table retains the original pre-review local snapshot.

| Case | Parent wall (s) | Worker CPU (s) | Full result bytes | Status |
| --- | ---: | ---: | ---: | --- |
| example | 0.376 | 0.016 | 53389 | computed |
| maximum_false | 1.249 | 0.891 | 1546278 | computed |
| maximum_true | 0.917 | 0.547 | 1593303 | computed |

Windows 11 / Python 3.14.8; BLAS threads 1. Both maximum samples use three profiles, 24 combos/player, three players and 24 action models/profile. The disjoint-card sample enumerates all 13,824 compatible private deals.

115 tests, including 20 exact-Fraction random-model checks, plus existing 10-case river/sensitivity regressions passed. Raw reports remain in local/CI artifacts; JSON retains source/raw/profile hashes. These are measured samples, not universal bounds or hosted acceptance. Final-head CI was pending when this local snapshot was recorded.

After review, private-context history replay prevents £6.01/£6.02 fingerprint
collisions at ambient precision 2. Position aliases normalize consistently through
history, priors and target pairs. The full suite now passes **117 tests**, plus
Ruff, compileall and the unchanged river/sensitivity checks. All nine profile
digests below match the original evidence exactly; no numerical gates changed.

| Fresh review-fix case | Parent wall (s) | Worker CPU (s) | Full result bytes | Status |
| --- | ---: | ---: | ---: | --- |
| example | 0.392 | 0.016 | 53388 | computed |
| maximum_false | 1.343 | 0.938 | 1546276 | computed |
| maximum_true | 0.979 | 0.594 | 1593302 | computed |

Same Windows/Python environment and local-only limits. The JSON's
`review_fix_validation` retains fresh source/raw/profile hashes. The pre-review
CI at `4c764ba` passed in run `39644126795`; review-fix final-head CI is pending
at this snapshot. These local checks establish no new hosted acceptance.
