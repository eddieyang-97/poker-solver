# Axis reductions for frozen chance blocks (#49)

This follows owner-merged #57. The goal is to reduce the cost of the same
crossed-hand estimator, not change its chance weights, information sets or
learning rule. Historical sources and receipts remain unchanged.

## Change and correctness

For K own samples per seat, the reference enumerates Cartesian pair positions
in row-major order: `(0,0), (0,1), ..., (K-1,K-1)`. Its scatter into sample
positions is exactly a sum over the other sample axis. Reshape each action's
K*K values to K by K; sum axis 2 for seat 0 and axis 1 for seat 1, transpose to
sample/action rows and divide by K*K. Diagonal mode needs only transpose/K.
Apply the same operation to regret and own-reach average increments.

The inherited final scatter to **private-hand indices** still uses `add.at`:
different sample positions may contain the same hand and must all be added.
Removing that scatter or using ordinary advanced-index `+=` would drop duplicate
updates. Both seat passes still read one frozen policy profile. True-prior
sampling, signed cumulative regret, average policies, visits and export are
inherited unchanged. This is the same real-number estimator as #57, with changed
floating-point summation order; it is not a new equilibrium algorithm.

The new module keeps the graph recurrence explicit so the historical source
manifest stays replayable. Tests compare explicit pair sums at K=1/2/3/8/32,
both modes/seats, duplicate-containing fixture passes at recall 1/2/full, and a
randomized full-rule pass. They independently enumerate nonuniform two-type
chance blocks against exact graph increments, and reject invalid hands before
mutation. Mathematical equivalence does not imply bit-identical adaptive
trajectories; the measured study checks that sensitivity separately.

## Predeclared study and admission

Use K=8 crossed blocks for all measured comparisons, one OpenBLAS thread and
seeds 490061/62/63. No batch-size selection follows from looking at results.

1. **Frozen full-rule cost:** shared randomized regret table (seed 490061) and
   32 true-prior blocks. Four untimed paired passes check scaled increment error
   <=2e-12 and warm both implementations. Time all 32 blocks in balanced
   reference/axis/axis/reference order; verify neither table mutated. Record
   both CPU ratios and their median. This excludes `step` updates and does not
   measure learned-policy quality or sustained service latency. Two original
   regret/average table pairs are temporarily resident; whole-study peak
   includes that local probe, with no provider-memory acceptance claim.
2. **Fixed-count sensitivity:** both six-bid fixtures, recall 1/2/full, seed
   490061, paired trajectories at 100/500 blocks with identical hand streams.
   Record max policy-probability difference and full-history EV/BR/NashConv for
   both implementations. Paired CPU/wall measurements cover each training
   segment together, not per-method timing. Retain all twelve final tables.
3. **Equal CPU:** fresh reference/axis controls on both fixtures at recall
   1/2/full, all three seeds, cumulative 1/5 training CPU seconds. Rotate method
   order with the seed. Retain all 36 runs/72 checkpoints and final tables,
   exact full-history EV/BR/NashConv, own-hand samples and coverage.

The engineering admission gate is fixed before measurement: frozen-pass median
axis/reference CPU ratio <=0.85; maximum fixed-count endpoint EV and NashConv
drifts <=0.01; final equal-CPU recall-2/full NashConv median ratio <=1 and maximum
ratio <=1.1 across all twelve fixture/seed pairs. Report every win, loss and
policy difference. Recall-1 evidence is retained but excluded from the quality
ratio gate. These thresholds are a bounded experiment decision, not statistical
noninferiority tests, general performance guarantees or equilibrium acceptance.

Only if all three conditions pass, run fresh full-rule **reference/axis crossed
blocks** at cumulative 15/60 training CPU seconds, all three seeds. Every
checkpoint gets depth-one full-history continuation-response search, 32 own
nodes per seat, plus independent 2,000-game raw-dice response-policy replay.
Final policies also face fixed probability-0.3/0.7 opponents in both seats,
2,000 games each. Retain six final lossless snapshots, verify exact loads and
retain all costs, own-hand coverage, uncertainty and failures. No full-rule
adaptive training occurs if admission fails.

Training timers include guard/loop/update overhead but exclude freezing,
evaluation and export; a budget can overshoot by one block. Whole-study wall/CPU
and Windows process peak include every phase. The 1,800-second guard checks
between work units, not as a hard process deadline. Running/completed/incomplete
status and completed checkpoints persist. Estimator/driver source hashes are
checked at completion; thresholds and historical corpora stay unchanged.

## Reproduce and limits

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_axis_batches.py -v
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_axis_batches.py
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Use the project environment.
CPU-budget counts vary across machines. To replay archived counts:

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_axis_batches.py --replay-counts experiments/liars_dice/outputs/axis-batches.json --output .artifacts/axis-replay.json
```

Explicit replay records its input hash and follows the archived admission for
full-rule counts. It does not assert the new machine passes the cost/quality
gate. It reruns the frozen probe and fixed-count controls; actual costs and
current admission metrics remain visible. Source hashes use LF-normalized
SHA-256; exported-policy hashes cover raw bytes. Software/platform and all
iterations must accompany cross-machine comparisons. A count replay is not
expected to reproduce wall time or guarantee bit-identical float64 policies.

Fixture BRs are exact chance/full-history evaluations **within** the six-bid,
56-profile policy class. These are not unrestricted full-game bounds; compressed
labels can lose persistent private correlation for imperfect-recall strategies.
Full-rule training still uses one-bid recall with no general equilibrium
guarantee. Full-game response intervals are structural float64 bounds, not
outward-rounded certificates. Overlapping intervals and smaller lower endpoints
do not prove stronger play. Held-out probability opponents are explicit models,
not calibrated humans; individual Hoeffding intervals are not simultaneous
significance claims. Historical targets/bounds and hosted models stay unchanged.

## Recorded outcome

The frozen full-rule probe passes: maximum scaled increment error is
**4.05e-16**. The two balanced axis/reference CPU ratios are **0.592593** and
**0.632432**, median **0.612513**. Absolute timings differ substantially between
chunks; retain both observations rather than a best-case timing. These are
local frozen-pass results, not a cross-machine or sustained-training guarantee.

All six fixed-count controls completed both checkpoints. Maximum policy-entry
difference over all recorded trajectories was **8.75e-14**. At the 500-block
endpoints, maximum EV drift was **8.33e-17**, NashConv drift **3.61e-16**.
These small observed differences do not prove bitwise equivalence or rule out
larger adaptive sensitivity on untested seeds/games.

All 36 equal-CPU fixture runs completed. At five training CPU seconds, exact
full-history NashConv ranges across three seeds are:

| Fixture | Recall | Reference | Axis |
| --- | --- | ---: | ---: |
| q2 | 1 | 0.016644–0.021577 | 0.016645–0.021307 |
| q2 | 2 | 0.025546–0.028846 | 0.025071–0.028563 |
| q2 | full | 0.035212–0.041402 | 0.035936–0.038955 |
| q3 | 1 | 0.052900–0.065649 | 0.055629–0.061721 |
| q3 | 2 | 0.032476–0.040228 | 0.030372–0.037285 |
| q3 | full | 0.052641–0.062141 | 0.052842–0.059159 |

The admission gate passed: recall-2/full median NC ratio **0.985044**, maximum
**1.020570**, with **10/12** wins. Gains are modest on these small-action
fixtures. Across all recalls, axis wins 13/18 comparisons. Keep the negative
cases: for q3 recall 1 / seed 490061, more blocks (3,585 versus 3,222) produce
NashConv 0.060412 versus 0.052900. Faster updates and more iterations do not
ensure monotonic policy improvement, especially with imperfect recall.

All six admitted full-rule runs completed. At 60 training CPU seconds:

| Method | Seed | Blocks | Own samples per seat | NashConv lower / upper |
| --- | --- | ---: | ---: | ---: |
| Reference | 490061 | 631 | 5,048 | 1.576370 / 1.856903 |
| Axis | 490061 | 899 | 7,192 | 1.526193 / 1.858363 |
| Reference | 490062 | 614 | 4,912 | 1.597697 / 1.865259 |
| Axis | 490062 | 943 | 7,544 | 1.537325 / 1.863479 |
| Reference | 490063 | 595 | 4,760 | 1.598441 / 1.859825 |
| Axis | 490063 | 1,019 | 8,152 | 1.516602 / 1.857830 |

Block-throughput ratios normalized by actual training CPU are
**1.425 / 1.535 / 1.714**. Actual training cost includes inherited final scatter
and loop overhead; it is distinct from
the frozen-pass timing. Axis unsampled own-hand prior mass spans **0.013–0.090%**
across seats/seeds, versus reference **0.039–0.244%**, and is lower in every
matched case. Coverage is hand-level evidence, not information-set convergence.

All intervals overlap; the lower lower endpoints do not establish stronger
unrestricted play. For seed 490061 the axis upper endpoint is slightly higher,
and interval widths are larger for all three axis runs. The response search
still demonstrates substantial vulnerability and leaves strength unresolved.

Axis final payoff means exceed the reference in all twelve fixed-opponent/
seat/seed comparisons. Candidate-utility ranges across both seats and seeds:

| Opponent threshold | Reference | Axis |
| --- | ---: | ---: |
| 0.3 | -0.085 to 0.001 | 0.005 to 0.080 |
| 0.7 | 0.057 to 0.170 | 0.147 to 0.235 |

Near-zero positive means do not establish positive EV; individual uncertainty
is retained, without simultaneous significance claims. These are explicit
probability opponents, not human calibration or adversarial BRs. All 24
independent response-policy replay checks fall within their individual Hoeffding
intervals. Retain every checkpoint and all prior valid bounds for unchanged
historical targets.

The whole main run completed in **761.00 wall / 754.125 CPU seconds**, with Windows
process peak **329,973,760 bytes (314.69 MiB)**. Retain twelve fixed-count tables,
36 equal-CPU fixture tables and six lossless full-rule snapshots, all with
source/file fingerprints. The optimization preserves the measured estimator and
improves full-rule training throughput; it is not equilibrium acceptance.

Observed locally with one OpenBLAS thread: all **68 standalone tests** pass in
63.31 seconds, including all 48 final fixture-table replays, six snapshot
loads/fingerprints, source provenance and admission rejection boundaries. Ruff,
compile and whitespace checks pass. Count replay is supported and documented;
the recorded primary run used measured CPU stops, not archived-count execution.

## Next research decision

Use the retained policy snapshots to measure stronger full-history response
bounds and training-budget sensitivity before claiming unrestricted quality or
adding larger representations. Retain recall controls: faster arithmetic does
not repair imperfect-recall information loss. No GTO frequencies, general
continuation advice, hosted model change or policy promotion follows here.
