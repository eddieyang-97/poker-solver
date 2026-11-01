# Exact full-rule payoffs, restricted strategy equilibrium

This experiment solves a finite strategy-family game inside the owner-confirmed full Liar's Dice game. It provides exact chance-weighted policy values and a precise **restricted-family** equilibrium gap. It does not supply a full-game GTO policy. Outside posterior-aware responses decisively reject that interpretation.

## Policy family and exact matrix

There are fifteen parameterized deterministic policies (some behaviorally identical): challenge thresholds 0.3/0.5/0.7 crossed with five raise styles. The first style chooses the highest prior truth probability, with lower quantity, higher face and 飞 breaking ties. The other four styles choose the highest legal quantity whose prior truth probability is at least 0.2/0.5/0.8/0.95, then highest truth probability and the same face/mode tie ordering. If no bid meets that confidence level, use the safest bid. At non-opening decisions, challenge first if the current claim's prior truth probability is below the policy's challenge threshold. Forced final challenges remain legal and mandatory. These are policy-class restrictions, not new house rules or action-tree pruning.

Each policy sees its own exact hand and public last bid. Every legal face, mode and quantity is available when choosing its action. `exact_matrix` plays each of the 225 policy pairs on all 63,504 private multiset pairs, with integer ordered-roll multiplicities. Each matrix entry has denominator **60,466,176**; its integer numerator is retained in `outputs/family.json`. The vectorized terminal utilities and chance sums are independently checked against the tuple-tree evaluator on small games, and the full-game prior-policy diagonal is checked against `prior_control.py`'s scalar enumeration.

The matrix is a normal-form game whose actions are complete policies. Its mixtures select a component independently of the private roll. They do not allow choosing the component after seeing the opponent hand, or optimizing a separate mixture for every own hand. Those restrictions limit what the family gap can prove.

## Mixing without losing recall

Resampling a component independently at every decision would implement a different strategy. `Mixture` instead converts a root mixture into a behavioral policy using **own action reach**: discard components inconsistent with that player's earlier public actions at its known private hand, then renormalize the original mixture weights. Opponent actions do not directly prune own components; they determine the public states at which own actions were taken.

The resulting behavioral policy retains full public history even though each individual component is a last-bid policy. At own-zero-reach information sets it has an explicit uniform fallback. Tests compare the exact tuple-tree value of this converted policy with the bilinear payoff `xᵀAy` of the root mixture, and compare its accelerated posterior likelihoods with independent conditioning. Matching pennies, an asymmetric mixed game, a pure saddle and rock-paper-scissors check the matrix solver and its reported best-response gap.

## Convergence inside the family

The solver uses alternating positive-regret matching and linearly weighted averages. For reported mixtures x/y, the exact family value bracket is

`min_j (xᵀA)_j ≤ finite-family game value ≤ max_i (Ay)_i`.

The difference is the measured family NashConv. This bracket applies only to the fifteen declared strategies. It cannot upper-bound exploitability in the full extensive-form game. Chance enumeration is exact; mixture arithmetic and the reported bracket use floating point, not interval certification.

| Matrix iterations | Family NashConv | Expected player-0 payoff of mixtures |
| --- | ---: | ---: |
| 1,000 | 0.0000238990 | −0.035517947 |
| 10,000 | 0.0000002392 | −0.035533363 |
| 100,000 | 0.000000002392 | −0.035533517 |

The limiting family solution is nearly degenerate: player 0 puts essentially all mass on confidence-0.8 raising, split between two challenge thresholds that are equivalent on the relevant paths; player 1 favors the safest-bid style. The near-50/50 component weights are not evidence for a universal bluff frequency or a uniquely identified strategy.

The exact full-game expected payoff of these **restricted policies** is approximately −0.035533517. This does not establish the unrestricted game's equilibrium value. A held-out self-play sample gives −0.0292, consistent with the exact value within its interval.

## Outside responses still expose the policy

Frozen mixtures face uniform and prior-only bots for 5,000 games per seat and two posterior-aware bots for 2,000 games per seat. These use fresh seed 900001 and separate evaluation offsets. No mixture weight is fitted to those outcomes.

Despite beating uniform play, the mixture has a simultaneous 95% **full-game NashConv lower bound of 1.2079** from those twelve bot/seat tests. The exact family gap is about 2.4e−9, but the full-game lower bound exceeds 1.20. This is a concrete example of a small restricted-game equilibrium gap failing to validate an abstraction. The posterior bots are not full best responses, so true exploitability can be larger.

Matrix construction took approximately 1.04 seconds and the complete matrix solve plus 53,000 evaluation games approximately 8.86 seconds on this local machine. The component choice table occupies 1,277,640 bytes; this excludes all other model, working and Python memory. Unlike the sampled training study these times did not include allocation tracing. This is a small-class feasibility result, not a general full-game compute bound or a like-for-like solver speedup.

## A model-specific belief lesson

Under this frozen player-0 mixture, opening **five fours 飞** occurs with probability approximately 0.0334362. With own hand **11235**, an independent pre-action opponent roll makes that claim true with probability **0.2098765**, giving challenge EV **+0.5802469**. After conditioning on the fact that this particular model chose that opening, the claim is true with probability effectively **1**, and challenge EV becomes **−1**.

With own **22356**, the same conditioned claim is false and challenge EV is +1. Both results use only the responder's hand and the observed bid; the opponent hand is integrated out. `run_family.py` checks the posterior calculation against the existing terminal utility helper and records the inputs and outputs.

This lesson depends on the declared frozen opponent model. It does not claim human opponents follow this policy, or that the mixture is GTO. It demonstrates why even exact unconditional dice probabilities can reverse a challenge decision when used without action conditioning.

## Reproduce and next step

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_family.py --games 5000 --adaptive-games 2000
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Payoff numerators, component parameters, root mixture weights, value brackets, source hashes, timing and test outcomes are retained in `outputs/family.json`. This is an in-repository model/evaluator, not an externally audited solver. No strategy is promoted as practical GTO.

The next substantive step is to expand the strategy class with history-conditioned responses and repeat the response tests, potentially through a policy-space double-oracle procedure. A low gap after that expansion would still need progressively stronger response searches or a credible full-game upper bound. The present result rejects the current class; it does not authorize hiding its failure behind the tiny family gap.
