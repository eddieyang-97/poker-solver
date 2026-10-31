# Independent reproduction and full-rule feasibility

Scope: Issue [#40](https://github.com/eddieyang-97/poker-solver/issues/40), following archive PR [#41](https://github.com/eddieyang-97/poker-solver/pull/41), now merged as `27dfec1da6ea5b96921e4352537cd0097f215c0d`. Follow-on PR [#42](https://github.com/eddieyang-97/poker-solver/pull/42) targets `main`. Solver code, tests and measured outputs remain under this standalone directory; the existing required `river` CI job also runs the research tests, preserving the other numerical gates and required `test` aggregate.

Historical experiment provenance (31 October 2026): the measured working tree was based on archive head `f245b59ad9d34b4bb41075c0e2116e5b5a076f33`; main inspected at that time was `f59e8d7c5009845acc4f9a2c82364e104b80395d`. These hashes identify the original experiment context, not current merge status.

## Reproduction and audit

The archived Python enumeration reproduced exactly. Independently enumerated unordered hands with multinomial weights reproduce all ordered-roll frequencies; binomial counts independently verify the nonbonus categories. Fly face-four contribution frequencies are `0:1024, 1:2560, 2:2560, 3:1280, 4:320, 6:30, 7:2`. Zhai frequencies are `0:3125, 1:3125, 2:1250, 3:250, 4:25, 7:1`. These are exact **pre-action** probabilities under the default scoring implementation, which the owner subsequently confirmed on 31 October 2026.

The archived C++ solver ran with GCC 14.2.0, `-O3 -std=c++17 -Wall -Wextra -pedantic`, seed 761245 and 200,000 sampled deals. This machine measured 15.22 seconds training, versus the archive's machine-dependent 21.65 seconds. Its reported outputs reproduced to four decimals. `audit_baseline.cpp` exports all 4,096 history masks × seven hand types × thirteen padded action probabilities as little-endian doubles. `one_face.py` then independently traverses ordered bid tuples, computes expected utility and pools hidden types before each best-response choice.

| Exact evaluation of exported average policy | Value |
| --- | ---: |
| Player 0 self-play EV | 0.020681623 |
| Player 0 best response, own utility | 0.035810054 |
| Player 1 best response, own utility | −0.009121437 |
| Player 0 unilateral improvement | 0.015128431 |
| Player 1 unilateral improvement | 0.011560186 |
| NashConv (sum of improvements) | 0.026688617 |
| Exploitability (NashConv / 2 convention) | 0.013344309 |

A negative player-1 BR payoff is legitimate in a game favouring the opener. Adding the two own-utility BR values is the correct NashConv here; it does not mean either player's improvement is negative. The C++ evaluator does not let the responder observe the opponent's type. The seven contribution classes are lossless **only in that one-face game**.

No numerical mistake was found in the archived frequencies or the measured toy NashConv. Important limitations remain:

- The archive uses chance sampling with positive clipping after individual samples. Clipping a noisy estimate is nonlinear; do not import deterministic CFR+ convergence guarantees without analysis. The independently measured policy gap remains meaningful regardless of that training issue.
- Float regret/average accumulators, a single seed, rare contribution-seven hands and a finite training budget limit extrapolation. Longer runs are not certified by a short run's result.
- Collapsing hands to one face's contribution is invalid once other faces or modes can be bid. The archive omits those actions entirely.
- The Python script reports face four only and does not implement bid legality or action-conditioned beliefs. Its default scoring, including special all-ones treatment, was an assumption when the experiment ran and has since been owner-confirmed. Neither archived script validates arbitrary malformed input.

The original Python script is preserved byte-for-byte (including its unused import). The C++ archive receives only an explicit `return 0`, needed when its `main` is renamed by the audit wrapper; training, RNG and evaluation logic are unchanged.

## Solvers and validation

`one_face.py` includes a separate deterministic, alternating CFR+ reference: exact independent private-deal enumeration, opponent-reach weighting, aggregation over hidden types before clipping, and linearly weighted own-reach average policy. The independent evaluator is also checked against a forced-action analytical game and enumerated response plans in a two-opening game.

For the restricted face-four game with bids 3..5:

| Trainer | Iterations | Exact NashConv |
| --- | ---: | ---: |
| Exact CFR+ | 10 | 0.03394969 |
| Exact CFR+ | 100 | 0.00036975 |
| Exact CFR+ | 1,000 | 0.00000373 |
| Outcome sampling, seed 761245 | 1,000 / 10,000 / 100,000 | 0.183305 / 0.024766 / 0.003221 |
| Outcome sampling, seed 42 | 1,000 / 10,000 / 100,000 | 0.131289 / 0.036414 / 0.006275 |

The exact reference's final EV is 0.022641557. Sampled convergence is uneven and seed-sensitive, even here. This is evidence for the implementation on a small game, not proof of practical convergence on the larger game.

`mccfr.py` uses outcome sampling with signed cumulative regrets and regret matching, not clipped sampled CFR+. An iteration is one fresh sampled episode for each updating player. The updater explores with 0.6 uniform + 0.4 current strategy; the other player uses 0.05 uniform + 0.95 current strategy. Both retain full support, including when the target policy assigns zero probability to a history for some hidden hands. Tail importance correction applies to both seats. Full private hands and public histories are retained. No history merging, depth truncation, product imports or policy sharing between rule profiles occurs.

For a sampled action a at h with behaviour probability q(a), recursive child estimate X gives action estimate `X/q(a)`, node estimate `sigma(a)*X/q(a)`, and updater regret increment `opponent_reach/sample_prefix_reach * (action_estimate - node_estimate)`. Unsampled action estimates are zero. Average accumulation is `own_reach/sample_prefix_reach * sigma`. Chance samples from the true private-deal prior; its factor cancels in regret importance weights and is a fixed factor within each information set's normalized average. A trajectory-enumeration test directly checks the estimator's expectation. Other tests cover legal full-game play, normalization, zero-support policies, budget failure and unseen uniform fallback.

Method sources: [Lanctot et al., MCCFR (2009)](https://papers.nips.cc/paper_files/paper/2009/hash/00411460f7c92d2124a67ea0f4cb5f85-Abstract.html), and [OpenSpiel's outcome-sampling implementation](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/outcome_sampling_mccfr.py) as a cross-check of the estimator/average weighting. This implementation adds opponent exploration to support its simple average estimator across hidden histories; it is independently written, not a vendored OpenSpiel dependency or a claim of identical algorithm settings. A nonuniform trajectory-enumeration test checks both regrets and averages when one hidden hand gives the observed opponent action zero target-policy probability. The mathematical sources do not establish convergence of these finite runs.

## Measured full-game failures

The now-confirmed default rules allow 144 opening bids. Each of two seeds completed 10,000 iterations. Traced training memory was approximately 71 / 70 MiB, with 84,496 / 84,160 allocated information sets. Training plus model setup took 54.43 / 56.38 seconds while Python allocation tracing and other local checks were active. These are wall times, not isolated CPU measurements. Traced memory excludes some native/process allocations and is **not peak RSS** or a universal bound.

Frozen average policies were evaluated with 2,000 independent fresh games per opponent and seat. Baselines are uniform legal play and probability-only policies with challenge thresholds 0.3/0.5/0.7. The latter choose the legal bid with highest unconditional truth probability, breaking ties by lower quantity, higher face, then 飞. They ignore signalling and are not equilibrium strategies. They act using their own hand only. Evaluation RNG seeds are separate from training.

| Training profile | Seed | Self-play EV | Unseen decision fraction | 95% NashConv **lower** bound |
| --- | ---: | ---: | ---: | ---: |
| Full actions, default assumptions | 761245 | 0.005 | 69.54% | 1.7741 |
| Full actions, default assumptions | 42 | −0.032 | 69.76% | 1.7731 |
| Exclude face 1 | 761245 | 0.002 | 67.88% | 1.7681 |
| Allow mixed-hand 斋 bonus | 761245 | 0.005 | 69.54% | 1.7731 |
| All ones contribute six in 飞 | 761245 | 0.005 | 69.54% | 1.7741 |
| 飞-only opening, floor three | 761245 | −0.004 | 67.50% | 1.7831 |

These large lower bounds reject useful convergence; a near-zero self-play EV does not rescue the policies. The rare scoring alternatives often do not alter sampled training paths at this budget. Similar reported numbers therefore **do not establish insensitivity to those rules**. The example 44411 receives only fourteen root updates in each default seed and produces different opening frequencies; the frequencies in raw JSON are diagnostics, not recommendations.

The adjacent-action experiment keeps the smallest legal quantity for each face/mode (12 openings), preserving exact hands and full histories. Its deployed policy assigns zero probability to omitted jumps, but accepts all full-game opponent histories. Both seeds requested 50,000 iterations and hit the 100,000-information-set cap after only 5,070 / 5,046 complete iterations. The partial final episode is retained, explicitly labelled incomplete. Traced peaks were 67.07 / 62.59 MiB; measured training times 15.50 / 17.39 seconds. Maximum prefix importance diagnostics reached roughly `5.4e18` / `5.1e18`, exposing severe variance.

It beat uniform opponents but still lost heavily to probability-only opponents. Full-game NashConv lower bounds were 1.3591 / 1.3281. This restriction improves some finite-budget outcomes, but is insufficient. Its unseen coverage was not instrumented (null in output); no coverage claim is inferred.

Each individual match has a distribution-free Hoeffding interval for bounded ±1 outcomes. For each run separately, `summarize.py` applies a union bound over eight predeclared bot/seat tests, then sums the two candidate-response payoff lower bounds. Since exact best responses can do at least as well as those candidates, this is a 95% simultaneous **lower bound** on NashConv for that run. It is not a confidence upper bound, a point estimate of true exploitability, or a joint 95% statement across all research runs. Test sets were not used to select or update strategies. Dependence between opponent evaluations does not invalidate the union bound.

## Practical next step

Do not publish the sampled full-game frequencies as GTO advice. The owner confirmed all house rules listed in `RULES.md` on 31 October 2026; no rule-clarification blocker remains. The follow-on [guidance/control-variate study](guided-research.md) now tests probability-informed initialization and value baselines against posterior-aware responses. It improves coverage but still rejects useful convergence. The [finite-family study](family-research.md) exactly enumerates full-rule policy payoffs and reaches a tiny restricted gap, while outside opponents expose a full-game gap above 1.20. The original receipts above remain historical evidence, not replaced results.

The next priority is richer history-conditioned responses, potentially a policy-space double-oracle procedure or a public-belief/subgame approach with explicit continuation uncertainty. Last-bid-only state merging loses recall and requires explicit approximation validation. CFR/MCCFR with larger budgets alone, or a tiny gap inside a weak strategy class, is not a demonstrated solution to this history explosion.

`beliefs.py` already provides exact action-likelihood conditioning under an explicitly supplied opponent policy, including zero-support rejection. It does not infer a human's policy or repair the failed full-game equilibrium runs. The [strategy guide](strategy-guide.md) separates exact probability guidance from toy equilibrium findings and unvalidated approximation output.
