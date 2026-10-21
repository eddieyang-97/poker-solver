# Local range exploration: measured evidence

Supplied-model conditioning only; no solver, action EV or population calibration.

| Case | Parent wall (s) | Worker CPU (s) | Full result bytes | Status |
| --- | ---: | ---: | ---: | --- |
| example | 0.376 | 0.016 | 53389 | computed |
| maximum_false | 1.249 | 0.891 | 1546278 | computed |
| maximum_true | 0.917 | 0.547 | 1593303 | computed |

Windows 11 / Python 3.14.8; BLAS threads 1. Both maximum samples use three profiles, 24 combos/player, three players and 24 action models/profile. The disjoint-card sample enumerates all 13,824 compatible private deals.

115 tests, including 20 exact-Fraction random-model checks, plus existing 10-case river/sensitivity regressions passed. Raw reports remain in local/CI artifacts; JSON retains source/raw/profile hashes. These are measured samples, not universal bounds or hosted acceptance. Final-head CI was pending when this local snapshot was recorded.
