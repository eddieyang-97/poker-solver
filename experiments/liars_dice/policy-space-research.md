# History-conditioned policy-population expansion

Follow-on [Issue #43](https://github.com/eddieyang-97/poker-solver/issues/43) builds on accepted #40 / merged [PR #42](https://github.com/eddieyang-97/poker-solver/pull/42). All owner-confirmed rules remain unchanged. This is a policy-space response experiment, not a full-game equilibrium certificate.

## Method and information

Start with the fifteen complete prior-probability policies from [the finite-family study](family-research.md). Solve their exact payoff matrix, freeze its root mixture, and construct four new deterministic response policies: challenge thresholds 0.4/0.6 crossed with safest-posterior raising or highest-quantity raising supported at posterior probability 0.8. The response sees its own exact hand, full public history and an explicitly supplied frozen opponent model. It never sees the actual opponent hand or which population component the opponent selected.

For each public history, integrate the likelihood of the opponent's actions over its private hands. Own actions do not directly update that belief. Weighted histograms of the opponent's effective contribution compute all 252 own-hand truth tables without sampling. The complete history is retained; a last-bid key would conflate different signals.

The reference model uses behavioral action probabilities `(1−epsilon) × frozen_policy + epsilon / legal_action_count`, with epsilon 0.02 in the primary run. This explicit assumption defines beliefs even after actions impossible under the untrembled reference. It does not reset the posterior to the prior. The deployed response itself is deterministic. Its probability/aspiration rule is a heuristic; it does not optimize strategic continuation value and is not an exact best response.

Add these complete responses to the policy population, recompute the restricted equilibrium, and construct fresh responses against the new frozen mixture. Each reference is a snapshot of the preceding population, so there are no circular policy definitions. Mixtures select components independently of the dice at the root. Behavioral conversion conditions on the player's own earlier actions at its known hand, preserving realization equivalence even when components are history-dependent.

This follows the population/meta-game pattern of [Lanctot et al. (2017)](https://papers.neurips.cc/paper_files/paper/2017/hash/3323fe11e9595c09af38fe67567a9394-Abstract.html). Our response construction is deliberately simpler than their learned oracles. It has no inherited guarantee of unrestricted best-response quality or double-oracle termination at equilibrium.

## Exact evaluation and bounded work

`exact_pair` groups all 63,504 private multiset pairs by their full public history, chooses actions separately for each acting hand, and sums terminal utilities with integer ordered-roll multiplicities. Every deterministic policy-pair payoff numerator has denominator 60,466,176. Legality, terminal completion and maximum depth are checked. Small-game tests independently compare this evaluator with the original tuple-tree evaluator; old Markov-policy payoffs also match the separate vectorized matrix evaluator.

Mixture weights and posterior comparisons use floating point. This is exact chance enumeration, not formal interval certification of every floating-point decision. Reported lower bounds integrate complete frozen policies, rather than taking an illegal per-deal maximum over hidden opponent hands.

For a frozen target mixture x/y and outside candidates r/s, both `u(r,y)` and `−u(x,s)` are evaluated through the exact component payoff matrix. Maximizing separately for the two seats, also including existing components, gives a **full-game NashConv lower bound**. It has no sampling confidence interval because every chance outcome is enumerated. It remains a lower bound: untested strategies may exploit the target more strongly. Half that sum is the exploitability lower bound under the convention used throughout this directory.

The initial unpruned run was stopped during its second expansion after an observed 216.28 process CPU seconds. Its completed first round and interruption are preserved in `outputs/policy-space-unpruned.json`; incomplete expansions do not receive payoff or convergence claims. That receipt's run-start manifest predates one additional test, as recorded in the receipt. Executable source hashes correspond to commit `47895c5`.

The primary driver explicitly discards root weights below 1e-6, renormalizes, records both discarded masses and recomputes the **deployed mixture's** value and restricted gap directly from the exact matrix. It retains the original unprojected solver report. This avoids recursively evaluating negligible-weight historical components. It is a policy change, not an invisible cache approximation. Per-pair public-node limits and a total time budget checked between policy pairs retain incomplete status on exhaustion; the latter is not a hard process deadline.

## Measured primary result

Two expansions grow the population from 15 to 19 to 23 complete policies. Each restricted matrix is trained for 100,000 iterations. Fresh responses against the current mixture are evaluated before they could be admitted to the next population.

| Population | Deployed restricted NashConv | Exact full-game NashConv lower bound | Exact mixture self-play EV, player 0 | Round CPU seconds |
| --- | ---: | ---: | ---: | ---: |
| 15 | 0 | 1.364617 | −0.035534 | 60.41 |
| 19 | 0.000002087 | 1.092897 | +0.012702 | 163.27 |
| 23 | 0.000002392 | 0.825342 | −0.076037 | 364.75 |

The first projected mixture is an exact saddle within the original finite family at the displayed arithmetic precision; the unprojected 100,000-iteration gap remains 2.3923e−9. Projection does not imply an improved unrestricted solution. Maximum discarded mass for either seat across the primary run was 3.495e−7.

The final full-game exploitability lower bound is **0.412671** per round, even though the restricted gap is about 2.4e−6. This still rejects useful equilibrium quality. A falling *lower bound* against these newly constructed heuristics does **not** prove that true unrestricted exploitability decreases, establish a convergence rate, or upper-bound the remaining error. Restricted self-play EVs are values of these particular policies, not the unrestricted game's value.

The deployed final player-0 policy puts about 31.0% root weight on the first generation's safest-posterior response and 16.2%/52.8% on two second-generation responses. Player 1 uses three history-aware components. These weights diagnose population adaptation; they are not recommended bluff frequencies. Different components can choose the same action at a given hand/history.

The primary run completed in 595.33 wall / 589.39 process CPU seconds, including initial matrix construction. It evaluated 713 deterministic policy pairs including the initial 225, each over 63,504 private deals. The most expensive pair visited 16,656 public nodes; the longest observed path had 21 bids. The explicit node budget was not reached. These are local Windows measurements; the sensitivity run overlapped part of the primary run, so wall-time differences are not a controlled performance comparison. No complete-process peak-memory measurement is claimed.

## Opponent-model sensitivity

A second full run changes the belief-model tremble from 0.02 to 0.10 while preserving thresholds, raise styles, projection cutoff and matrix iterations.

| Population | NashConv lower bound, tremble 0.02 | NashConv lower bound, tremble 0.10 |
| --- | ---: | ---: |
| 15 | 1.364617 | 1.363773 |
| 19 | 1.092897 | 1.093170 |
| 23 | 0.825342 | 0.826045 |

The second run's final deployed restricted gap is 2.6484e−6. It completed in 603.13 wall / 597.08 CPU seconds. Its last policy pair began before the 600-second between-pair budget check; completion slightly beyond 600 seconds is consistent with the documented guard, not a hard-deadline pass. Both runs complete all requested expansions.

The conclusion is stable for these two trembles: substantial residual exploitability remains after population adaptation. This does not establish robustness to arbitrary opponent-model errors, alternative response searches, more expansions or a different population basis. The four fresh policies are outside the current population but use the same predeclared construction class; they are not a broad independent best-response search or a held-out human model.

## Decision

The population approach is practical at this scale and produces a more responsive diagnostic strategy class. It remains scientifically inadequate for GTO recommendations. Costs rise sharply with nested history-conditioned references, and the current response construction uses claim truth instead of strategic continuation values. The next priority is stronger continuation-aware response search with independent small-game best-response checks, while retaining exact payoff evaluation where feasible. Simply adding more nearly identical probability thresholds is not a validated route to a full-game certificate.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_policy_space.py --rounds 2 --iterations 100000 --tremble 0.02 --mixture-cutoff 0.000001 --max-seconds 600
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_policy_space.py --rounds 2 --iterations 100000 --tremble 0.10 --mixture-cutoff 0.000001 --max-seconds 600 --output experiments/liars_dice/outputs/policy-space-tremble10.json
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Use `.venv/Scripts/python.exe` and `$env:OPENBLAS_NUM_THREADS='1'` in PowerShell. The JSON receipt retains source hashes, exact payoff numerators, every frozen reference's ancestry and weights, response parameters, restricted gaps, full-game response lower bounds, CPU/wall time and evaluation node counts. No hosted resources or external solver services are used.
