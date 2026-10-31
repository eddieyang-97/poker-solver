# Probability guidance and baseline-corrected sampling

This is the next Issue #40 experiment after the [confirmed-rule baseline study](research.md). It keeps all 252 private hands, every legal bid/challenge and full public-history information sets. It changes initialization, fallback play and the sampled value estimator; it does not merge histories, remove actions or alter the owner-confirmed rules. Historical failed runs in `outputs/research.json` and `outputs/abstraction.json` remain intact.

## Predeclared comparison

`run_guided.py` compares four settings with seeds 761245 and 42, 10,000 complete iterations requested and a 200,000-information-set cap per run:

| Variant | Initial / unvisited policy | Initial cumulative regret | Sampled value baseline |
| --- | --- | ---: | --- |
| `uniform` | Uniform legal actions | 0 | Zero |
| `baseline_only` | Uniform legal actions | 0 | Prior probability proxy |
| `guided` | Probability-only policy | 5 × initial policy row | Zero |
| `guided_baseline` | Probability-only policy | 5 × initial policy row | Prior probability proxy |

Exploration remains 0.6 for the updating player and 0.05 for the opponent. Both sampling policies have full support. Regrets remain signed; no clipping, importance-weight cap or weakened convergence gate is introduced. The original sampler's default settings remain the `uniform` control. Finite initial regrets and a useful fallback can improve short-run behavior but do not certify equilibrium.

The guide challenges when the prior probability of the preceding claim is below 0.5. Otherwise it chooses the legal bid with highest prior truth probability, with ties broken by lower quantity, higher face, then 飞. Its exact finite probability sums use integer ordered-roll multiplicities out of 7,776 before division; this avoids floating summation changing mathematically tied choices. It assumes independent opponent dice, ignoring signalling. This is a heuristic policy, not an equilibrium calculation. An **untrained** guide is evaluated separately so that its quality is not attributed to CFR learning.

The value proxy is `1−2P(true)` for challenge, or `2P(true)−1` for a raise under the hypothetical assumption that the next player immediately challenges. It uses the acting player's hand and the independent prior, not the realized opponent hand. It is not an estimate certified for strategic continuation.

For sampled action a with sampling probability q(a), use action estimates

`B(i) = b(i) + 1[i=a] × (child_estimate − b(i)) / q(a)`.

The node estimate is `sum_i sigma(i) B(i)`; the existing prefix reach corrections apply to regret updates, and average-policy accumulation is unchanged. The proxy is evaluated before sampling and its sign converted to the updating player's utility at opponent nodes. Wrong baselines can increase variance, but the correction preserves the expectation. Method sources: [Schmid et al., AAAI 2019](https://ojs.aaai.org/index.php/AAAI/article/view/4048) and [Davis et al., ICML 2020](https://proceedings.mlr.press/v119/davis20a.html). This implementation uses a fixed prior proxy, not those papers' full set of learned baseline methods.

## Independent estimator and small-game checks

Tests enumerate nonuniform sampling paths and chance types, including hands whose target policy gives an observed action zero probability. Both regrets and average weights match their exact expectations. A perfect-baseline two-action example eliminates the action-sampling variance; a deliberately wrong baseline remains unbiased. The frozen-policy moment oracle independently enumerates first and second moments on the one-face 3..5 game and checks its mean against the existing exact policy evaluator.

| Frozen toy policy | Updater | Zero-baseline variance | Prior-proxy variance |
| --- | ---: | ---: | ---: |
| Uniform | 0 / 1 | 0.998958 | 0.673714 |
| Probability-only | 0 | 2.355775 | 2.561152 |
| Probability-only | 1 | 1.752552 | 1.971524 |

These moments include private-deal chance variance and hold the policy fixed; they are not the variance of a changing training run. The proxy helps the uniform policy but harms the probability-only policy in this fixture. A blanket claim of variance reduction would therefore be false.

The JSON receipt also records exact NashConv at 1,000, 10,000 and 100,000 iterations for every variant/seed on that toy game. These are exact best-response evaluations of the toy policies, not full-game exploitability measurements.

## Stronger full-game response tests

Each frozen average policy faces uniform and three prior-only threshold bots in both seats with 2,000 fresh games per pairing. It also faces two posterior-aware bots (thresholds 0.4 and 0.6) with 1,000 games per seat, using different evaluation seeds from training. No policy is updated or selected using these outcomes.

The posterior bots know the frozen target's behavioral policy. They update its private-hand distribution using the likelihood of each observed target bid and choose challenges/raises using the resulting truth probabilities. They receive only their own private hand and public history, never the target's dealt hand. Their bounded posterior cache is separate from the solver and is created only after training freezes. Own observed actions add no target-hand likelihood conditional on the bot's own information. Zero-support evidence raises an error instead of resetting to a prior. The accelerated calculation is compared against the independent `beliefs.posterior` helper.

This is a more informed diagnostic opponent, **not an exact best response**: its raises maximize claim probability rather than full continuation value. The larger set of response tests can establish only an exploitability lower bound. For each run, the bound uses a simultaneous 95% Hoeffding/union correction across all twelve predeclared bot/seat tests, accounting for each test's sample count. It is not a joint guarantee across runs or an exploitability upper bound. Small or zero lower bounds cannot establish GTO.

## Measured outcome

All eight runs completed 10,000 iterations without hitting the information-set cap. Values below are diagnostics, not strategy recommendations. Memory is traced training allocations, not RSS; CPU time includes allocation tracing overhead.

| Variant | Seed | Information sets | Training CPU seconds | Traced MiB | Self-play unseen decisions | 95% full-game NashConv lower bound |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uniform | 761245 | 84,496 | 79.89 | 71.23 | 69.54% | 1.7689 |
| Uniform | 42 | 84,160 | 79.39 | 70.97 | 69.76% | 1.7679 |
| Baseline only | 761245 | 83,399 | 133.66 | 69.86 | 69.17% | 1.7699 |
| Baseline only | 42 | 83,288 | 134.02 | 70.02 | 69.40% | 1.7649 |
| Guided | 761245 | 24,791 | 78.23 | 40.71 | 28.15% | 1.3938 |
| Guided | 42 | 24,959 | 51.98 | 40.92 | 28.05% | 1.3978 |
| Guided + baseline | 761245 | 25,649 | 86.09 | 45.88 | 29.95% | 1.1538 |
| Guided + baseline | 42 | 25,654 | 85.98 | 46.33 | 29.31% | 1.2178 |

Uniform reproduces the earlier control's information-set counts and self-play EVs. The revised opponent suite has more tests, different sample counts and a different simultaneous correction, so its lower bound should not be numerically equated with the old eight-test bound.

Guidance reduces unseen decisions and beats uniform opponents, but posterior-aware responses still win heavily. The untrained guide itself has a 95% NashConv lower bound of **1.3078**. Guided CFR without the baseline has a larger demonstrated lower bound; guided + baseline has a smaller demonstrated lower bound. These are **lower bounds from a finite opponent set**, not complete exploitability rankings or evidence that any run is close to equilibrium. Static heuristics already supply much of the improvement against uniform play, and more iterations are not demonstrated to cure the remaining weakness.

`prior_control.py` independently enumerates all 63,504 private multiset pairs, weighted as 60,466,176 ordered chance outcomes, for the untrained guide. Its exact self-play player-0 EV is **−1758491/10077696 ≈ −0.1744933564**, with player 0 drinking probability **0.5872466782**. This is a policy value, not the value of the game. The sampled control self-play EV −0.178 agrees within its stated interval. The scalar enumeration is also checked against the independent tuple-tree evaluator on three small games. See `outputs/prior-control.json`.

The [finite-family experiment](family-research.md) tests a different approach with exact full-game chance enumeration and an explicit strategy restriction. It reaches a tiny restricted gap but is still exposed by outside opponents. Together these failures point to action-conditioned beliefs and stronger response/search classes as the next priority, rather than publishing heuristic opening frequencies.

## Reproduce and interpret the receipt

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_guided.py --seeds 761245 42 --checkpoints 1000 10000 --games 2000 --adaptive-games 1000 --max-infos 200000
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/prior_control.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

On PowerShell set `$env:OPENBLAS_NUM_THREADS='1'` and use `.venv/Scripts/python.exe`. Results are written incrementally to `outputs/guided.json`; a missing requested variant means the study did not finish. Source hashes are explicitly LF-normalized, and the JSON is written with LF endings. The original historical receipts retain their original raw-source hash convention.

Training records requested versus completed iterations, actual wall/CPU time, traced allocations, information-set counts, maximum prefix weights and maximum recursive value estimates. Training time includes model/guide setup; traced peaks begin after setup and exclude some native/process memory. Evaluation time is recorded separately. These are local measurements, not universal resource bounds or hosted acceptance. Raw opening frequencies are diagnostics until solver quality is independently established.
