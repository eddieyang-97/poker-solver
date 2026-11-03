# Frozen-policy analysis and state representation (#46)

**Limited go for a local, model-conditional analysis prototype. No-go for GTO-labelled actions or deployment acceptance.** Exact streaming reproduces the tested frozen policies, but those policies remain highly exploitable. The new interface returns legal actions, the current claim's prior/model probability and immediate challenge EV; it abstains from continuation recommendations.

This study follows [Issue #46](https://github.com/eddieyang-97/poker-solver/issues/46). It is stacked on #45 / PR #47 and reuses that implementation for quality evaluation. PR #47's deeper 23-policy response interval is approximately [1.474843, 1.928530] NashConv, using structurally conservative float64 bounds rather than formal interval arithmetic. That is research evidence, not accepted hosted functionality.

## What is small—and what is not

| Representation | Measured or enumerated size |
| --- | ---: |
| Ordered hands / weighted multisets per player | 7,776 / 252 |
| Weighted private pairs / ordered chance mass | 63,504 / 60,466,176 |
| Syntactic bids / opening bids / reachable bids | 168 / 144 / 150 |
| Distinct per-hand contribution views | 11 |
| uint8 contribution views | 2,772 bytes |
| Views + bid-to-view mapping + quantities | 3,108 bytes |
| Full terminal truth table / bit-packed table | 10,668,672 / 1,333,584 bytes |
| Full-history information sets | approximately 3.54e47 |
| Canonical policy snapshot JSON | 3,478 bytes |
| 23-policy streaming state's NumPy arrays | 23,688 bytes |

The last three byte figures are different objects, not total process memory. The artifact reconstructs Python/NumPy objects, prior policy tables and a fixed reference-model DAG. Eleven views suffice because fly/zhai face-one counts coincide. Quantity-one bids and quantity-two fly bids are unreachable; quantity-two zhai bids are reachable via 3 fly → 2 zhai.

Direct contribution lookup was faster than packed-table lookup on the 1,000-query local probe (about 4.03 versus 9.36 microseconds, both including equality checks). The construction probe took about 91 ms and includes two identical Game constructions; it is not the single-instance load measurement below. The full truth table is generated for verification but **not persisted**. We retain the small canonical policy snapshot and recompute rule tables. All contribution entries are independently checked against raw-dice scoring, with chance multiplicities enumerated from all 7,776 ordered rolls. Packed/direct truth queries also agree.

## Exact sufficient state for this frozen family

The input always retains the complete public history. Internally, streaming maintains:

- Own-action consistency masks for each component, possible private hand and seat.
- The two seat-specific belief vectors for each distinct nested reference-model/tremble pair.
- The external observer's opponent posterior and support flag for each seat.
- The last bid and turn index.

Before consuming an observed bid, all model likelihoods are calculated from the **old** state. Only then are the actor's component masks and the opposite seat's belief vectors updated. The root mixture integrates its eligible components before evaluating the next action. These updates reproduce the original recursive definitions by induction over public bids: identical initial priors/masks, identical choices and likelihoods, then identical mask/Bayes updates. Shared reference-model beliefs avoid duplicating identical vectors across response variants.

This sufficiency argument is specific to the recorded acyclic family of prior and Bayesian components. It does not establish that a marginal opponent-hand posterior plus last bid suffices for arbitrary strategies, human opponents or the unrestricted equilibrium game. No histories are merged in exact mode and no posterior values are quantized.

Tests compare all component choices and selected behavioral likelihood vectors against the recursive reference at both seats across the 15/19/23 populations, including legal off-policy histories. A separate 78-case posterior comparison, including a 150-bid stress history, found maximum absolute difference **0**. Full small-game EV and exact BR/NashConv also match the independent tuple-tree reference.

## Lossy controls and concrete history collisions

`last_bid` retains only the current bid and actor parity, resetting masks and beliefs. `last_two` retains the last two bids and parity: the earlier bid initializes the boundary and only the later observation updates the reset state. Earlier bids are forgotten. An initial pilot counted the boundary bid as an extra memory slot; that definition was corrected before the committed receipts were generated. These are explicitly altered behavioral policies, not exact cached versions of the full-history policy.

Under the declared 23-policy model, Hero holds **12222** at seat 0:

| Legal history | Current bid | Immediate challenge EV |
| --- | --- | ---: |
| Hero: 4×2 fly; opponent: 4×4 fly | 4×4 fly | −1 |
| Hero: 3×4 fly; opponent: 4×4 fly | 4×4 fly | +1 |

Both histories have positive opponent-model support. Their opponent-hand distributions have L1 distance 2. Hero's previous bid changes what the opponent's response reveals. A last-bid-only lookup cannot distinguish them. Another supported pair ending at 4×6 fly yields challenge EVs +0.275346 versus −0.548851 for the same Hero hand. A third retained example changes the posterior without changing the chosen hand's challenge EV. These are conditional statements about an explicit frozen model, not calibrated human advice.

On the exact-solvable quantity-3..7 one-face fixture, full-history/streaming NashConv is 0.364749; last-bid and last-two policies give 0.363990 and 0.395367. Lossy changes can accidentally improve a particular weak policy as well as worsen it; that does not make the representation lossless.

The full-game study evaluates every representation in the unabstracted confirmed game using #45's depth-one, 32-node response evaluator. Each response is additionally tested with 1,000 fresh-roll games per seat, seed family 460046, with individual Hoeffding intervals retained. The sampling checks are payoff checks, not full-game BR certificates.

| Population | Full stream lower / upper | Last bid lower / upper | Last two lower / upper |
| --- | --- | --- | --- |
| 15 | 0.878877 / 1.904486 | 0.878877 / 1.904486 | 0.878877 / 1.904486 |
| 19 | 0.650340 / 1.849635 | 0.527681 / 1.846778 | 0.705830 / 1.890923 |
| 23 | 1.182534 / 1.947904 | 0.646426 / 1.902453 | 1.256917 / 1.947904 |

These are float64 NashConv bounds against the corresponding frozen behavioral policies. Smaller lower bounds do not prove stronger play. The exact-stream results reproduce the same-budget #45 results. The shallow probes do not supersede #45's stronger lower bound for the original 23-policy model. None supports GTO recommendations.

## Latency, memory and cache evidence

Five fresh Windows/Python subprocesses each loaded the snapshot, processed 161 typical/stress queries from 30 seeded games, then repeated the longest-history query 100 times. `OPENBLAS_NUM_THREADS=1` was used.

- Fresh-process first supported response: median **493 ms**, p95 **505 ms**, maximum **508 ms** over five additional subprocesses. This includes Python/import startup, model load, one request, output and process exit; it excludes network/provider time.
- Model load: 245–280 ms. This includes rule-math/model reconstruction and fingerprint checks; it excludes Python process startup.
- Mixed query corpus: median 3.59–4.15 ms, p95 10.20–12.57 ms; maximum 169–213 ms. These include input validation and copying returned data.
- Repeated 150-bid query: median 1.25–1.36 ms. Validation and deep-copy cost remain on a cache hit.
- Full subprocess elapsed time: 2.70–2.85 s, **including the entire workload**, not just cold-start latency.
- Peak process working set: 64,827,392–66,289,664 bytes (about 61.8–63.2 MiB), measured with Windows `GetProcessMemoryInfo/PeakWorkingSetSize`. The parent quality/precompute process peaked at 158,044,160 bytes; that is not the query-worker footprint.
- Each cold query pass had 154 misses and 7 hits; the cache is bounded to 64 results. These are full-query results keyed by immutable per-instance model identity, sorted Hero hand, seat and complete history.

The separate posterior-only replay comparison found that naive whole-history streaming was **slower** than a warmed recursive implementation: medians 4.34 ms versus 1.06 ms, excluding API validation/serialization. Streaming eagerly updates model state even after external support vanishes, whereas the posterior-only recursive comparison can stop early. This is not a demonstrated runtime speedup; it demonstrates an exact finite-state representation with explicit memory accounting.

A corpus-only likelihood table reduced repeat posterior calculations to about 4.4 microseconds median, but 44 new prefix/action entries were needed on 58 held-out queries. Its 121 vectors occupied 243,936 bytes before Python/key overhead. Keys include model ID, actor, full public prefix and observed action; misses compute the exact likelihood. That diagnostic table is unbounded and is **not** the shipped query cache. No finite corpus cache covers arbitrary beliefs/histories.

Worker peak memory includes corpus-generation policy caches as well as the analyzer/query cache; it is an observed whole-process peak, not an isolated analyzer allocation count. No Linux address-space, Free Render cold-start, provider or authenticated client measurement occurred. Windows working set is not the hosted 384 MiB Linux address-space constraint. Deployment feasibility remains unverified even though local analysis is fast.

## Pure prototype and proposed later MCP contract

`Analyzer(snapshot_bytes, generation=2).analyze(hero_hand, hero_seat, history, model_id)` is a pure deterministic analysis call with bounded memoization. The artifact is canonical JSON with content checksum, format/rules identity, input-receipt provenance and LF-normalized implementation hashes. A mismatch rejects loading; it never substitutes a nearby strategy. Checksums establish content identity, not a cryptographic signature from a trusted publisher.

Input requires exactly five integer dice, a valid seat to act, complete legal bid history (maximum 150 bids), and the exact loaded model ID. Bid dictionaries contain only quantity/face/mode. Unknown fields, illegal openings/transitions, wrong turns, incompatible models and malformed bids are rejected. The API accepts no opponent private hand. Zero model support produces an explicit status with no posterior or model EV; it never silently resets to the prior. Tiny float-rounding deviations remain possible in probability/EV scalars.

Outputs contain legal actions, canonical input/provenance, opponent posterior with a declared hand ordering, current own contribution, pre-action prior truth probability, model-conditional truth probability and immediate challenge EV. The opening has no challenge value. Continuation output is `abstain: strategy_quality_not_validated`; no GTO recommendation is supplied. Returned objects are detached copies so callers cannot corrupt cached results.

A later `analyze_liars_dice_v1` tool could expose this contract with a server-selected allowlisted immutable snapshot. It must distinguish rule math, model-conditional challenge EV and separately gated continuation estimates. The next release issue would need product/API approval, bounded body/output design, Linux/Free Render resource evidence, authenticated client tests and rollout/rollback acceptance. This PR registers no MCP tool, changes no existing hosted behavior and performs no deployment.

## Reproduce and decision

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_analysis_research.py --games 1000 --cold-samples 5
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_replay_comparison.py
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_cold_query.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Use the project virtual environment; PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. `analysis-model.json` is regenerated from the unchanged accepted population receipt. `analysis-research.json` and `replay-comparison.json` retain costs, source fingerprints, counterexamples, exact small-game values and full-game bounds/sampled checks. The replay-comparison and cold-first-query drivers were added after the primary run started and have their own source receipts. All 39 standalone tests passed locally, along with repository/research Ruff, compileall and whitespace checks.

**Go:** standalone exact rule math and explicit-model posterior/challenge analysis. **Limited go:** model-specific streaming state and bounded full-history memoization; retain recursive replay as the correctness reference and benchmark before claiming a speedup. **No-go:** GTO-labelled actions, general continuation recommendations and hosted acceptance. Stronger strategy quality remains #45/research work; compact storage alone does not resolve it.
