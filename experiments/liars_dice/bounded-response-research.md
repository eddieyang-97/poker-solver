# Continuation-aware response bounds

[Issue #45](https://github.com/eddieyang-97/poker-solver/issues/45) follows owner-merged #44 (`fd8056c`). It evaluates complete frozen 15/19/23-policy snapshots, preserving the confirmed rules and full public history. The new responses expose substantially more exploitability in the 23-policy snapshot. They do not produce an equilibrium strategy.

## Search and bound interpretation

The search conditions on the frozen opponent's actual behavioral action probabilities. There is no extra opponent tremble in this evaluator: trembles inside historical Bayesian components remain part of those components' definitions. `PopulationModel` computes sparse action probabilities from the root weights and own-action reach masks, including the original uniform behavior at own-zero-reach states.

At each responder node, opponent-hand mass is integrated **before** choosing a maximum separately for each own hand. Each legal raise is followed by every nonzero opponent response. Observed opponent bids update unnormalized opponent-hand mass; own actions introduce no additional opponent-hand likelihood. Player 1's value first integrates the opponent's opening, with a separate decision for each observed opening and own hand. No action selection observes the realized opposing hand or component identity.

At an unsearched responder state, an immediate challenge supplies a legal policy and its exact chance-weighted value L. Utility +1 supplies the optimistic value U; if a challenge is the only legal action, L=U. Weighted sums propagate opponent branches; componentwise maxima propagate own decisions. Thus L is realized by the extracted response and U upper-bounds unrestricted best-response value against this **fixed complete opponent**. Summing the two seats gives a NashConv interval; exploitability uses half that interval. The two maxima may choose different actions, so the upper endpoint is not a deployable strategy's EV.

Bounds are evaluated in float64, without outward-rounded interval arithmetic. They are structurally conservative search bounds, not formal machine-certified intervals or a certificate that the frozen strategy is GTO. Independent small-game checks tolerate 1e-12 arithmetic differences.

This use of feasible-policy lower values and optimistic continuation bounds is consistent with the general bounded online-planning approach surveyed by [Ross et al. (2008)](https://www.cs.cmu.edu/~sross1/publications/Ross-OnlinePOMDP-JAIR.pdf). Our finite-game implementation and tests provide the evidence here; no generic POMDP convergence claim establishes full-game equilibrium quality.

## Budgets and the retained failed allocation experiment

Depth counts own decisions. The node budget limits newly expanded own public nodes per seat and refinement pass; each expanded node still evaluates every legal action and nonzero opponent branch. It is not a wall-time or total recursive-model-call limit. Opponent observations are visited by descending reach mass, with action ID breaking ties; own actions follow the game's legal-action order.

The initial depth-first experiment could spend its entire budget below an early opening and leave other openings with immediate-challenge fallback. On the 23-policy target, player 1's depth-one response value was +0.696223, but independently restarting depth two with 32 nodes produced −0.421524. This was a valid but much weaker response, not a payoff bug. `outputs/bounded-response-unanchored.json` preserves that experiment and its source context (`0423c99`).

Refinement now retains the preceding solved policy and its bounds. Budget/depth frontiers use compatible incumbent subtrees when available. New decisions and bounds cannot worsen their incumbent counterparts; numerical checks enforce that invariant. Incumbents must match the exact game, guide, seat and frozen target object. Extracted policies retain full histories, use the chosen lower-value actions and challenge at other non-opening histories. Stored previous decisions are included in deployment. The budget therefore counts **additional work**, with retained-node counts separately reported.

## Measured results

All values below concern the same accepted frozen policies, not newly trained equilibria. All reported response lower values were independently replayed through the grouped full-rule evaluator for each positive-weight opposing component, over all 63,504 private deals per pair, and matched within 1e-10.

| Target population | Depth | Nodes per seat/pass | NashConv lower | NashConv upper |
| --- | ---: | ---: | ---: | ---: |
| 15 | 1 | 32 | 0.878877 | 1.904486 |
| 15 | 2, retaining depth 1 | 32 | 1.307736 | 1.894960 |
| 19 | 1 | 32 | 0.650340 | 1.849635 |
| 19 | 2, retaining depth 1 | 32 | 0.879369 | 1.845362 |
| 23 | 1 | 32 | 1.182534 | 1.947904 |
| 23 | 2, retaining depth 1 | 32 | 1.252292 | 1.947904 |
| 23 | 2, retaining depth 1 | 128 | 1.473141 | 1.928530 |
| 23 | 3, retaining depths 1–2 | 128 | **1.474843** | **1.928530** |

The last interval corresponds to exploitability approximately **[0.737421, 0.964265]**. Its width is still large, and its lower endpoint already rejects useful equilibrium quality. The earlier 0.825342 lower bound was a weaker diagnostic of the same target, not a claim disproved by a changed strategy. Prior valid lower bounds remain valid when a particular new limited search produces a smaller one; these tables do not rank true exploitability across populations.

The six-run 32-node study completed in 47.90 wall / 47.13 process CPU seconds, including toy checks and deployment replay. The 23-policy 128-node study completed in 180.62 wall / 178.06 CPU seconds. Its depth-two search alone used 22.06 / 55.02 CPU seconds for seats 0/1; depth three used 46.14 / 43.70 seconds and added little lower-bound improvement. Some runs overlapped, caches were reused across refinement passes, and these local Windows times are not controlled speedup measurements, peak-RSS evidence or hosted acceptance.

## Validation and reproduction

Five focused tests cover sparse likelihoods against the existing behavioral API, independent exact BR containment on one-face games, full-depth equality, policy realization, forced calls, budget boundaries, monotonic fixed-depth budget refinement, incompatible incumbents, and nested-opponent/full-rule deployment. The numerical driver additionally records 54 small-game comparisons against the independent tuple-tree evaluator. Larger budgets and horizons recover the exact toy BR values, while finite cuts retain bounds and executable policies.

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_bounded_response.py --generations 0 1 2 --depths 1 2 --max-nodes 32
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_bounded_response.py --generations 2 --depths 1 2 3 --max-nodes 128 --output experiments/liars_dice/outputs/bounded-response-budget128.json
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Receipts retain the frozen population's LF-normalized hash, executable/test hashes, budget/frontier statistics, exact deployment numerators, raw seat bounds and CPU/wall costs. Original #43 corpora remain unchanged. The initial allocation failure is retained separately; it is not relabelled as a successful refinement.

## Decision and handoff to #46

Proceed with this evaluator as a stronger quality diagnostic and offline response constructor. Wide upper bounds and expensive nested-model queries prevent an equilibrium-quality or query-time-serving claim. A useful next search improvement would allocate expansion to decision-relevant uncertainty, rather than relying on depth-first action order.

[Issue #46](https://github.com/eddieyang-97/poker-solver/issues/46) should first establish a pure full-history analysis baseline and measure exact compact rule tables and incremental frozen-policy state. The confirmed game has 168 syntactic bids, 144 openings and 150 reachable bid descriptions. Its contribution table has only 11 distinct face/mode views (face-one modes coincide), requiring 2,772 bytes as uint8 before metadata. This is not a strategy footprint or a measured total process-memory figure.

For the nested frozen policies, a marginal opponent-hand posterior plus the last bid is not established as sufficient: future action probabilities also depend on component reach and the reference models' internal beliefs. Test an exact streaming state against full-history replay before introducing lossy belief quantization. Keep raw full history as the input and provenance even if internal state is compressed. Exact rule math and declared-model challenge EV are credible prototype targets; continuation recommendations require resource and quality gates, and GTO-labelled actions remain unsupported. No MCP registration or deployment is authorized by this study.
