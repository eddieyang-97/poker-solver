# Linear averaging and regret clipping at matched CPU

Issue #49 follows the [ten-bid study](recall-bridge-research.md), where
one-bid recall had the lowest NashConv at seven training CPU seconds.
This study tests whether two changes to the crossed-block trainer improve
its short-budget policies and whether the two-bid policies close the gap.

## Protocol

- Use both ten-bid fixtures with all 252 exact private hands, recall one
  and recall two, and fresh seeds 490171 and 490172. All variants use the
  same fixed profile-ordered strata with eight samples per seat and the
  same seed stream. A matched block count within a seed and game has the
  same sampled deals. Matched CPU can give different block counts.
- Compare signed regret and uniform averaging, signed regret and linear
  averaging, and clipped regret and linear averaging. The first uses
  the existing trainer. The signed pair isolates averaging at fixed
  block counts. The linear pair compares the regret update under the same
  averaging schedule. Exact comparisons measure each end-to-end policy.
- Freeze both players' current strategies for a crossed block. At block
  index t starting at one, linear averaging adds t times the own-reach
  policy increment. The clipped variant aggregates all regret increments
  for each private hand, including repeated samples, before flooring the
  touched rows at zero. Both seats update simultaneously. Sampling a
  regret increment and then clipping is nonlinear. The update is a
  measured variant and carries no deterministic CFR+ guarantee.
- Rotate the six training slots in one-second CPU slices. Checkpoint at
  3, 7 and 15 training CPU seconds, recording clock time and completed
  blocks. Keep the existing 32,768-block and 45 training wall-second
  guards and use complete frozen blocks. Exact full-history BR and EV
  evaluation is outside the training clock. Continue using the bridge
  graph and table caps.
- For each variant versus signed-uniform, require all checkpoints within
  5% of their CPU targets. At 15 seconds require NashConv median ratio
  at most 0.95, worst ratio at most 1.10 and at least three of four wins
  separately at both recalls. Treat the comparison between the two
  linear methods as a diagnostic. Compare the absolute recall-one and
  recall-two results separately. Preserve every regression.

The evaluator scores both seats by traversing every public history of each
ten-bid fixture and pooling hidden opponent hands. It uses float64. The
study does not evaluate any strategy over the full-rule bid menu, and the
existing full-rule response-search admission gate applies.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_regret_updates.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_regret_updates.py -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Pass `--out-dir` for a
fresh run. The receipt preserves all 72 scores and their policy
fingerprints. The archive contains the 24 final policies. Timed
training counts depend on the machine. Recorded counts and seeds
permit replay independent of the CPU clock.

## Recorded outcome

All 72 checkpoints reach their targets at the resolution of the
recorded CPU clock. The [receipt](outputs/regret-updates.json) preserves
both response values, self-play EV and block counts. The [archive](outputs/regret-updates-policies.npz)
retains the 24 final policies. The run took 367.60 elapsed seconds and
362.70 CPU seconds, with a 66.28 MiB Windows peak working set.

Each cell reports a median paired NashConv ratio. Values below 1
indicate lower NashConv. Wins use the 15-second target.

| Recall | Variant / control | 3 s | 7 s | 15 s | Final wins |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | signed-linear / signed-uniform | 0.688 | 0.815 | 0.971 | 3/4 |
| 1 | plus-linear / signed-uniform | 1.200 | 1.343 | 1.486 | 0/4 |
| 1 | plus-linear / signed-linear | 1.749 | 1.667 | 1.531 | 0/4 |
| 2 | signed-linear / signed-uniform | 0.606 | 0.618 | 0.622 | 4/4 |
| 2 | plus-linear / signed-uniform | 0.876 | 1.097 | 1.296 | 0/4 |
| 2 | plus-linear / signed-linear | 1.460 | 1.835 | 2.140 | 0/4 |

With two-bid recall, signed-linear improves all four comparisons at
every checkpoint. At 15 seconds it reduces median paired NashConv by
37.8%. The absolute median changes from 0.04245 to 0.02782. With
one-bid recall the final median ratio is 0.971, above the predeclared
0.95 cutoff. In q3/490172 NashConv rises from 0.03280 to 0.03512.
The combined criterion therefore fails. Signed-linear two-bid recall
beats signed-linear one-bid recall in two of four final fixture/seed
comparisons, with absolute medians 0.02782 and 0.02459 respectively.

The clipped variant loses all eight final comparisons against
signed-uniform and all 24 checkpoint comparisons against signed-linear.
Its final median block counts are 12,100 and 2,802.5 at recall one
and two, versus 12,347 and 2,905.5 for signed-linear. These comparisons
measure end-to-end training under the same CPU budget. They apply to
this simultaneous clipped update on sampled crossed blocks.
