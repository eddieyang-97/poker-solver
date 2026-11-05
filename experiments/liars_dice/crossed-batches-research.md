# Crossed private-hand minibatches (#49)

After owner-merged #56, this study tests whether vectorized chance blocks can
amortize graph work and cover more own hands per CPU second. #56's direct
conditional integration remains an unchanged reference. No product or hosted
model changes follow from this experiment.

## Operator and correctness

Draw two independent lists of **K=8** hands from the true weighted prior, with
replacement. Freeze the whole policy profile for one block. Diagonal batching
averages the K scalar paired-deal increments at corresponding list positions.
Crossed batching averages all K*K paired-deal increments from their Cartesian
product. Normalize regret **and** average-strategy increments by the number of
pairs. Scatter to each hand's row, adding every duplicate occurrence. Do not
replace empirical multiplicities with a uniform distribution on unique hands.

Both operators have the old scalar frozen-pass expectation. Crossed increments
are also the average over every permutation of diagonal pairings of these two
lists. Conditional on the two unordered sample multisets, every pairing has the
same distribution. Thus crossed increments have no larger fixed-policy
componentwise/trace variance than a diagonal block. K*K pairs share samples;
they are not K*K independent deals. This says nothing about the learned policy's
variance or equilibrium convergence.

All policies are selected by the acting seat's own hand and public graph key.
Opponent dice enter training expectations/terminal payoffs, never action choice.
Both seats read the same frozen profile, with no within-block policy update.
Consequently a block is **not** K sequential adaptive CFR iterations. Equal
iteration counts, sample counts or pair counts are not equal-compute controls.
Signed cumulative regret, own-reach average updates, graph keys and terminal
utilities are inherited unchanged. Full-rule runs retain one-bid recall; fixture
controls also retain two-bid and full recall. Imperfect recall has no general
equilibrium guarantee here.

Tests independently compare K=1 with the original scalar trainer, compare a
full-rule duplicate-containing Cartesian block with nine scalar passes at a
frozen profile, average all six diagonal permutations for K=3, and enumerate all
16 size-two blocks of a nonuniform two-type fixture. The latter checks exact
expected regret/average increments and trace variance at recall 1/2/full.
Additional checks cover repeated indices, unsampled rows, seeds and invalid
inputs before mutation.

## Predeclared measured study

Use both existing six-bid house fixtures (zhai quantities 2 and 3), the same
56-profile private policy class, recall 1/2/full and seeds 490051/52/53. Fresh
controls are scalar paired, diagonal8, crossed8 and direct conditional
integration. Each gets cumulative **1 and 5 training CPU seconds**, excluding
freezing, evaluation and export. Method order rotates with the seed. Keep all
72 runs/144 checkpoints, including failures and negative results; export all
72 final full-public-history tables. Evaluate chance, EV and both unrestricted
public-history BRs exactly within the declared fixture in float64.

The fixture admission heuristic is fixed before measuring results: at the final
CPU budget, at least one batch method must achieve median NashConv/scalar ratio
<=0.8 and win at least 9 of the 12 recall-2/full cases across both fixtures and
three seeds. Report crossed/diagonal ratios separately. This is an engineering
gate, not a significance test or a general guarantee. Recall-1 results remain
visible but do not determine this gate. Do not tune K or discard failing cases
after looking at the gate.

If admitted, run fresh **scalar, diagonal8 and crossed8** full-rule one-bid
controls at cumulative **15 and 60 training CPU seconds**, all three seeds.
Retain iteration blocks, sampled own-hand counts, minimum visits and unsampled
prior mass. A hand visit does not guarantee every information set is trained.
Every checkpoint gets depth-one full-history continuation responses with 32 own
nodes per seat and independent 2,000-game raw-dice response-policy replay. Final
policies additionally face probability-0.3/0.7 opponents in both seats, 2,000
games each. Retain nine final lossless research snapshots and verify exact loads.
This is a bounded quality probe, not permission to spend unbounded compute or
allocate richer full-game tables. A failed fixture gate means no full-game run.

The training timer includes loop/guard/update overhead and can overshoot by one
block. Array/scratch overhead, evaluation and export are included in whole-study
resource measurements. The overall 1,800-second guard checks between work units,
not as a hard process deadline. Status/checkpoints persist on failure. All
measurements are local Windows evidence with one OpenBLAS thread, not provider
or client acceptance. No benchmark threshold or historical receipt is changed.

## Reproduce and interpret

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_crossed_batches.py -v
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_crossed_batches.py
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The project virtual environment
contains NumPy and the existing test tools. Source manifests use LF-normalized
SHA-256; policy exports retain raw-byte hashes. To replay machine-dependent
fixture and full-game iteration counts:

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_crossed_batches.py --replay-counts experiments/liars_dice/outputs/crossed-batches.json --output .artifacts/batch-replay.json
```

Explicit replay follows the archived admission decision and records the input
hash. It does not claim the new machine passes the CPU/quality gate. Both modes
record actual CPU/wall cost. Compare archived policies with numerical tolerance
and retained probability hashes, not CPU counts as a cross-machine invariant.

The fixture's action restriction and 56-type policy-class limits from #55 still
apply: redundant 252-hand labels can support private persistent correlation in
imperfect-recall policies. Fixture NC is not full-game exploitability. Full-game
response bounds are structural float64 intervals, not outward-rounded formal
certificates. Overlapping intervals do not establish a strength ranking; lower
lower bounds alone are not evidence of improvement. Individual Hoeffding 95%
payoff intervals do not give simultaneous significance across comparisons.
Keep valid prior bounds for unchanged historical targets.

## Recorded outcome

All 72 fixture runs/144 checkpoints completed. At five training CPU seconds,
the exact full-history NashConv ranges across three seeds are:

| Fixture | Recall | Scalar | Diagonal8 | Crossed8 | Conditional |
| --- | --- | ---: | ---: | ---: | ---: |
| q2 | 1 | 0.047057–0.073599 | 0.039360–0.041306 | 0.015194–0.018993 | 0.024708–0.030645 |
| q2 | 2 | 0.108992–0.115118 | 0.049354–0.060500 | 0.020285–0.023918 | 0.052347–0.061574 |
| q2 | full | 0.137300–0.155692 | 0.071489–0.079698 | 0.033607–0.036578 | 0.083428–0.091068 |
| q3 | 1 | 0.098253–0.106622 | 0.081183–0.083613 | 0.048265–0.057702 | 0.075687–0.092705 |
| q3 | 2 | 0.149978–0.171750 | 0.080477–0.096910 | 0.034667–0.038253 | 0.092359–0.104791 |
| q3 | full | 0.228009–0.260135 | 0.119010–0.129493 | 0.052222–0.054887 | 0.158544–0.168305 |

The admission gate passed: diagonal/scalar median ratio **0.515373**,
crossed/scalar **0.228885**, both winning all twelve recall-2/full comparisons.
The crossed/diagonal median ratio is **0.439449**. Crossed results are lower in
every matched final fixture comparison, including recall 1 and direct conditional
controls. These are measured improvements on this finite corpus, not asymptotic
rates or an unrestricted house-game quality claim. The two CPU checkpoints do
not establish a convergence rate or a strategy-class floor.

All nine admitted full-rule pilots also completed. At 60 training CPU seconds:

| Method | Seed | Blocks | Own samples per seat | NashConv lower / upper |
| --- | --- | ---: | ---: | ---: |
| Scalar | 490051 | 5,495 | 5,495 | 1.644203 / 1.865842 |
| Scalar | 490052 | 4,294 | 4,294 | 1.674392 / 1.874241 |
| Scalar | 490053 | 4,356 | 4,356 | 1.672923 / 1.873281 |
| Diagonal8 | 490051 | 1,093 | 8,744 | 1.582761 / 1.848516 |
| Diagonal8 | 490052 | 1,239 | 9,912 | 1.559272 / 1.839854 |
| Diagonal8 | 490053 | 1,105 | 8,840 | 1.571912 / 1.842905 |
| Crossed8 | 490051 | 585 | 4,680 | 1.599609 / 1.863537 |
| Crossed8 | 490052 | 588 | 4,704 | 1.598505 / 1.862350 |
| Crossed8 | 490053 | 591 | 4,728 | 1.591821 / 1.862229 |

These intervals overlap; none establishes an unrestricted strength ranking.
Both batch methods remain substantially exploitable. Crossed blocks cost roughly
1.9–2.1 times as much CPU per block as diagonal blocks in this larger action
space. Their own-hand coverage is therefore not uniformly better than scalar:
unsampled prior mass spans 0.051–0.283% (crossed), 0.013–0.039% (diagonal), and
0.039–0.257% (scalar) across seats/seeds. These are hand-level coverage measures,
not information-set convergence claims.

At the final checkpoint, crossed payoff means exceed both matched controls in
all twelve opponent/seat/seed comparisons; diagonal means exceed scalar in all
twelve. Ranges across both seats and all three seeds, in candidate utility:

| Opponent threshold | Scalar | Diagonal8 | Crossed8 |
| --- | ---: | ---: | ---: |
| 0.3 | -0.388 to -0.263 | -0.178 to -0.138 | -0.066 to -0.040 |
| 0.7 | -0.165 to -0.094 | -0.023 to 0.104 | 0.084 to 0.138 |

These fixed probability opponents are declared models, not calibrated humans
or adversarial BRs. Individual uncertainty is retained; this is not a
simultaneous significance claim or a universal ranking. All 36 response-policy
replay checks fall within their individual Hoeffding intervals. Historical
targets and bounds remain unchanged.

The main run used **1,200.36 wall / 1,188.77 CPU seconds**, with Windows process
peak **329,433,088 bytes (314.17 MiB)**. All 72 fixture tables and nine full-rule
snapshots are retained, including every seed/checkpoint. All **62 standalone
tests** pass locally in 52.51 seconds, including replay of every final fixture
table, snapshot loads, source/file hashes and fail-closed admission cases. Ruff,
compile and whitespace checks pass. These are measured research results, not
acceptance for policy promotion or a full-game GTO solution.

## Post-study cost diagnostic and next decision

After the main run, a separate short cProfile diagnostic uses seed 490054, two
warmups and twenty full-rule steps for each batch method. It records its own
source manifest in `outputs/batch-profile.json`. In that instrumented run,
NumPy `ufunc.at` accounts for approximately **42.8%** of crossed wall time and
**22.4%** of diagonal wall time. This combines pair-position reductions and final
duplicate-hand scatter; it does not isolate those call sites. Absolute short-run
instrumented timings are not comparable with sustained CPU-budget training.

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/profile_crossed_batches.py
```

**Next design:** replace Cartesian pair-position scatter with axis reductions,
while retaining multiplicity-safe scatter to duplicate private-hand rows. Check
equality against this frozen reference, then measure the actual CPU/quality
benefit on fixtures before another bounded full-rule comparison. Own-hand
blocking and richer recall remain candidates, not automatic memory/compute
allocations. Longer training alone is not accepted as a solution to recall loss.
Withhold GTO frequencies and general continuation recommendations; the full-rule
quality evidence remains far from equilibrium despite the held-out mean gains.
