# Expanded local turn validation and resource study

After PR #9 merged as `dd9249297300bc859101859e324de5d9de554599`, this
development-only milestone expands strategic turn coverage and measures the
unchanged engine against the existing hosted budget numbers. No product solver,
MCP registration, worker, deployment, authentication or hosted limit is changed.

## Broader correctness coverage

The independent corpus grows from six to ten games. Four new fixtures use
three or four concrete combos per side: weighted dry-board collisions,
four-flush holdings, trips with full-house/quads runouts, and a draw-heavy board
with two sizes on both streets. They contain 11–14 compatible private deals
and up to 39,019 independently constructed concrete nodes. Each compatible
deal still has exactly 44 legal rivers. These exercise the reference's existing
four-combo bound; they do not establish correctness at the product's 24-combo
bound or constitute an externally audited comparison.

Bidirectional policy comparison now checks each player's best-response bound
separately, as well as root EV and raw NashConv. This prevents offsetting errors
in the summed gap from hiding a disagreement. All use the unchanged `1e-8`-chip
numerical allowance. Convergence remains 0.5% of initial pot; trained-value,
cross-play, exact analytical and frequency gates remain unchanged. The two
engines still train separately from configuration alone.

A deterministic seed (`1379`) additionally generates 15 fully mixed policies
per new fixture, 60 total. Both models evaluate every policy's root values,
individual best responses and NashConv, independently of convergence or a
trained profile's near-zero branches. Regression tests retain hidden-hand
pooling, exact tree/cent matching and product fault injection.

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark_turn_independent.py --output .artifacts/turn-expanded
.venv/Scripts/python -m unittest discover -s tests -p test_turn_independent.py -v
```

See [versioned outputs](turn-independent-results.json) and
[comparison table](turn-independent-results.md). The original six fixtures and
their analytical targets are retained. Earlier PR #9 evidence remains in Git
history; differences in raw report hashes reflect new fields, fixtures and
runtime metadata and are not a comparison of arbitrary file bytes.

## Exact Linux budget probes

`benchmarks/turn_resources.py` is a standalone development worker. In `limits`
mode it sets both soft and hard `RLIMIT_CPU` to 20 seconds and `RLIMIT_AS` to
384 MiB **before importing NumPy or product code**. The parent imposes a
20-second wall deadline including process/import startup, calculation, both
hand queries over every river, serialization and exit. This is a separate
probe with the existing budget numbers, not integration with the hosted runner.
The production river worker has a different startup/import path.

Each completed probe records actual `getrlimit` values, per-stage timings,
whole-process CPU through the post-calculation snapshot, resident memory,
Linux `/proc/self/status` peak/current virtual and resident bytes, payload
size, platform, Python/NumPy, thread settings, PID and convergence diagnostics.
An observed fit requires parent wall and CPU within their budgets and peak
virtual bytes at most 384 MiB. The kernel limits also remain in force through
serialization/exit. A separate field reports the unchanged convergence gate;
completing quickly with an unconverged policy is not a usable solve.

The six explicitly retained configurations are:

| Workload | Combos per player | Sizes per street | Iterations |
| --- | --- | --- | --- |
| Original deep dry maximum | 24 | 2 | 2,000 |
| Original weighted four-flush maximum | 24 | 2 | 2,000 |
| Smaller private ranges | 4 | 2 | 2,000 |
| Intermediate private ranges | 12 | 2 | 2,000 |
| Fewer actions | 24 | 1 | 2,000 |
| Less training | 24 | 2 | 500 |

Both maximum inputs remain identical to the original performance corpus.
The others are explicit subsets/sizing/iteration ablations in the report,
not replacement acceptance fixtures. No smaller workload is silently declared
the new supported hosted limit.

Timeout kills and reaps the worker. Reports retain elapsed time and partial
stage markers and omit unavailable solve/memory results. Nonzero signals stay
labelled by signal; SIGKILL alone does not prove CPU rather than another cause.
Caught `MemoryError`, unsupported platforms and harness errors are distinct.
Resource failures remain in `resource_failures` and readable rows. The study
command exits nonzero for harness errors; expected resource failures are data,
not hidden or converted into passing hosted acceptance. CI tests enforce a
successful small Linux probe and a real rejected oversized allocation.

```powershell
.venv/Scripts/python scripts/benchmark_turn_resources.py --profile --output .artifacts/turn-resources
```

Windows reports Linux probes as `UNSUPPORTED`, without creating limit-fit
claims. This machine has no installed Linux runtime. The
[Windows record](turn-resource-windows.json) therefore contains six unsupported
probes and one separately labelled instrumented execution. CI performs actual
fresh Linux probes and retains full JSON/Markdown under `turn-resource-study`,
including failed probes. Use each report's source hashes and platform; do not
infer a Linux outcome from Windows or from a green study step alone.

## Separate profiling and remaining gates

The optional `--profile` run uses cProfile on the original deep 24-by-24,
two-size, 2,000-iteration workload. It has a separate 180-second development
deadline, **no CPU/address-space cap**, and records that `limits` is null.
Instrumentation changes timing; profile wall/CPU values are not budget evidence.
It retains top functions by self and cumulative time with call counts.
Cumulative times overlap and cannot be added as independent work.

The recorded Windows instrumented process took 14.194 seconds. Largest self
times were `_walk` (3.429 seconds), `update_strategy` (2.528), NumPy reductions
(2.444) and `c_einsum` (2.397). These identify measured candidate costs, not
promised speedups. Fresh uninstrumented original maximum workloads also all
completed in [six local repeats](turn-performance-coverage.json), 12.03–13.35 seconds parent wall, maximum resident
peak 34.82 MiB. These remain observations, not portable worst-case bounds.

The local suite runs 75 tests, with one real Linux allocation test explicitly
skipped on Windows. Larger private-information regression coverage and a
development Linux resource probe strengthen validation. They do not establish
Render capacity, concurrency, bounded hosted payloads, authenticated MCP or
ChatGPT turn acceptance. Prior Ubuntu workloads exceeding 22 seconds remain
valid historical evidence; a faster later sample does not erase them. Turn
remains local, and general full-range/richer-tree correctness remains open.
