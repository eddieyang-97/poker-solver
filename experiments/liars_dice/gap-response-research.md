# Allocating best-response search by unresolved bounds (#49)

This study compares search schedules against six frozen targets with exactly
enumerable best responses. Four targets come from [#55's recall ablation](recall-ablation-research.md):
the exact full-recall and sampled one-bid policies (seed 490021) for both
six-bid house fixtures. Those fixtures retain the confirmed scoring and
mode switches on their selected bid sets, with 56 chance-weighted hand
profiles. The other two targets use the one-face game with maximum bid 10
and integer-weight policy rows generated in legal-action DFS order from
NumPy seeds 490081 and 490082. Each target is evaluated from both seats.

All methods pool hidden opposing hands before choosing each own hand's
action. At an unexpanded own node, challenge gives a feasible value and
+1 times the incoming opponent reach gives an optimistic value. Forced
challenges are exact. Expanding an own node evaluates every legal action and
every positive opponent response. The full public history and unnormalized
opponent-hand masses remain distinct at each node.

| Schedule | Allocation |
| --- | --- |
| Legacy | Depth-first in legal action order, with depth high enough to be inactive |
| Reach | Reuse expanded nodes and descend into the highest-reach unresolved opponent observation |
| Gap | Reuse expanded nodes and descend toward the largest remaining gap on the current optimistic path |

Gap priority assigns each own hand to its current upper-maximizing action
(legal order breaks ties). It weights the child interval widths by the
prior of the assigned hands, and passes that subset of hands down when
choosing the next branch. Opponent nodes sum weighted continuations.
Backups use all hands and actions for both endpoints, including branches
outside the optimistic path. The lower plan uses a single legal action per
own hand and complete public history. Optimistic values use float64
arithmetic. A reach-scaled tolerance suppresses rounding noise in priority,
while reported endpoints retain the calculated values.

The incremental methods keep a default cap of 20,000 generated non-forced
own histories, counting attempted work. If an expansion reaches the cap
after initialization, the previous feasible plan and valid frontier bound
remain in place. If initialization cannot produce a complete root, the
search raises a limit error. Node and history caps count search work, and
the experiment reports process memory and CPU separately.

## Reproduction and decision criteria

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_gap_response.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The receipt
[`outputs/gap-response.json`](outputs/gap-response.json) contains source and
input hashes, seeds, exact profile EV and best responses, both endpoints,
work, realized plan values and timings. The independent evaluator enumerates
complete public histories with explicit utility matrices at terminals. It
checks the frozen target's exact best response and the realized value of
every tested lower plan in float64.

The matched caps are 2, 4, 8 and 16 expanded own nodes per seat, plus a
4,096-node closure check against the independent best response. The gate for
a larger full-rule search budget requires a median summed-width ratio of at
most 0.80 against each control, no per-checkpoint width increase above
0.05, and at most 1.25 times each control's aggregate CPU at cap 16. CPU
timings use 20 fresh solves per seat and method in rotating order, with
oracle and replay work outside the timer. Equal node caps allow different
CPU costs.

The supplemental comparison uses the smallest integer node cap at which
each schedule achieves width 0.02 or less. Its timing repeats the same
rotation with those caps. Width is a best-response measurement target in
round-utility units. The two timing comparisons answer different questions
and use separate receipts within each case.

## Recorded outcome

Gap allocation narrows the summed partial widths in all 12 seat/target
cases against both controls. The median ratios are 0.298 against legacy
and 0.288 against reach. Every method closes to the independent best
response within 2.23e-16 at the exhaustive cap. All 216 lower-plan checks
realize their reported value within 3.34e-16.

| Schedule | CPU at cap 16 | Sum of minimum caps for width ≤ 0.02 | CPU to reach width ≤ 0.02 | Wall time to reach width ≤ 0.02 |
| --- | ---: | ---: | ---: | ---: |
| Legacy | 0.734 s | 245 | 1.063 s | 0.999 s |
| Reach | 1.297 s | 264 | 1.891 s | 1.922 s |
| Gap | 1.172 s | 80 | 0.797 s | 0.828 s |

At cap 16 gap costs 1.596 times legacy's CPU and exceeds the full-rule
admission threshold. At the width target it reaches the goal with lower
node caps in all 12 cases and costs 0.750 times legacy's CPU in aggregate.
These are small local timing batches. The width target comparison supports
further work on the scheduler, while the cap-16 gate limits this milestone
to fixtures. The archived full-rule bounds retain their #59 provenance.

The run took 35.02 wall seconds and 34.78 CPU seconds, with a 47.25 MiB
Windows peak working set. The strongest result concerns work allocation on
the declared fixtures. Full-rule memory, speed and response quality remain
open.
