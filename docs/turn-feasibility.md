# Turn delivery feasibility — Issue #21

This is a local engineering study, not a turn MCP implementation or release.
The product solver, hosted river tools, authentication, budgets and deployment
configuration are unchanged. All games are synthetic post-session studies with
explicit independent arrival assumptions; they do not infer actual populations.

## Starting evidence and experiment

The [PR #10 resource study](turn-resource-study.md) recorded both 24-by-24,
two-size maximum games fitting on one Ubuntu runner (13.285 / 13.589 seconds),
and both hitting the actual 20-second deadline on another. The recent Issue #28
CI measurements again retain both maximum timeouts. A successful profiling
command does not mean its individual probes passed. This rules out admitting
the full local dimensions merely because a faster sample exists.

The existing six Linux probes remain in CI, unchanged. This study adds four
existing independently checked strategic games: weighted dry-board collisions,
a four-flush, trips/full-house runouts, and a draw-heavy two-size game. Complete
boards, exact expanded weights, pots/stacks, sizes and iterations are retained
in each report. They are deliberately narrow questions about selected combos,
not realistic full-width ranges or general turn support.

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark_turn_feasibility.py --output .artifacts/turn-feasibility
# Windows: explicit unlimited measurements; never Linux budget acceptance
.venv/Scripts/python scripts/benchmark_turn_feasibility.py --unlimited --output .artifacts/turn-feasibility-local
```

The new disposable worker installs the existing **20s CPU / 384 MiB AS** limits
before NumPy/product imports. The parent **20s wall** deadline includes launch,
input parsing, imports, tree construction, 2,000 iterations, checkpoints/BR,
full-policy and action-EV collection, JSON/gzip/file output, final response and
reaping. Stage markers remain available on timeout. CPU is measured through the
reported snapshot; the kernel limit remains active during final response/exit.
Linux `/proc` retains peak/current AS and RSS; Windows resident measurements
are explicitly unlimited. Unexpected errors fail the study. Expected timeouts,
memory failures, signals and nonconvergence remain visible, not hosted passes.

Two solves per game use separate processes. First/subsequent samples may differ
in OS filesystem cache; neither is a measured Free Render cold start. Lookup
also runs in a new process with the same limits, reconstructs/validates the
complete game/tree, then performs three reads/verifications/decodes/projections.
Reported first/subsequent lookup stages distinguish process startup from warm
in-process decoding. No service, keepalive, queue or cache daemon is added.

## Provisional admission and convergence

The deliberately conservative *input candidate* is at most **four combos each,
one size per street and exactly 2,000 iterations**, within the existing no-raise,
no-rake model. Larger/different classes are measured or rejected, not relabelled
as safe. To count as an observed candidate, both independent-process Linux
samples must converge under the unchanged **0.5%-of-pot NashConv** gate and fit
**10s wall / 10s CPU / 192 MiB peak AS**. This reserves half the existing budget;
it is an experimental margin, not a universal runtime guarantee or a replacement
hosted limit. Convergence must also be checked per request, not inferred from
dimensions. The two-size games remain outside this conservative candidate even
if individual timings fit. A separate 20-iteration run demonstrates whether a
fast result is converged; it is never admitted to the candidate or catalog.

Every admitted stored policy is replayed in the existing independently built
turn reference and the product model; root EV, individual BR bounds and NashConv
must agree within the unchanged **1e-8 chips**. Stored action EVs and null support
are checked on fixed-policy replay. Full policies stay in ignored/CI artifacts.
The ten independently trained games and all 188 separately trained no-turn-bet
river subgames remain separate CI gates. This reference is in-repository and
shares the pinned evaluator/CFR+ family; it is not an audited external solver.
Low-reach conditional EVs can remain inaccurate despite a small root gap.

## Exact reuse experiment and proposed receipt

The experiment writes small, deterministic gzip files under `.artifacts/` only.
It is not a shipped solution library (#25), upload reader or operational cache.
No product module imports it. Each file contains:

- Versioned full-game identity: ordered four-card board, both complete ordered
  expanded combo lists and exact binary64 weights after card removal, starting
  pot/effective stack and per-street sizes; no rake/raises, exact 44-per-deal chance.
- Engine source hashes, algorithm/EV baseline, accepted iteration count and
  Python/NumPy versions. Runtime identity intentionally prevents unverified
  cross-runtime reuse; training probabilities are not known to be bit-identical.
- All 48 public river contexts, full average policy tensors at every node,
  all hands' fixed-policy action EVs, null support, own/opponent reach, effective
  chip amounts, checkpoints, root/BR/NashConv diagnostics and checksum.

Only JSON field ordering and expansion already performed by the solver are
canonicalized. Preserve board/hand order, absolute weight scale and size order;
do not presume weight scaling, suit isomorphism, proportional money amounts or
different iteration settings yield interchangeable stored profiles. Unknown
versions, missing nodes, wrong shapes/actions, corrupt digests, nonfinite or
nonconverged results fail closed. A missing identity is `not_found`; there is
no nearest match and no automatic live miss fallback. A future library needs
immutable trusted manifests, explicit `invalid_artifact`/`not_verified` errors,
bounded decompression/output and an independently verified record-admission
process; the local experimental reader is not that security boundary.

Hero and river filters are output-only views of the same full policy, **not**
conditioning the turn on a future card. Regression tests compare frequencies,
EVs, nulls and reach with the direct solver for both players/all runouts. Lookup
measures all range hands; changing ranges or tree is a different game.

The declared sensitivity set has **20 synthetic queries**: three output views
of each of four catalog games, then eight held-out changes to board, weight,
pot, stack, turn size, river size, iterations or combo support. With all four
verified entries it yields **12/20 exact hits, 0/8 held-out hits**. That 60% is
constructed reuse, **not measured organic user coverage**. On miss no solve is
executed; its cost is rejection plus a later independently admitted live solve
or new offline training/validation. All query configurations remain in the report.

The Windows unlimited sample stores four games in 200,465 compressed bytes
(1,563,486 JSON bytes); eight full training runs complete without a harness
failure. All-hands/all-rivers projected JSON is much larger: **505,167–1,310,307
bytes per game**. Full process lookup, including three complete projections,
takes approximately 0.7–1.9 seconds locally. These measurements include validation
and decoding, not a claim of sub-millisecond hosted lookup. A future MCP contract
must bound views; compression alone does not solve response-size limits.

## Decision and future release gate

General hosted turn solving: **no-go** under the admitted local limits and
current measurements. The full-width model is already unsupported, and maximum
local inputs have repeatedly timed out. No hardware upgrade is proposed.

A small immutable lookup-only product is **deferred**: repeated hand/runout
views of a deliberately fixed game benefit, but there is no evidence of useful
organic exact-hit demand. Different natural-language range or sizing assumptions
quickly produce misses. #25 should proceed only with a declared demand sample
showing meaningful repeated complete games, rather than manufacturing a catalog
and counting its own examples as usage. Files are small; coverage is the concern.

If Linux measurements retain the provisional small-game headroom, the recommended
path for #26 is **bounded live-only investigation**, not deployment. Require:

1. A reviewed schema with exact game semantics and strict combo/tree/body/output
   bounds, explicit low-reach/insufficient-convergence states and no range inference.
2. Measured existing Free Render startup/import/serialization/reap capacity and
   cold starts, plus negative timeout/AS/concurrency recovery under unchanged
   20s/384 MiB/one-worker/no-queue/rate limits. CI is not Render capacity.
3. Full unchanged river/turn/reference tests, negative query/output projection
   tests and exact source/request/result receipts. Do not relax convergence to
   fit latency or omit hard cases from evidence.
4. Explicit owner approval to add a hosted tool, then OAuth and actual
   authenticated ChatGPT acceptance, unchanged existing tool regressions and a
   tested disable/rollback path. A passing study does not authorize registration.

If that bounded product is not useful or fails real capacity tests, keep turn
local. No live-only, lookup-only or hybrid production architecture is approved
by this feasibility PR.
