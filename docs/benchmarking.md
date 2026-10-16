# Independent river benchmarks

This development-only harness compares the restricted Python river solver with
the independently authored [noambrown/poker_solver](https://github.com/noambrown/poker_solver)
at commit `6a10442877ffc8fd28af93e16e279b9bbdd97b2a`. It is an open-source
reference comparison, not commercial-solver certification or full NLHE GTO.
No reference code or dependency is loaded by the hosted solver.

## Reference selection and provenance

The reference supports explicit weighted hole-card ranges, river-only play,
independent five-card-combination hand ranking, CFR+, customizable bet fractions,
all-in inclusion and a configurable raise limit. Its small Python reference path
can run offline in CI without paid tools, compiled binaries or credentials.
Its unmodified four-module subset and MIT license are under
`benchmarks/vendor/noambrown/`. `provenance.json` records the exact repository,
commit and SHA-256 checksums; the harness verifies them before importing it.
Hashes normalize CRLF to LF for Windows checkout portability. Import origins
are checked to avoid accidentally using an unrelated installed package.

The pinned reference's fast showdown path has a real custom-range limitation:
`vector_eval.showdown_values` indexes an opponent-only rank dictionary using the
acting hand's strength. Disjoint strength sets raise `KeyError`, including the
basic polarized fixture. Initial exploration failed nine of ten fixtures there;
the tied-board fixture passed. This was investigated, not scored as a product
failure or removed from the fixture corpus.

The benchmark explicitly uses the upstream **`use_naive_eval=True`** option and
`naive_eval.exploitability_naive`, which enumerate opponent hands and do not have
that lookup problem. Vendored files are unchanged. A regression documents the
fast-path limitation and checks the fallback result. This reference is itself
experimental; agreement does not prove both engines are universally correct.
No proprietary baseline has been used or redistributed.

### Issue #1 reference contract and actual CLI outcome

Read both Issue #1 comments, including the
[source-verified contract](https://github.com/eddieyang-97/poker-solver/issues/1#issuecomment-6219355562),
before this follow-up. [reference-polarized.json](../benchmarks/reference-polarized.json)
preserves its exact £100 JSON, including equal weights, `max_raises=0` and
`include_all_in=false`. On 16 October the following command was run against a
separate checkout at the pinned commit:

```powershell
.venv/Scripts/python .artifacts/upstream-reference/python/src/cli/run_river_exploitability.py --config benchmarks/reference-polarized.json --algo cfr+ --dump-strategy .artifacts/upstream-polarized-strategy.json
```

**Actual outcome: exit 1; no strategy dump.** The traceback ended at
`vector_eval.py:103`, `opp_summary.strength_ranges[hand.strength]`, with
`KeyError: (1, 13, 9, 8, 4)`. The CLI selects the fast evaluator and exposes no
naive-evaluation flag. Its advertised command is therefore incompatible with
this fixture at the pinned revision. This was not reported as a passing CLI run.

The unmodified `VectorCFRTrainer` has a supported `use_naive_eval=True` option.
Our small development-only wrapper calls that implementation in a **fresh
isolated Python process**, without importing `poker_spot`. It emits upstream-style
ordered `hands`/`weights`/`profile`, raw exploitability checkpoints and training
costs. It verifies source hashes and import origins. Reproduce the successful
exact-configuration run with:

```powershell
.venv/Scripts/python -I benchmarks/reference_worker.py --config benchmarks/reference-polarized.json --iterations 4000
```

[reference-polarized-output.json](../benchmarks/reference-polarized-output.json)
retains the actual output (including the observed process ID and timing).
The report's usual currency scale of 100 is not used in this particular command;
the reference's integer chip is £1, exactly as the issue specified. The generic
adapter uses cents and verifies the same game after scaling. The test compares
configuration, source commit, normalized weights and every ordered policy row
against this snapshot. Its `1e-9` frequency tolerance permits floating-point
replay differences in the **same pinned algorithm and iteration schedule**, not
differences between valid equilibrium mixtures or external solver versions.

The first exact run returned QJ bluff frequency **49.9712359%**, KK call frequency
**49.9987098%**, OOP check frequency **99.9999432%**, and raw exploitability
**£0.0075206912** at 4000 iterations. Thus its normalized NashConv is
**£0.0150413824**, twice raw exploitability. The snapshot includes checkpoints
25–4000; the initial raw exploitability was £1.3555064. Convergence need not be
monotonic at every iteration.

## Matching the game

`benchmarks/fixtures.json` contains ten explicit fixtures: full-/half-pot
polarized games, dry merged ranges, monotone, paired, four-flush and four-straight
boards, a board-play tie, short-stack capping and a three-size £505 case.
Weights, blockers and low-reach branches are included. Concrete combo lists
avoid sharing the product's shorthand-range expansion with the reference;
these fixtures do not independently validate the shorthand grammar.

Every fixture explicitly declares no rake, no raises and no implicit all-in
action. Both players receive the same initial pot fractions, with bets capped
by the effective remaining stack. The adapter walks the entire legal reference
tree and checks its action sets, combo sets and uniquely mapped bet amounts
before importing a product strategy. Duplicate/collapsed bets, nonzero rake,
implicit all-ins, extra raises and unsupported histories are rejected.

The reference uses integer chips. The adapter scales currency by **100**, and
rejects any pot, stack or bet that would need rounding at that scale. It does not
silently round or add actions. These fixtures fit that representation; arbitrary
sub-cent inputs are unsupported by this benchmark, even if the product accepts them.

The reference awards the starting pot to the winner and measures payoff relative
to future contributions. Subtract half the starting pot from each player's EV,
then divide by 100, to match the product's zero-sum half-pot convention.
The reference reports exploitability as half the sum of unilateral improvements;
multiply it by two and divide by 100 to compare **NashConv in currency units**.
Compatible hole-card pairs are weighted by the product of the two range weights,
conditioned on no shared cards. Independently normalized marginal ranges preserve
that joint distribution after conditioning.

## What is checked

The runner trains the product and reference separately; all reference training,
including the richer-tree experiment, runs in the isolated worker with a
120-second process deadline. It validates exported hand sets, row probabilities,
weights and action ordering before importing them, and checks raw upstream
exploitability against the independently evaluated normalized NashConv.
It also imports the
product's averaged strategy into the reference tree and evaluates that *same
policy* using the reference's independent showdown and best-response routines.
This separates evaluator/normalization bugs from different approximate equilibria.

- Full hand-rank agreement across fixture hands, plus 300 deterministic random
  seven-card hands and explicit quads/double-trips/wheel cases in unit tests.
- Root EV and NashConv from independent evaluation of the product policy must
  agree with its rounded output within 0.000051 currency units.
- Conditional action EVs for the same policy must agree within `1e-9` of pot;
  reachability/undefined-value masks must match too.
- Each engine must meet the existing analytical-regression gate of NashConv at
  most **0.5% of pot**. The difference between independently trained root EVs
  must lie within the sum of their measured gaps, plus `1e-6` of pot for output
  rounding. That gap bound is a zero-sum value bound, not a fitted target.
- Both polarized cases explicitly compare QJ bluffing, KK calling, AA value
  betting and OOP checking with analytical frequencies. The absolute frequency
  gate is 0.04, retained from the existing analytical test, not selected to match
  this reference. Analytical root EV is `-P*B/(2*(P+B))`; each computed value must
  be within its measured NashConv plus rounding error. The Markdown report shows
  both engines beside the analytical values; full checkpoints and profiles are
  retained in JSON.
- Strategy L1 distances, each hand's joint node reach, conditional action EVs,
  and action regret against the reference opponent are recorded. Best-action
  agreement is reported only when the reference's best/second-best gap exceeds
  0.5% of pot. These are diagnostics, not exact-frequency pass criteria.
  Average joint reach below `1e-5` is flagged as rare. No unconditional node
  quality guarantee follows from a small global gap.

The joint-reach diagnostic includes **both** players' path probabilities and
compatible chance weights. It is different from the product tool's current
`own_reach_probability`. Benchmark diagnostics do not add a hosted API field.
Timing uses `perf_counter`; peak allocation uses `tracemalloc`. That is Python
allocation tracking, not operating-system RSS or a hosted latency measurement.
Both fields cover training only, excluding initial game/range construction and
later evaluation. Allocations made before tracing begins are not included.
For the worker, the peak is the largest traced allocation across training
segments between checkpoints; checkpoint evaluation and process startup are excluded.
Tracing adds overhead, so the timing fields are not general performance claims.

Fault-injection tests corrupt only the product's hand evaluator and verify that
the differential checks fail. Configuration tests reject deliberately mismatched
trees and nonrepresentable bet amounts. Tolerances were not widened to match
reference outputs; the fast-path failure remains explicitly documented above.

## Reproduce and inspect

Using the project's existing development environment:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark.py --output .artifacts/benchmark --sensitivity
.venv/Scripts/python -m unittest discover -s tests -v
```

Defaults: 1500 product iterations and 4000 reference iterations. The command exits
nonzero on a failed case and emits JSON plus a Markdown delta table. GitHub
Actions runs it offline and uploads both reports even when a comparison fails.
Inspect `.artifacts/benchmark.json` for all per-hand/node diagnostics. A recorded
local run is versioned in [benchmark-results.json](benchmark-results.json), with
a [human-readable table](benchmark-results.md). Inputs, local core and harness
hashes are included so stale reports can be identified. Runtime/allocation fields
will vary across machines; numeric comparisons are deterministic within floating
point and convergence limits.

To refresh the reference, download the four source files and license from the
exact upstream commit recorded in `provenance.json`, verify their SHA-256 values,
and retain them at the same relative paths. To select a new upstream version,
audit it, review license/configuration changes, update the manifest and pinned
commit deliberately, then regenerate and investigate the full report. Do not
silently modify vendored algorithms or alter a baseline to hide a discrepancy.

## Separate tree-sensitivity experiment

`--sensitivity` solves the same dry merged fixture with the reference alone,
first without raises and then permitting **one extra raise** using the same
fractions. Upstream counts the opening bet as raise 1, so `max_raises=2` permits
that extra raise. This experiment is explicitly excluded from correctness gates.
It does not add raise support to the product.

The first recorded run changed OOP root EV from approximately £34.7803 to
£35.3927 in a £100 pot (about **£0.6124**, or **0.6124% of pot**). The respective
NashConv values were about £0.00123 and £0.00067. This is one example of modeling
error from the omitted actions, not an estimate of typical real-world error.

The initial ten-fixture run and [GitHub Actions](https://github.com/eddieyang-97/poker-solver/actions/runs/38962276458)
passed. Its largest independently trained root-EV
difference was about **0.00111% of pot**; same-policy action EVs agreed to around
`5.2e-15` of pot. Broader/larger ranges, additional fixtures, another reference
implementation and commercial comparisons remain useful follow-ups. The current
corpus is not an exhaustive proof, a production security audit, or validation of
assumed live-population ranges.

**Subsequent milestone:** independently configure and cross-validate with
TexasSolver after verifying its exact river/no-raise tree and export semantics.
No TexasSolver execution, proprietary reference or gold-standard claim is part
of this milestone. Keep the corpus at ten until the current harness has further
review and useful failure evidence; expansion to 20–30 is intentionally deferred.
