# Same-target full-history response refinement (#49)

This follows owner-merged #58. It evaluates **all six retained 60-CPU-second
reference/axis policies**, seeds 490061/62/63, without training or changing them.
The question is whether search effort and allocation strengthen their response
bounds. Changing a bound on one target is not changing that target's strength.

## Calibration and selected design

The versioned calibration uses the first declared axis target, seed 490061,
before selecting the uniform main schedule. It reproduces #58's baseline with
both the original action API and the exact cached adapter. Its depth-two,
32-node incumbent refinement takes 24.78 search CPU seconds across the seats,
raising NashConv's lower endpoint by only about 0.001. The receipt and both
response plans remain in `outputs/response-calibration*`.

The single-order cached/uncached timings are not controlled speedup evidence;
cached search was slower in this calibration. The adapter's acceptance is
probability/search parity, not a performance promise. It caches immutable
action-probability views only for the validated frozen one-bid target class.
Representative *legal full histories* construct the cache; abstract last-bid
keys alone can have the wrong turn parity. Response nodes, decisions and
unnormalized opponent-hand likelihoods continue to retain **full histories**.
This does not assert that a last bid is sufficient for general opponent models.

The main experiment keeps every target and selects these stages before running:

| Label | Depth (own decisions) | Own-node cap per seat/pass | Incumbent |
| --- | ---: | ---: | --- |
| base32 | 1 | 32 | none; must reproduce #58 |
| breadth128 | 1 | 128 | base32 |
| legacy128 | 2 | 128 | breadth128 |
| priority128 | 2 | 128 | breadth128 |

The last two branches start from the **same** incumbent. Legacy uses legal
action order. Priority visits actions selected by the incumbent for the most
own-hand prior mass first, then breaks ties in legal order. At previously unseen
response nodes it uses legal order. This is an allocation heuristic, not a
best-first optimality claim. It never observes a realized opposing hand. It
still integrates every legal action and every positive opponent branch at each
expanded node, pools opposing hands before maximizing separately for each own
hand, and retains the same legal frontier policy and optimistic bounds.

Changing order can alter ties and which nodes get expanded. Equal node caps do
not mean equal CPU, unique new histories or strategy quality. Caps count work
in the current pass, including re-expansion; inherited decisions are separately
reported. At cutoffs compatible old subtrees remain usable. Both branches must
preserve their incumbent's lower/upper directions. Historical search/trainer
sources and all accepted corpora stay unchanged.

## Policies, independent replay and envelopes

Each seat/stage exports a lossless pure response: full public histories map to
252 own-hand action IDs. No opposing hand or component ID is a policy input.
Other non-opening states challenge; an absent opening uses the first legal bid.
Plans bind the rules, seat and target probability fingerprint; strict loading
checks histories, action legality, duplicates and wrong-target/rule contexts.
The experiment reloads every saved plan before evaluating it.

Independent exhaustive replay reconstructs target probabilities through the
**scalar policy API** and scores raw dice separately from the search guide.
It propagates own/opposing hand masses through complete public histories;
terminal values use independent 8x8 count-pair sums. This enumerates weighted
chance/actions in float64, not sampled chance or outward-rounded arithmetic.
Limits are 200,000 public-node entries / 10 wall seconds, checked between work
units. On exhaustion it aborts and records cost/statistics **without returning
a partial value**. Every completed replay must realize the stored lower value
within 1e-10. Every stage also gets independent 2,000-game scalar raw-dice replay,
with its individual Hoeffding 95% interval. Permitted statistical misses and
replay budget failures are retained; intervals are not simultaneous claims.

The final envelope takes each seat's greatest valid feasible lower value and
smallest valid optimistic upper value across **all four completed stages**.
It records which saved plan attains each lower endpoint. Combining requires
identical full target-file fingerprints, probability fingerprints and game
semantics; bounds from different targets are never pooled. Sum the two seats
for NashConv, divide by two for exploitability. The best lower/upper sources
can differ, and an upper value is not a deployable policy's EV.

All six historical baselines must reproduce within 1e-10. Each loaded target's
probability hash is checked before/after analysis. The whole-study 1,800-second
guard checks between search/replay work units; node caps are **not hard wall or
total model-call limits**. Running/completed/incomplete receipts persist with
costs, frontiers, retained nodes, raw bounds, failures and plan hashes. Whole
Windows process peak and CPU/wall cost include loading, search, replay and
exports. No provider/client/hosted acceptance follows from this local study.

## Reproduce and validation scope

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/calibrate_response_refinement.py
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_response_refinement.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Use the project environment.
The main run has fixed node/depth budgets, not machine-dependent CPU training
stops. Source hashes are LF-normalized; target and exported plan hashes identify
raw bytes. Resource variation can affect whether an exact replay completes;
never substitute a truncated replay value for an exact result.

Focused tests check scalar/cache parity, cached/uncached search agreement,
independent exact BR containment and full-depth equality on declared one-face
games, extracted-plan realization, incumbent preservation for both algorithms,
raw rule scoring including sensitivity flags, off-policy completion, resource
abstention, plan validation and same-target envelope provenance. The one-face
fixture supplies a numeric bid-rank adapter without changing its rules.

Full-rule targets still arise from one-bid training, not equilibrium-certified
full-history training. The response search is full-history; its finite cuts do
not prove a target is near equilibrium. Structural float64 bounds are not formal
interval certificates. Keep all prior valid same-target bounds. Disjoint
well-supported intervals could establish a model-specific ordering; overlapping
intervals cannot, and lower lower endpoints alone never establish stronger play.
No GTO frequencies, general continuation advice, model promotion or deployment
is authorized by this experiment.

## Recorded outcome

All six targets and all four stages completed. The historical baselines
reproduce exactly at the reported float64 endpoints. The final envelopes are:

| Frozen target | Baseline NashConv interval | Refined envelope | Envelope width |
| --- | --- | --- | ---: |
| axis / 490061 | [1.526193, 1.858363] | [1.534652, 1.854380] | 0.319728 |
| reference / 490061 | [1.576370, 1.856903] | [1.584541, 1.852715] | 0.268175 |
| axis / 490062 | [1.537325, 1.863479] | [1.545431, 1.860504] | 0.315073 |
| reference / 490062 | [1.597697, 1.865259] | [1.605928, 1.861953] | 0.256024 |
| axis / 490063 | [1.516602, 1.857830] | [1.525106, 1.854547] | 0.329441 |
| reference / 490063 | [1.598441, 1.859825] | [1.606241, 1.856360] | 0.250118 |

The lower endpoints rise 0.007800–0.008504 and upper endpoints fall
0.002974–0.004188. These are tighter measurements of the **same vulnerable
policies**. All intervals still overlap across methods; no unrestricted
strength ranking or near-equilibrium conclusion follows.

Legal-order depth-two refinement attains every final lower endpoint and every
seat-one upper endpoint. Seat-zero upper endpoints never improve; the envelope
retains their baseline provenance. Incumbent-priority refinement produces a
weaker NashConv lower and upper endpoint on **all six targets**, despite starting
from the same breadth128 anchor and using the same node cap. Its total search
CPU is 149.30 seconds versus legal order's 282.30 (ratio 0.529). Equal node caps
leave different continuation costs; this is a quality/cost tradeoff, not a
controlled equal-CPU comparison. The heuristic contributes no envelope endpoint
and is not selected as an improvement. Raw results and plans remain available.

Every one of the 48 main plans was saved, reloaded and exhaustively replayed
within its declared limits. Maximum lower-value discrepancy is 9.99e-16;
replays visit 840–77,132 public nodes and total 53.125 CPU seconds. Both
calibration plans also pass exhaustive replay. All 48 sampled replays fall
within their individual 95% intervals. Agreement validates realized lower
values; it does not independently certify optimistic upper bounds or make
those statistical intervals simultaneous.

The main run uses 713.24 wall / 708.625 CPU seconds and 185.41 MiB Windows
process peak working set. Calibration separately uses 50.06 wall / 49.609 CPU
seconds and 177.75 MiB peak. These are local costs, not hosted resource limits.
All six original target files and prior corpora are unchanged. The receipts
retain source hashes, target fingerprints, all 50 plan hashes, search/frontier
statistics, replay outcomes and measured costs.

The useful delivery is a verifiable response-plan/replay path and modestly
tighter same-target bounds. Before blindly increasing search budgets, evaluate
allocation guided by unresolved upper/lower gaps or batched frontier work on
exactly evaluable fixtures, with independent BR containment and measured cost.
The incumbent-action heuristic alone has not earned that role. Training-budget
sensitivity remains a separate research question; this experiment keeps every
target fixed. Neither a larger training representation nor product model
promotion is accepted by these results.
