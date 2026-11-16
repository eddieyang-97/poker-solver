# Selective frontier tightening (#49)

This combined milestone implements selective querying, checks its feasible
responses and failure paths, and compares complete cold searches against
the prepared, dense and eager factored controls on all six frozen fixtures.
It follows the fixed full-rule workload measurements in
[the feasibility study](full-frontier-feasibility.md).

The scheduler retains +1 at newly created leaves. When its existing
optimistic-path priority selects an unexpanded leaf, it queries the factored
one-reply upper bound once. The tighter value is backed up and the scheduler
chooses again. If that leaf is selected again it is expanded normally.
Lower choices still depend on own hand and public history.

Three declared variants allow 4, 16 or 4,096 queries per seat. Query caps
apply cumulatively across checkpoints. A query consumes work even if the
bound is unchanged. A memory/work exception disables further oracle calls
and retains the previous valid bound before continuing ordinary expansion.
The root opening is expanded using the existing mandatory initialization.
All legal actions and positive target branches are retained at expansions.

## Reproduction and comparison

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_selective_frontier.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

The [receipt](outputs/selective-frontier.json) records source and input
hashes, every partial interval, oracle queries and expansions, exact BR
containment and independent lower-plan values. Caps 1/2/4/8/16 measure
partial results and 4,096 expanded nodes check closure. Node caps count
expansions only, with queries recorded separately. The precision comparison
uses the first integer expansion cap reaching width 0.02.

Five rotated timing blocks each run 96 fresh solves per fixture and seat,
including fresh oracle creation. Setup and search costs are recorded
separately and added for admission. The existing thresholds remain median
summed upper-slack ratio ≤0.70, worst upper increase ≤0.02, and cold CPU
ratio ≤1.25 versus prepared at width 0.02. All tested variants and controls
remain in the receipt. Results concern this finite fixture corpus.

## Recorded outcome

All 504 independent lower-plan replays agree within 3.34e-16. All 72
exhaustive intervals close to the independently enumerated best response.
Prepared, dense and eager factored controls reproduce the archived
numerical endpoints.

| Method | Median upper-slack ratio | Cold CPU ratio at width 0.02 | Oracle calls at width 0.02 | Expanded nodes at width 0.02 |
| --- | ---: | ---: | ---: | ---: |
| Prepared | 1.000 | 1.000 | 0 | 80 |
| Dense | 0.376 | 4.229 | 270 | 56 |
| Eager factored | 0.376 | 1.428 | 270 | 56 |
| Selective 4 | 0.898 | 1.250 | 46 | 74 |
| Selective 16 | 0.851 | 1.295 | 80 | 63 |
| Selective 4,096 | 0.851 | 1.404 | 80 | 63 |

Calls and expansions sum the twelve seat/target cases. The four-query
variant meets the CPU threshold but misses the required slack ratio.
Both larger budgets miss the quality and cost conditions. The worst
matched-cap upper increase is 0.000629, reflecting altered allocation.
Queries save work on oracle construction but add traversal and backup
work, and leave useful bounds unqueried. None earns the full-rule pilot.

The study took 339.60 wall seconds and 335.81 CPU seconds with a 53.77 MiB
Windows peak working set. This closes the selective-query experiment at
the tested schedules. A follow-up should compare budgeted work against a
fixed precision objective before further scheduler optimization.
