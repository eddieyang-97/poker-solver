# Reproduced baseline — 2026-10-31

Executed from the two archived scripts (Python 3, C++17 with `g++ -O3 -Wall -Wextra -pedantic`, 200,000 sampled training iterations, C++ RNG seed 761245).

## Probability enumerator
Opponent fly contributions to face 4, among 7,776 equally likely ordered rolls:

| Effective count | 0 | 1 | 2 | 3 | 4 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sequences | 1024 | 2560 | 2560 | 1280 | 320 | 30 | 2 |

Opponent zhai contributions: 0:3125, 1:3125, 2:1250, 3:250, 4:25, 7:1.

For own roll (4,4,4,2,3) in fly, bid validity for N=3..10:
`100.00%, 86.83%, 53.91%, 20.99%, 4.53%, 0.41%, 0.41%, 0.03%`.
For (4,4,4,1,1), own fly count=6; probability of at least N=6,7,8,9,10 is `100.00%, 86.83%, 53.91%, 20.99%, 4.53%`.

These are **pre-action baseline probabilities**. A bid is informative; challenge EV cannot generally be inferred from these alone.

## One-face toy experiment
```text
EV p0 self-play 0.0207
BR player0 payoff 0.0358 BR player1 payoff -0.0091 NashConv 0.0267
```
Observed elapsed ~21.65 s on the available CPU; this is machine-dependent.

Average-strategy challenge probabilities to an opening bid of 3, by own effective-4 contribution 0/1/2/3/4/6/7:

`0.9847, 0.6022, 0.0066, 0.0000, 0.0000, 0.0001, 0.0013`

To an opening bid of 4:

`0.9964, 0.9897, 0.3577, 0.0005, 0.0000, 0.0001, 0.0014`

The approximate NashConv concerns **only the one-face toy model**, not the full rule set. The toy's unusual incentives (e.g. starting with N=3 for most types) should not be extrapolated to the actual game. Verify the solver independently before relying on the estimate.

## Open issues for follow-on work
Confirm all edge-case rules, benchmark the existing solver on an independently evaluable toy game, add tests for probability and action legality, then explore a genuine two-player full-rule approximate equilibrium with honest convergence/resource reporting. See [#40](https://github.com/eddieyang-97/poker-solver/issues/40).
