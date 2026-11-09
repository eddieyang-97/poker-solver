# Preparing terminal and opponent-branch work (#49)

[#60](gap-response-research.md) found that gap-guided allocation reduced
interval widths on six frozen fixtures, while exceeding the fixed-node CPU
gate for a full-rule pilot. This milestone profiles the same searches and
tests two ways to reduce repeated work:

- Prepare each bid's integer contribution and tail-lookup arrays once per
  guide. Use the same weighted histogram, reversed cumulative sum, sign
  convention and float64 arithmetic as the original terminal calculation.
- Compute a positive opponent branch's reach once, then use it for both
  filtering and sorting. Sort by descending reach and ascending action ID,
  preserving the original order.

The claim-only and combined variants use these kernels with depth-first,
incremental reach and incremental gap schedules. The game, target policy,
challenger decisions, frontier rule, and history limits come from the
existing search. No policy is retrained. Tests compare the prepared payoff
vectors with the original operation and with explicit pairwise truth
matrices, including sparse and very small opponent reach.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_response_kernels.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The
[fixture receipt](outputs/response-kernels.json) fingerprints the source
and the #60 receipt. It records independent lower-plan values, comparison
errors, profiling totals, individual timing blocks and resource use.
Each kernel must reproduce the search's expanded work, choices and both
endpoints across the same caps, exhaustive closures and width-0.02 operating
points. A separate exhaustive tree evaluator checks the lower plans and
best-response containment.

The profiler runs 24 complete fixture batches at cap 16 per gap variant.
Profiling times include instrumentation and serve to locate repeated work.
The timed comparison uses three rotated blocks of 24 fresh solves per
seat, target and schedule at each operating point. The precomputed guide
and lookups are shared and setup cost is recorded separately. CPU ratios
use the median of block-level aggregate ratios. The #60 thresholds remain
0.80 for the median summed-width ratio, 0.05 for the largest allowed width
increase, and 1.25 for the cap-16 CPU ratio against each original control.
The study also reports both controls with the same optimized kernels and
reports matched-precision CPU separately.

## Recorded outcome

The original gap profile attributes 1.282 of 2.589 seconds (49.5%) to
terminal value calculation, including its array setup. The combined
profile attributes 0.440 seconds to the prepared terminal kernel with the
same 26,016 calls. Fixture lookup preparation took 0.687 ms across all six
targets. The timed batches reuse that setup.

All 432 checks match their same-schedule reference endpoints exactly,
with identical search decisions and work counters. Independent lower-plan
realization agrees within 3.34e-16. The original summed-width ratios
against depth-first and reach remain 0.298 and 0.288.

| Median CPU ratio for combined gap | Cap 16 | Width ≤ 0.02 |
| --- | ---: | ---: |
| Compared with original gap | 0.653 | 0.642 |
| Compared with combined depth-first | 2.750 | 1.024 |
| Compared with combined reach | 1.071 | 0.384 |

At cap 16 the combined gap variant costs 1.262 times original depth-first
CPU (individual blocks 1.250, 1.262 and 1.375), above the 1.25 threshold.
Pooling the CPU totals as in #60 gives 1.294 and the same decision.
The claim-only variant is also above the threshold at 1.279. Branch reach
reuse on top of prepared scoring has a median ratio of 0.987, with block
ratios from 0.951 to 1.056. Its standalone speed contribution remains
uncertain.

The gate keeps the full-rule pilot deferred. With the same kernels on both
schedules, gap and depth-first take similar CPU to reach width 0.02 on
these fixtures. The shared optimization preserves the search's numerical
behavior. Existing full-rule response measurements retain their #59
provenance.

The complete study took 128.07 wall seconds and 127.19 CPU seconds, with
a 48.54 MiB Windows peak working set.
