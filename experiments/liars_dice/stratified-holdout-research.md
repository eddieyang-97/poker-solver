# Held-out and equal-CPU tests of stratified training

Issue #49 tests whether the [fixed-block gains](stratified-chance-research.md)
survive new seeds, a new tree and changes to the ordering of the chance strata.
All policies use the same axis-reduced CFR trainer with a frozen crossed
block of eight private hands per seat. Only the private-hand draws change.

## Protocol

- Retain q2 and q3, and add a held-out fixture with all six q2 bids plus
  3 fly face six. The new bid changes the public tree and increases the
  private types from 56 to 126. The fixture uses the confirmed house legality,
  chance and payoffs.
  Hand profiles pool only combinations with the same count on every
  retained bid.
- Compare IID with three fixed stratified orderings. Profile order is the
  original lexicographic count vector. Zhai-first sorts by the two retained
  zhai contributions, breaking ties by profile order. Permuted shuffles
  profile order with Python's random seed 490140. Each order carries the
  original integer hand weights and maps sampled indices back into the
  common policy table. The two seats draw independently.
- Train recall one, recall two and full recall, pairing methods at seeds
  490141 and 490142. Alternate methods in rotating slices of 0.5 training
  CPU seconds. Freeze after a complete block at 1, 2.5 and 5 training CPU
  seconds. Charge draws and updates to this budget, and record actual CPU,
  wall, blocks and private hands observed. Freeze and independent evaluation
  run outside the training clock. Each trajectory caps at 32,768 blocks
  and 45 seconds of training wall time. All timings must be within 5% of
  their targets for the matched-CPU comparison.
- Evaluate both best responses with full public history. Preserve self-play
  EV, both response values, NashConv, absolute scores and every checkpoint
  policy. For the claim that the improvement is robust across orderings,
  require each stratified method at both richer recall depths to improve
  median NashConv at 5 seconds, win at least four of six paired comparisons
  and improve both seeds of the new fixture. Retain every adverse result.
- In a separate frozen diagnostic, warm up an IID trainer at seed 490143
  for 128 blocks per fixture and recall setting. Save its regrets, which
  determine the current policy. Use four independent groups of 64 frozen
  blocks per sampler (seeds 490151–490154). Measure distinct hands per
  list, distinct crossed pairs and the sum of unbiased coordinate sample
  variances of the scattered regret and average-policy increments, by
  seat. Group-level figures show sampling variation. This diagnostic
  conditions on one snapshot per fixture and recall. Its trace depends
  on the table coordinates and does not measure long-run learning noise.

The richer-recall robustness criterion applies to these restricted games.
Any proposed full-rule transfer needs a separate predeclared resource budget
and independent evaluation protocol. The existing full-rule search admission
gate and installed policies retain their current evidence.

An initial attempt stopped before the first matched comparison because the
8,192-block cap was too low for the one-bid trainer. A 2,048-block timing
probe took 1.094 CPU seconds on q2 with one-bid recall. The cap rose to
32,768 before the recorded run, with the same CPU targets and decision rule.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_stratified_holdout.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_stratified_holdout.py -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Pass `--out-dir` to save
a fresh run separately. Clock-stopped runs vary in block counts by machine
and load. The archived tables allow the exact recorded policies and frozen
diagnostics to be checked independently of timing.

## Recorded outcome

Each run matched its target at the resolution of the recorded process CPU
clock. The [receipt](outputs/stratified-holdout.json) records all 18 matched
cases, and the [archive](outputs/stratified-holdout-policies.npz) retains all
216 policy checkpoints and nine frozen regret tables. The study took
475.51 seconds elapsed and 472.28 CPU seconds including evaluation and
export, with a 71.25 MiB Windows peak working set. Final training counts
ranged from 3,440–9,298 blocks with one-bid recall, 1,379–3,660 with two-bid
recall and 822–1,905 with full recall.

Each cell reports the median of paired stratified/IID NashConv ratios.
Values below 1 indicate lower NashConv. Wins are counted at 5 seconds.

| Recall | Ordering | 1 s | 2.5 s | 5 s | Wins | Held-out wins |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | profile | 0.843 | 0.963 | 0.940 | 4/6 | 1/2 |
| 1 | zhai-first | 0.994 | 0.995 | 1.004 | 2/6 | 1/2 |
| 1 | permuted | 0.940 | 0.911 | 0.990 | 4/6 | 2/2 |
| 2 | profile | 0.833 | 0.740 | 0.771 | 6/6 | 2/2 |
| 2 | zhai-first | 0.850 | 0.856 | 0.795 | 6/6 | 2/2 |
| 2 | permuted | 0.887 | 0.879 | 0.856 | 5/6 | 1/2 |
| Full | profile | 0.851 | 0.787 | 0.739 | 6/6 | 2/2 |
| Full | zhai-first | 0.904 | 0.899 | 0.858 | 6/6 | 2/2 |
| Full | permuted | 0.914 | 0.905 | 0.915 | 4/6 | 1/2 |

Profile and zhai-first improve all 24 final richer-recall pairs, including
both held-out seeds. On the seven-bid fixture, full-recall profile NashConv
at 5 seconds is 0.03734 and 0.03648, compared with IID's 0.04248 and 0.04334.
The permuted order increases NashConv on held-out seed 490142 from 0.02098
to 0.02134 at two-bid recall and from 0.04334 to 0.04639 at full recall.
It therefore misses the predeclared across-orderings criterion. With
one-bid recall the original profile order also increases NashConv on that
held-out seed from 0.01531 to 0.02149.

Per 64 evaluated pairs in a frozen block, IID averages 51.16 distinct
pairs, profile 62.97, zhai-first 61.85 and permuted 61.50. Across recall
depths the median regret-variance trace ratios span 0.667–0.740 and
average-policy ratios span 0.722–0.789. Lower frozen traces coexist
with adaptive regressions on individual configurations. This supports
an ordering-dependent restricted-fixture benefit for structured strata.
Evidence for the 252-hand full-rule game remains open.
