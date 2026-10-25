# Issue #26 Stage B: hosted timeout investigation

**Decision: no-go for accepting the current bounded live-turn pilot on Free
Render.** After owner-merged PR #33, the pinned game now computes twice, but
still fails the unchanged latency/headroom gates. Keep #26 open. Recommend
restoring the river-only entry point while investigating; that production change
requires owner approval and was **not performed**.

## Post-merge hosted retest — 25 October 2026

PR #33 merged at `39e979c6bc0fd0b9cdcb10d5a5f3f9cdb7226e4f` on 24 October
22:00:14 UTC. Exact main [CI 40136664337](https://github.com/eddieyang-97/poker-solver/actions/runs/40136664337)
passed all five jobs, exact required `test` after its four dependencies, all
eleven artifact groups and **191/191 Linux tests, no skips**. PR-head
[CI 40121852759](https://github.com/eddieyang-97/poker-solver/actions/runs/40121852759)
also passed. Main resource ZIP SHA-256
`aa6452211b9a94a6315204d351ab98df6e1b4146862309a43b6e5bf50217866b`
and all eight pilot source/request/result/limit receipts verify. CI parent time
was 0.363–0.966s, CPU 0.341–0.943s, peak AS <=119.832 MiB and SDK <=10,819
bytes. These measurements remain separate from actual Render capacity.

Existing `checksPass` automatically deployed that merge: deploy
`dep-dbeio1cs728c73clkmeg`, Live 24 October 22:08:04 UTC. Readback confirms
the existing hosted factory, Free plan and one worker/instance. Public smoke
verified exact SHA, health/readiness 200 and unauthenticated MCP 401. This
investigation performed no production configuration change or deploy trigger.

Two warm authenticated connector calls used the exact pinned game and all three
views, including the future `9c` projection. [Raw results and checks](turn-postmerge-hosted-evidence.json)
retain original server text to preserve JSON spelling for result hashing.

| UTC start, 25 October | Client wall | Parent wall | Worker CPU | Peak AS | Acceptance |
| --- | ---: | ---: | ---: | ---: | --- |
| 08:57:44 | 18.114s | 16.995s | 2.468s | 115.270 MiB | FAIL latency/headroom |
| 08:58:15 | 17.621s | 17.022s | 2.405s | 115.270 MiB | FAIL latency/headroom |

Both return `source=computed_on_demand`, `status=computed`, identical result
SHA `7d127276a0a3be869c33e0324eafc53e78757ddceff16a70f8c48672b3c47f59`,
NashConv 0.00527675 chips and valid request/game/source/Linux-limit receipts.
The calculation passes the existing 20s/384 MiB hard bounds and convergence gate.
Both **fail** 10s parent headroom and 15s warm delivery. Do not relabel them
timeouts or insufficient convergence; valid computed output is retained despite
failed release acceptance. No strategy precision follows for low-reach rows.

CPU/worker-wall is 0.14962 and 0.14597, further supporting limited CPU availability.
Direct cgroup throttling counters remain unmeasured. A second optimization would
need about 38–39% less **total** CPU work to approach 10s at an ideal sustained
0.15 CPU, before allowing contention. There is no measured candidate achieving
that. CI sub-second solves do not override these real hosted failures.

Both exact river baselines were freshly checked: call EV 955 in 2.699s, and the
polarized solve in 5.586s with full existing economics/policy/schema validation.
An earlier turn attempt paused for reauthentication and is excluded from timing.
The public checks and prior initialization primed these calls; no fresh idle
cold-start or automatic OAuth lifecycle acceptance is claimed.

Stop full-subset acceptance testing after this mandatory pinned case fails;
additional cheap examples cannot repair that result. No further solver rewrite,
cache, relaxed numerical/resource target, infrastructure upgrade or rollback
was performed. Next decision remains owner-approved river-only rollback versus
a separately scoped optimization/product/hosting change.

## Initial deployment and calls — 24 October history

PR #32 merged as `3f3aeb093c75c62dbb2665122f8d1fbe58c5a0e4`; its
[post-merge CI](https://github.com/eddieyang-97/poker-solver/actions/runs/40026617454)
passed five jobs. Render deploy `dep-dbdt93dg1s2s73b0up60` became Live on
23 October 2026 at 21:42:36 UTC, with the explicit hosted factory, Free plan,
one instance/worker and `checksPass`. Public smoke on 24 October verified that
SHA, `turn-pilot-v1`, health/readiness 200 and unauthenticated MCP 401.

All times below are UTC. [Retained evidence](turn-timeout-hosted-evidence.json)
contains the fresh raw tool text, exact requests, numeric Render metric series
and startup logs; it contains no credentials or client IPs.

| Probe | Observation | Interpretation |
| --- | --- | --- |
| Original pinned game, 23 October (reported in #26) | ~20.757s; `timeout`, `Turn calculation exceeded its wall-clock limit`; no strategy/receipt | Actual server worker deadline |
| 24 October 08:43:38 pinned retry | 20.273s; connector `McpServerError: Connection timed out` | Startup-related transport failure, not a solver receipt |
| 08:45:19 warm pinned retry | 21.631s; same server worker `timeout`; no strategy/receipt | Reproduced computation failure after startup |
| 08:46:14 river call recovery | 2.254s; exact baseline call-minus-fold EV 955 | Legacy call tool still works after timeout |
| 08:46:46 existing `turn_allin` diagnostic | 10.118s client; 9.554s parent, 9.290s worker wall; 1.396 CPU seconds | A different, cheaper admitted game computed |

The all-in diagnostic uses a £100 pot/stack, KK versus equally weighted AA/QJ,
one pot-sized turn bet and **no river betting**. It is not substituted for the
£100 pot/£200 stack, 0.7-weight QJ, half-pot turn/river pinned request.
Its source/request/game/result hashes, 2000 iterations, unchanged convergence
gate and actual Linux 20s CPU / 384 MiB AS receipts verify against the deployed
sources. NashConv is 0.02218518 chips; peak AS 115.277 MiB, peak RSS 42.031 MiB.
This one sample passes existing headroom but proves neither repeatability nor
acceptance of strategic river continuation. The original post-activation river
solve success is historical; only the river call was rerun in this investigation.

An earlier authentication prompt was accepted after a long user interaction;
that elapsed interval is excluded from all performance conclusions.

## Likely causes and remaining uncertainty

**CPU availability is the leading explanation for the warm failure.** Render
reports a 0.15 CPU limit. The successful child's measured CPU/wall ratio is
**0.15028**, consistent with that allocation. Its imports alone took 1.402s
wall; validation/training/BR/projection/receipt took 7.888s. Recorded ordinary
Linux weighted-dry samples consumed about 3.3–3.5 CPU seconds. At 0.15 CPU,
that work would need about 22–23 seconds before contention. This scaling is an
estimate, not a measured completion time for the failed game.

The failed child's CPU and progress were not returned. Render's 30-second
metric samples are service-wide, dilute shorter bursts and contain no cgroup
throttling counters. Thus quota enforcement versus other scheduling contention
is not conclusively isolated. Original sampled service memory peaked around
113 MiB against ~512 MiB; the repeat window peaked around 113 MiB too. No OOM
or restart was observed during the warm failure; sampling cannot exclude every
transient memory peak. The error path itself indicates the parent wall deadline,
not the usual memory/worker-crash/output-limit classifications.

The deadline wraps child spawn, imports, parse, solve, BR, projection, encoding,
pipe read and reap. There is one solve and no waiting queue. OpenBLAS/OMP/MKL
threads are already one. OAuth/network/idle startup precede this timer and
cannot directly produce its specific worker-timeout message.

**Startup is a separate delivery problem.** For the 08:43 retry, Render logged
the start command at 08:43:51.924 and startup completion at 08:44:05.744, after
the connector had timed out at 08:43:58.841. This supports a startup-related
failure, consistent with Free idle wakeup, rather than a timed solver result.
An exact idle interval/trigger was not independently recorded, so this is not a
formal cold-start acceptance run. [Render's Free documentation](https://render.com/docs/free)
describes spin-down after 15 minutes and roughly one-minute wakeup. Training
optimization cannot fix that boundary. No keepalive was added.

## Candidate changes and validation approach

Training dominated the original local profile. Alternating CFR+ consumes only
the updating player's returned values; the prior traversal calculated both.
The candidate visits the same tree/runouts but omits unused terminal products
and reductions, refreshes only strategies whose regrets changed (with a full
first refresh), and uses one addition for binary child sums. Both reaches remain
available for linear own-reach averaging. Diagnostics, BR and conditional-EV
collection keep the existing two-player traversal and shared terminal ledger.
No cache, fewer iterations, range/tree substitution or numerical gate change.

Exact differential tests compare each update and complete 2000-iteration
training with the old traversal/schedule: regrets, current/average strategies,
strategy sums, checkpoints, every node's conditional EV and reach. They include
blockers, zero support, tiny weights, all-ins, no betting, two sizes and a
24-combo pass. Independent strategic-turn and decomposition gates remain the
separate correctness checks; parity with old code is not external validation.

The development command below loads the actual deployed `turn.py` from the
pinned Git object, checks its SHA-256 and the shared rank evaluator, then compares
five cases in one runtime. It alternates variant order and reports raw CPU/wall
samples. These timings exclude imports/network and impose no kernel limits.
They cannot be used as hosted latency or a universal bound.

The [recorded final candidate comparison](turn-training-results.json), Windows
Python 3.14.8 / NumPy 2.5.4 with one BLAS thread, passes exact parity for all
15 paired samples (five cases, three repeats). Median baseline/candidate wall
seconds were: pinned 8.048/4.363, singleton 7.629/4.125, weighted-dry 8.015/4.300,
weighted-collision 8.316/4.563, terminal all-in 2.344/1.302: **1.80–1.86x**.
Raw samples retain a much faster first pinned pair (1.413/0.955); local timing
variation is not hidden or used to select favorable results. The earlier scratch
profile also measured faster absolute times. These observations support removing
wasted computation, not predicting a specific Render completion time.

```sh
OPENBLAS_NUM_THREADS=1 python scripts/benchmark_turn_training.py --output .artifacts/turn-training.json
OPENBLAS_NUM_THREADS=1 python scripts/benchmark_turn_pilot.py --output .artifacts/turn-pilot
OPENBLAS_NUM_THREADS=1 python scripts/benchmark_turn.py
OPENBLAS_NUM_THREADS=1 python scripts/benchmark_turn_independent.py
OPENBLAS_NUM_THREADS=1 python scripts/benchmark.py --sensitivity
```

The pinned Git object must exist locally; fetch the PR #32 merge if using a
shallow checkout. No baseline source is downloaded or substituted automatically.

Timeout observability also needs repair: the existing INFO outcome records are
suppressed by the documented default Uvicorn logging configuration, and child
stderr is discarded. The candidate takes a bounded best-effort Linux proc
snapshot before killing a timed-out child and emits one WARNING **after reap**:
parent wall, child CPU, peak AS/RSS only. Missing/exited/malformed counters are
unknown. It logs no request, hands, tokens, environment, process name or exception
text; it adds no solution receipt and preserves the timeout response/cleanup.

## Options and release decision

1. **Recommended now:** keep turn analysis local and restore the river-only
   hosted entry point after owner approval. Current release gates have failed.
2. **Worth a bounded trial after review and explicit deployment approval:** the
   optimization plus diagnostic logging. Require repeated actual Free Render
   calls of the pinned game and all four declared pilot questions, full receipts,
   <=10s parent/CPU headroom, <=192 MiB AS and <=15s warm delivery. At 0.15 CPU,
   the 10s headroom target allows only about 1.5 CPU seconds in ideal conditions;
   a faster CI run alone is insufficient. Retest startup/reconnect separately.
3. **Different product, separate decision:** narrower explicitly named games or
   an exact precomputed catalog (#25), only if useful. One cheap successful
   diagnostic is not justification to silently narrow or substitute the game.
4. **Paid compute, later and only if approved:** may address CPU and idle-start
   limitations, but still requires actual acceptance and does not justify larger
   game limits. No upgrade or new infrastructure is proposed for this PR.

If the candidate cannot meet the unchanged hosted targets, conclude live-turn
no-go on this infrastructure. A larger compiled/vectorized training project is
a separate investment, not grounds to relax gates. Issue #26 remains open;
merging, deploying, disabling the pilot or changing production settings requires
the owner's explicit approval in this investigation.
