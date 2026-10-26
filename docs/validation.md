# Numerical and hosted acceptance — evidence index

This is the **current evidence map**, not an append-only PR/CI journal. Do not conflate **(a) computed values in a specified game**, **(b) correctness relative to independent numerical or analytical oracles**, **(c) modelled opponent behavior**, and **(d) real hosted/user-client acceptance**. A passing numerical regression or standalone Linux resource receipt proves neither realistic poker ranges nor Free Render latency.

Historical implementation chronology, exact CI-run narratives and superseded gates stay in their Issues/PRs. A frozen [pre-consolidation validation record](https://github.com/eddieyang-97/poker-solver/blob/920d2bf2c54226caf16c8572bb531a9b2a91a489/docs/validation.md) remains available for original detailed observations and heading permalinks. The machine-readable results and test fixtures below are **retained in-repository**, rather than removed as mere history.

## Current verification boundaries

| Area | What has evidence | What it does **not** establish |
| --- | --- | --- |
| **River** | Ten fixed same-tree cases versus a pinned independently authored reference; independent root/action EV evaluation; analytical pot odds and equilibrium symmetry; explicit sensitivity and reference failure conditions. [Method](benchmarking.md), [full results](benchmark-results.json) and [summary](benchmark-results.md). | Correctness of unmodelled raises, population arrival ranges, all NLHE or an externally certified GTO solver. Frequencies at close/low-reach nodes are not stable prescriptions. |
| **Other river references** | Actual standalone TexasSolver rank-class execution and strict offline replay; original concrete-combo rejected and **two weighted-blocker reference convergence FAILs** retained. [Compatibility](texassolver.md), [raw output](texassolver-results.json), [blocker analysis](texas-blocker-audit.md), [failures](texas-blocker-results.json), [averaging ablation](texas-averaging-experiment.md). | Cross-validation of original single-combo weights/trees, or a passing Texas reference on the failed weighted cases. Offline replays are not fresh external tool runs. |
| **Local river raises and hand review** | Exact-size pot ledger, legal raises/refunds, one additional raise, isolated reference training, scenario reconstruction and optional review. [Raise contract](river-raises.md), [results](river-raises-results.json), [exact size](raise-review-results.json), [hand examples](hand-review-results.json). | A hosted raise tool, node locking, calibrated opponent tendencies or observed conditional-line EV without a declared model. |
| **Action-model range explorer** | Supplied hypotheses with chronological action conditioning, joint blockers/folded-player card removal, decimal/zero-support checks. [Contract](range-explorer.md), [results](range-explorer-results.json). | A calibrated population model or automatic substitution of correlated posterior marginals into an independent-range solver. |
| **Local turn correctness and feasibility** | Local two-street experiments and independent in-repository strategic reference; 44 river outcomes per legal turn deal; decomposed independent river cases; bounded Linux resource/failure data. [Turn](turn.md), [independent](turn-independent.md), [reference results](turn-independent-results.json), [decomposition](turn-decomposition-results.json), [performance](turn-performance-results.json), [feasibility](turn-feasibility.md), [resource study](turn-resource-study.md). | External certification, broad weighted range/tree coverage or accepted live-service capacity. Retain genuine timeouts/nonconvergence and any Windows-unlimited labels. |
| **Turn reuse/estimation #25** | Strict exact/suit-equivalent checks, independent target-policy comparisons, short fresh solves, held-out cases and deliberately abstaining weak bounds. [Study](turn-reuse.md), [results](turn-reuse-results.json). | General near-neighbour EV reliability or improved hosted game support. Owner-merged [PR #35](https://github.com/eddieyang-97/poker-solver/pull/35) does not itself authorize a lookup catalog or heuristic strategy. |
| **Hosted turn #26** | A separate opt-in turn factory and local/CI validations. Actual deployed Free Render runs eventually computed the pinned game; **parent headroom and warm-client latency gates still failed**. [Pilot contract](turn-pilot.md), [actual timeout study](turn-hosted-timeout.md), [raw postmerge results](turn-postmerge-hosted-evidence.json), [release criteria](turn-pilot-release.md). | Stage B acceptance, consistent sub-10s headroom or broadly available ChatGPT turn analysis. Existing river tools remain supported separately. |
| **Hosted river** | Real Auth0/OAuth SDK diagnostic and owner-private ChatGPT calls with inspectable tool outputs, including all four £505 river solves and three call calculations. [Actual responses](hosted-acceptance-results.json), [separate local reproduction](chatgpt-acceptance-reproduction.json). | Multi-user/friends readiness, automatic OAuth refresh/revocation, Claude end-to-end invocation or reliable response times across cold starts. |

## Numerical gates and reproducibility

- For product/no-raise river changes: `python scripts/benchmark.py --sensitivity`, retaining exact same-game trees/rounding, independent evaluation, analytical checks and sensitivity as separately labelled model experiments. The original 10-case root-EV difference was at most about **0.00111% of pot**; policy evaluation differences approximately `5.2e-15` of pot. Source provenance and limits are in [benchmarking](benchmarking.md). These are **corpus observations**, not universal bounds.
- The original pinned external-reference upstream CLI failed with `KeyError` for its rank-set case; the pinned brute-force alternate ran successfully under independent process isolation. [Fixture/response](../benchmarks/reference-polarized-output.json). Never quietly change trees/tolerances to count an incompatible result as a pass.
- The weighted Texas blocker audit yielded two **FAIL** NashConv results approximately **£1.5907 / £1.1317 in a £100 pot** against the unchanged **£0.50** gate. Its dedicated diagnostic intentionally exits nonzero; passing a replay regression means the failure is accurately preserved, **not** that Texas passed. [Audit](texas-blocker-audit.md).
- Relevant turn script entry points are listed in [AGENTS.md](../AGENTS.md). Preserve source and fixture hashes, full-policy/BR oracles, exactly **44** legal rivers per deal, the **48** decomposition candidates, correct chance/compatible mass, independent training, frozen game IDs, failure/resource receipts and unchanged **0.5%-of-pot** turn convergence gate. Short fresh solves, measured lookup costs and transferred-policy bounds are different claims.
- The required GitHub Actions `test` result is a **fail-closed aggregate** of all numerical/artifact jobs, not a partial fast pass. [CI contract](ci-throughput.md) and [time/result receipts](ci-throughput-results.json). Latest head must pass before merge; deployment and authenticated acceptance are separate.

## £505 checked-river acceptance study

Board `Ks,9s,5h,Td,Ts`; BTN/IP `AsJh`; pot £505, effective remaining stack £450.
Prior streets and opponent tendencies were not supplied. All ranges are therefore
**illustrative weighted arrival hypotheses**, including value, showdown hands
and missed draws, rather than reconstructed facts. They do not use a revealed
opponent hand as the entire range. `KdQd` is a separate representative OOP
bluffcatcher query, not a statement of the opponent's actual cards.

Reproduce with `python scripts/acceptance.py`. Exact input ranges and complete
computed outputs are committed in [acceptance-results.json](acceptance-results.json).
The three OOP variants differ in full-house and flush weights: some traps, more
traps and fewer traps. Both players have the same allowed sizes. OOP can bet;
read the IP action conditional on its solved check. This is not a solve against
an externally forced checking range.

| OOP range | Allowed bets (£) | AsJh after check: bet frequency | Action EVs relative to £252.50 baseline | NashConv / pot |
| --- | --- | --- | --- | --- |
| Some traps | 450 | 100% jam | Check −252.50; jam −197.99 | 0.001% |
| More traps | 450 | 100% jam | Check −252.50; jam −230.14 | 0.001% |
| Fewer traps | 450 | 100% jam | Check −252.50; jam −169.70 | 0.001% |
| Some traps | 166.65 / 303 / 450 | 12.64% / 62.93% / 24.43% | −41.59 / −41.59 / −41.55 | 0.002% |
| More traps | 166.65 / 303 / 450 | 7.18% / 92.71% / 0.10% | −166.58 / −166.54 / −167.98 | 0.002% |
| Fewer traps | 166.65 / 303 / 450 | 8.77% / 89.91% / 1.32% | −11.13 / −11.03 / −11.31 | 0.003% |

The multi-size action EVs are often very close. These rounded frequencies are
computed average strategies, not precise or unique prescriptions. Adding sizes
also changes OOP's lead/check behavior and therefore its conditional checking
range. In the multi-size “some traps” case KdQd checks only 0.13%, so its later
bluffcatch frequencies at that node deserve particular caution. A small global
gap does not certify every rare-node strategy.

As blocks nut-spade flush combinations; Jh removes J-containing hands. Blockers
remove potential value and bluffs, and their net effect depends on the supplied
ranges and strategies. The observed small-tree preference for bluffing cannot
establish a live-population recommendation, especially if opponents trap more,
call too much, or arrive with different ranges. Those are hypotheses requiring
new computed assumptions, not measured population facts.

Separately, `evaluate_river_call` evaluates KdQd facing £450 against the exogenous
betting range `AsQs,QsJs,Js8s,99:0.5,55:0.25,QJs:0.5` plus five possible bluffs
`AsJh,AsQh,AsQc,AhQh,AhJh`, each at the indicated weight:

| Each bluff's weight | Call EV minus fold | Decision under that range |
| --- | --- | --- |
| 0.1 | −£337.60 | Fold |
| 0.5 | −£24.24 | Fold |
| 1.0 | +£203.49 | Call |

Required equity = 450/1405 = **32.0285%**. These are exact weighted showdown
calculations under assumed betting ranges, not equilibrium frequencies or proof
that the population uses any of those bluff rates. They are separate from the
solver-derived response nodes saved in the JSON.


<a id="direct-authenticated-connector-acceptance-after-reconnect"></a>

## Hosted river — direct authenticated connector acceptance after reconnect

Later on 16 October, invoked the actual **Poker Solver Hosted** connector tools
directly in this chat and retained their returned `structuredContent`, rather
than an assistant's summary. The connection initially requested authentication,
then returned `UNAUTHORIZED` / requires reauthentication. The owner explicitly
reconnected it in their signed-in ChatGPT account. Another auth prompt was
accepted, followed by a network timeout at 20 seconds. A public `/health` request
then took about 29 seconds; after this startup delay, authenticated calculations
succeeded. No scope, allowlist or security check was weakened.

Both diagnostic calls succeeded: the exact call test returned 1/3 equity and
zero call EV; the analytical polarized solve returned 50.01% air betting, 49.93%
calling and NashConv £0.0371. Then all four full £505 solves and all three
bluff-weight call evaluations succeeded sequentially. **Every input and every
returned result field matched `chatgpt-acceptance-reproduction.json` exactly**
(JSON numeric equality, without a tolerance). This closes the raw-payload gap
for those seven calculations. The earlier range-order diagnostic remains local
reproduction/owner-reported evidence; it was not repeated through the connector.

[hosted-acceptance-results.json](hosted-acceptance-results.json) records the actual
seven requests/results plus two analytical diagnostics, endpoint, deployed
Python commit, service version, issuer and app binding. It contains no bearer
tokens, authorization codes, passwords or owner subject. The service remains
version 0.2.0 at `a4ba8e750582899642e468ba6c55d82bcc787d2f`; subsequent benchmark,
packaging and evidence commits require no production redeployment.

The £505 study above is directly confirmed by hosted
payloads. For KdQd facing £450 into £505, the three hypothetical betting ranges
returned call EV −£337.60, −£24.2424 and +£203.4884, with required equity 32.0285%.
Those are exact calculations against supplied betting weights, not an inferred
opponent strategy. The full-range CFR solves remain no-raise/no-rake
approximations, and closely tied action EVs do not justify precise live mixtures.

**Remaining operational gates:** explicit reconnect recovery now has positive
evidence, but automatic refresh is neither configured nor verified. Provider
grant revocation/access removal and a second-account connection remain untested.
Auth0 Google login still uses development keys. Free Render cold starts can
exceed the connector's request timeout, so this is a working private pilot with
availability limits. Do not describe it as reliable always-on hosting or a
friends beta that has passed multi-account acceptance.


## Further acceptance and attribution

- Direct hosted tool payloads, separate SDK harness responses, owner-supplied conversational summaries, fixture/CI verification and raw benchmark artifacts are **different evidence tiers**. Compare the exact request, returned structured fields, environment, relevant SHA and numerical gates before saying a case is verified.
- Actual OAuth/allowlist configuration and current release procedure: [hosting](hosting.md), [releases](releases.md), [distribution flow](distribution-flow.md). Existing private ChatGPT work is verified; **friend account** and Claude OAuth+live-tool acceptance require distinct real connected-client evidence. [PR #37](https://github.com/eddieyang-97/poker-solver/pull/37) separately proposes Claude onboarding documentation; a registered client or successful authorization preflight does not prove actual tool calls.
- Use [Issues](https://github.com/eddieyang-97/poker-solver/issues) for unresolved conditions and [PRs](https://github.com/eddieyang-97/poker-solver/pulls) for dated implementation/CI decisions. Add a new permanent scientific record only when it materially improves reproducibility or changes the present accepted contract; do not append another dated changelog here.
