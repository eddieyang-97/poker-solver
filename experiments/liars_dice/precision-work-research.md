# Precision and global query effects (#49)

The [#65 negative result](selective-frontier-research.md) showed fewer
oracle calls without meeting the combined quality/cost gate. This combined
follow-up measures where selective work changes the root interval and
compares cold cost at three precision targets. The targets, prepared
control, eager factored method and selective query caps 4/16 are fixed.

The six frozen fixtures and both seats are evaluated at every integer
expansion cap until closure, with a cap of 256. Widths 0.1, 0.02 and
0.005 select the first cap meeting each precision. Independent full-tree
evaluation verifies feasible lower values at each crossing and closure.
The width-0.02 checkpoints reproduce the #65 endpoints and expansion
caps. No timing-based strategy or action choice enters the experiment.

A read-only subclass records each complete selective refinement after
backups reach the root. Records include query and expansion counts,
before/after lower and upper values, and total root-width reduction.
Query-only work must preserve the feasible lower endpoint. Root effects
reflect the current competing actions, rather than just the changed
leaf's local interval. This instrumentation is excluded from timing.
Fresh uninstrumented solves must reproduce the instrumented final
endpoints and every retained action.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_precision_work.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

The [receipt](outputs/precision-work.json) pins source and #65 input
hashes, retains complete curves and events, and reports raw timing blocks.
Six timing blocks each use 96 fresh solves per case, method and precision.
Methods alternate within each case and seat, with rotated/reversed order
across repetitions. Every timer includes new oracle construction and
search. CPU and wall totals remain separate. Report medians and full
block ranges, without treating observations as independent trials or
claiming a confidence interval. Static guide preparation is shared.

The historical admission gate remains a no-go. These precision
sensitivity and event diagnostics inform the next design choice.
They supply neither new full-rule response bounds nor improved policies.

## Recorded outcome

All 192 independent lower evaluations agree within 3.34e-16. The 48
trajectories close to the exact BR and retain 1,162 integer-cap points.
Across complete selective trajectories, 47/48 four-cap queries and
160/170 sixteen-cap queries reduce the root width by more than 1e-12.
Every query-only event preserves the feasible lower value. These are
immediate effects under the current action competition. They do not
measure the counterfactual cost of expanding instead.

| Precision | Eager factored CPU / prepared | Selective 4 CPU / prepared | Selective 16 CPU / prepared |
| --- | ---: | ---: | ---: |
| 0.1 | 1.336 | 1.249 | 1.326 |
| 0.02 | 1.329 | 1.310 | 1.414 |
| 0.005 | 1.242 | 1.166 | 1.357 |

Prepared has the lowest median CPU at every declared precision.
The same ordering holds for median wall ratios. At width 0.02 the
CPU block ranges are 1.250–1.490 eager, 1.111–1.516 selective 4 and
1.222–1.575 selective 16. Every aggregate CPU block exceeds 1.67 seconds,
but variability remains and isolated near-threshold values are insufficient
to reconsider admission. At width 0.005 selective 4 uses 109 expansions
and 48 queries versus prepared's 113 expansions.

The study takes 266.27 wall seconds and 261.95 CPU seconds with a
48.25 MiB Windows peak. The observations support prepared search as
the current fixed-precision control. Further selective-query changes
need to demonstrate savings in total work, since most existing queries
already improve the global interval.
