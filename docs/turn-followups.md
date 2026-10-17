# Local turn validation follow-ups — 17 October 2026

PR #7 merged as `3e3a5ae7e72240851cc3d3a4678d6f35cf27fa96`. These follow-ups
add development validation and measurement without changing either solver or
registering/deploying a turn tool.

## Independent river-subgame decomposition

Disable all turn betting. The two forced checks leave pot, stack and arrival
weights unchanged. For a public river `r`, remove hands containing `r` and let
`Z(r)` be the sum of the products of the remaining compatible hand weights.
Let `Z` be the initial compatible pair mass. The public river probability is
`Z(r)/(44 Z)`, rather than `1/48` or a uniform distribution over range-union
cards. Conditional river ranges retain their original weights; the independent
game conditions on compatible pairs. Every original deal has 44 legal rivers.

The harness explicitly enumerates all 48 candidate cards. Zero-mass cards are
recorded with probability zero and skipped. Each supported river is a new game
constructed and trained by unmodified `noambrown/poker_solver`, pinned at
`6a10442877ffc8fd28af93e16e279b9bbdd97b2a`, in an isolated process that checks
no product modules are loaded. It uses the existing verified exhaustive-eval
fallback, 4,000 reference iterations, cents units and twice the upstream raw
exploitability divided by 100 to obtain NashConv in chips.

The turn engine trains for 2,000 iterations. For each independent river tree,
the adapter verifies the exact check/bet/call/fold tree and matches public
history, action amount, actor and concrete hands before mapping its river
policy. It never traverses the product tree to generate the reference tree.
Independent evaluation of that same policy must reproduce aggregate turn EV
and NashConv within `1e-8` chips. In addition, separately trained reference
river EVs are aggregated by the above probabilities; their difference from the
turn value must lie within the sum of the two NashConv gaps plus `1e-8` chips.
Both each supported subgame and the aggregate retain the existing 0.5%-of-pot
convergence gate. Frequencies need not coincide between approximate equilibria.
Differing trees, implicit sizes, duplicate capped bets and rounding are rejected.

Four fixtures cover singleton zero-mass runouts, weighted cross-range blockers,
a draw-heavy board with two sizes and a paired board with a capped size. The
[readable results](turn-decomposition-results.md) and
[versioned outputs](turn-decomposition-results.json) retain each public card's
mass, probability, EVs, gaps, deterministic reference-profile digest and source
hashes. Full ordered reference exports/checkpoints are kept separately at the
report's raw-evidence path under `.artifacts/` and in CI artifacts; they are not
added to the product or vendored reference source. The reference is a second
implementation, not a proven gold standard. This validates a special case
with no strategic turn betting, not independently trained two-street play.

```sh
OPENBLAS_NUM_THREADS=1 python scripts/benchmark_turn_decomposition.py
```

## Maximum-dimension performance study

Two explicit synthetic fixtures each exercise 24 combinations per player,
two uncollapsed sizes on both streets, deep stacks, 36 decision templates
(30 river templates, each with 48 public-card contexts) and 2,000 iterations.
Every run constructs a fresh solver in a separate process with BLAS/OpenMP
thread counts fixed at one. Measurements include initialization, solving with
both hand queries over all rivers, and JSON serialization. Parent-process wall
time also includes interpreter/import startup. Three repeats per fixture avoid
reusing rank caches across measurements. Each worker has a 120-second local
study deadline; a timeout kills it and is reported as failure, without inventing
a result or memory peak. CI runs one repeat per fixture.

The [measurements](turn-performance-results.json) and
[readable table](turn-performance-results.md) record Python/NumPy, OS/processor,
source hashes, effective bet amounts, convergence diagnostics and output sizes.
On the measured Windows machine, all six runs completed in 11.79–12.16 seconds
of process wall time, with maximum observed peak resident memory 34.66 MiB.
Windows uses `PeakWorkingSetSize`; Linux/macOS use `ru_maxrss` with platform unit
conversion. Peaks include interpreter imports and native allocations, not just
Python allocations. Timing is machine-dependent and resident peaks differ by
OS accounting. These are observations, not portable CI speed thresholds.
The all-river JSON query outputs were 372,389 and 394,193 bytes respectively
with the worker's serialization settings; a future hosted schema must bound
response size as well as computation.

```sh
python scripts/benchmark_turn_performance.py
```

This samples maximum configured dimensions on two inputs; it does not prove a
universal worst runtime across all boards, weights, sizes and machines. There
is no enforced address-space limit in this study, and resident memory cannot
establish compliance with the hosted 384 MiB address-space cap. These results
also do not establish hosted 20-second wall/CPU acceptance, maximum concurrency,
payload safety or authenticated ChatGPT turn integration. General two-range
external turn training remains a separate validation gap.

## Regression coverage

Five additional tests check explicit chance masses/zero-probability cards,
independent tree evaluation under reversed input hand ordering, injected product
payoff corruption, incompatible trees/rounding, maximum worker dimensions/memory
units and structured timeout reporting. Existing river, transport and turn
tests remain required. CI runs fresh decomposition, performance and the existing
benchmarks, retaining both summary and full reference artifacts.
