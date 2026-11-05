# Conditional opponent-hand integration (#49)

This study follows owner-merged PR #55. It replaces the paired-private-deal
regret estimator with a conditional expectation, keeping the same signed
cumulative updates, public graph, average policy and recall definition. The
experiment measures correctness, fixed-policy variance, learning cost and a
bounded full-game pilot. It does not automatically promote a policy into the
MCP analysis tool.

## Estimator and information constraints

For each seat, independently sample its own private hand from the true weighted
chance distribution. Hold the entire policy profile fixed. Run forward reach
and backward values over the public graph while **integrating every possible
opponent hand with its prior weight**. At acting-seat nodes use only that seat's
sampled own-hand policy row. At opponent nodes, each possible opponent hand uses
its own policy row. Integrate action advantages over opponent hands before
applying the sampled own-hand regret update.

Both seat passes read the same frozen policies; neither updates policies between
passes. Seat 0's update does not use seat 1's sampled hand, and vice versa. The
two sampled hands are used as separate own-hand samples, not as an observed
showdown. Hidden opponent hands are integrated, never revealed to action choice.
Conditional root values condition on different own hands and are not presented
as a realized-deal payoff.

For each seat's update vector this is the conditional expectation of #54's
paired-deal estimator given the own hand. Therefore it has the same expected
increment and no larger componentwise/trace variance at a fixed policy. That
claim is about the estimator, not convergence of imperfect-recall learning or
variance of final policies. Average-strategy increments use the same own reach;
we verify their means as well and do not claim that every quantity's variance
is reduced.

Tests enumerate a nonuniform private chance fixture at recall 1/2/full, compare
conditional increments with direct opponent-hand averages of the old estimator,
and compare total expectations with the exact-deal trainer. They check both
seats, independence from the other seat's sampled hand, repeatable seeds and
full-rule vector terminals against scalar payoff calls. Existing trainers and
historical receipts remain unchanged; mixins override only the frozen-pass
estimator and reuse allocation, updates, averaging and export behavior.

## Fixed-policy variance and fixture curves

On q3's 56-profile fixture, a fixed randomized regret table (seed 490041) is
shared by paired, conditional and exact trainers. Enumerate all 3,136 private
pairs to measure expected regret/average increments and regret-vector squared
error variance. Record each recall level separately; norms across different
representations are not a common quality measure. Time 100 repeated frozen
passes per estimator. Those short Windows CPU measurements are coarse and are
not a robust ranking when variance-times-time ratios are near one.

Then train the conditional method at recall 1/2/full, seeds 490041/42/43, with
checkpoints 1,000 and 5,000. Evaluate full-history EV and both BRs by exact chance
enumeration in float64. Retain all nine final public-history policy tables.
The accepted #55 paired/exact corpus is a hashed historical reference with
different seeds and recorded costs, not a fresh controlled equal-time run.

The q3 fixture still restricts actions to six bids and uses the same 56-profile
policy class as #55. Profile compression preserves payoff/full-history
evaluation, but not necessarily every 252-label imperfect-recall policy class:
redundant labels can supply persistent private correlation. These curves do not
establish unrestricted house-game exploitability or explain all prior failures.

## Predeclared full-game pilot and CPU comparison

After correctness checks, time 20 warm conditional full-game iterations. Admit
a bounded pilot only if the measured mean is <=0.25 CPU seconds per iteration.
That is a cost admission rule, not a strategic quality gate or hosted budget.
The two regret/average arrays remain 91,300,608 bytes. Additional frozen-policy
and conditional-vector scratch is included in measured process peak, not hidden
inside that two-array figure.

Use all 252 original hands, every legal bid and recall 1. Run **fresh paired and
conditional controls** for each seed 490041/42/43 at cumulative training CPU
budgets **15 and 60 seconds**. The CPU timer includes the training loop/update
overhead, excludes freezing/evaluation/export, and can overshoot by one iteration.
Iteration counts are machine-dependent and explicitly recorded; equal iteration
counts are not used as an equal-compute comparison. Own-hand sample coverage and
uniform fallback mass are retained at each checkpoint.

Every checkpoint receives fresh #47 full-history continuation responses, depth
one / 32 own nodes per seat, plus independent 2,000-game raw-dice response-policy
replay. Final policies also face predeclared probability-0.3/0.7 opponents in both
seats. All seeds/checkpoints/failures remain in the receipt. Sampled payoff
intervals are individual Hoeffding 95% intervals, not simultaneous claims across
all experiments. The response bounds are structural float64 calculations, not
outward-rounded numerical certificates. Lower lower bounds alone do not prove
that a policy is stronger. Prior valid bounds for unchanged historical targets
remain valid.

All six admitted final full-game policies are exported losslessly in the existing
research snapshot format and reloaded exactly. This is a research artifact,
not an allowlisted hosted model. No GTO frequency, general continuation
recommendation or human-opponent calibration follows from estimator correctness.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_conditional_chance.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Use the project environment; PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`.
To reproduce the archived full-game policy counts instead of stopping at a
different machine's CPU time:

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_conditional_chance.py --replay-counts experiments/liars_dice/outputs/conditional-chance.json --output .artifacts/conditional-replay.json
```

Explicit count replay records its input hash and bypasses cost admission; it
does not assert the new machine passes that cost gate. Both modes retain the
1,500-second between-work-unit experiment guard. The guard is not a hard process
deadline. Status and completed checkpoints persist on failure/interruption.
Counts, software/platform, source and output hashes are required when comparing
floating-point replay. CPU-budget iteration counts are not expected to be
identical across machines. All process/resource evidence is local Windows,
including the measured whole-study peak across training, validation and export;
no Linux/provider/client acceptance is claimed.

## Recorded outcome and decision

All variance checks, nine fixture runs and six full-game runs completed. Maximum
fixed-table mean error was **1.12e-16**. Conditional/paired regret trace variance
ratios were **0.293 / 0.236 / 0.210** for recall 1/2/full. Short frozen-pass timing
products are retained with their coarse measurement caveat; variance reduction
alone does not establish CPU efficiency.

At 5,000 fixture iterations, conditional NashConv ranges were **0.061420–0.071231**
(recall 1), **0.030122–0.032200** (recall 2), **0.028098–0.030618** (full). The
corresponding training CPU ranges were 8.44–8.75, 21.83–22.08 and 35.06–43.42
seconds. Compared with #55, this improves the recorded per-iteration curves, but
the historical seeds differ and these are not controlled equal-time comparisons.

The full-game warm admission measured **0.178125 CPU seconds/step**, so the pilot
proceeded. Its fresh 60-second controls produced:

| Method | Seed | Iterations | NashConv lower / upper |
| --- | --- | ---: | ---: |
| Paired | 490041 | 4,136 | 1.687268 / 1.880334 |
| Paired | 490042 | 4,506 | 1.670287 / 1.873444 |
| Paired | 490043 | 4,578 | 1.663681 / 1.874094 |
| Conditional | 490041 | 343 | 1.866795 / 1.963498 |
| Conditional | 490042 | 345 | 1.865019 / 1.956488 |
| Conditional | 490043 | 348 | 1.866010 / 1.960364 |

The intervals overlap, so this is not proof of an unrestricted exploitability
ranking. However, the conditional method shows no observed equal-CPU benefit:
all twelve matched held-out payoff means are lower. Conditional means range
**-0.767 to -0.564**, paired **-0.364 to -0.109**; individual uncertainty remains
in the receipt, without a simultaneous significance claim. All response-policy
replays fall within their individual Hoeffding intervals.

At 60 seconds, conditional uniform-fallback prior mass remains **16.8–20.6%**
across seats/seeds, versus paired **0.039–0.360%**. This accompanies the much
smaller own-hand update count; integrating opponents does not train unsampled
own-hand rows. Budget completion must not be described as coverage or convergence.

The main experiment used **777.09 wall / 768.80 CPU seconds**, process peak
**323,399,680 bytes (308.42 MiB)**. All six full-game snapshots and nine fixture
policy tables are retained. The prototype passes mathematical checks but is a
**no-go as the current equal-CPU full-game training replacement**, and a no-go
for recommendations/model promotion.

After the main run, `profile_conditional_chance.py` records a separate instrumented
20-step diagnostic (seed 490044, two warmups, one OpenBLAS thread), with its own
source manifest in `outputs/conditional-profile.json`. Its shorter instrumented
timing is not comparable with the sustained CPU-budget experiment. Roughly 67%
of that instrumented wall time is attributed to the pass body and 13% to clipping;
clipping alone is not shown to explain the full cost. Run it separately with:

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/profile_conditional_chance.py
```

**Next design:** test cached/blocked updates or crossed private-hand minibatches
to amortize work and increase own-hand coverage. Verify exact expected increments,
duplicate-hand handling and simultaneous freezing first; compare actual CPU and
quality on the existing fixtures. Require a measured benefit before another
full-game escalation. Keep recall controls and all previous negative evidence.
Neither additional integration nor more memory is automatically an improvement.
