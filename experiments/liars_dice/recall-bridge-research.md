# Matched-CPU recall with all 252 private hands

Issue #49 follows the [held-out stratification study](stratified-holdout-research.md)
with larger exact-evaluation games and a three-bid recall control. The original
profile order improved at richer recall on the previous fixtures. This study
tests that specific ordering with every physical hand type and all six opening
fly faces.

## Protocol

- Use the ten retained bids `3 fly` on faces 1–6, `q zhai` on faces 2 and 4,
  and `(q+2) fly` on faces 2 and 4, for q = 2 and q = 3. Use the confirmed
  house opening, raise, challenge and payoff rules within each menu. The
  opening menu also admits later retained fly bids and the q3 zhai bids.
  Retain all 252 exact unordered hands with original integer weights.
- Compare IID and profile-ordered strata in the same axis-reduced trainer.
  Each block combines eight draws per seat into 64 crossed pairs. The fixed
  order is lexicographic by the ten contribution counts in the declared bid
  sequence. Training recall is one, two, three or all public bids. Complete
  history is always available to the evaluator.
- Pair seeds 490161–490163 on both menus. Rotate the eight training slots in
  one-CPU-second slices and evaluate at 1, 3 and 7 training CPU seconds.
  The training clock includes draws and both-seat updates. Each trajectory
  caps at 32,768 blocks and 45 training wall seconds, checking before each
  block. Graphs cap at 1,024 public states and mutable regret plus average
  arrays at 32 MiB per trainer. Report actual CPU, wall time, block counts,
  each seat's sampled hand count and mass, and multi-action information
  rows with positive own-reach average weight.
- At the final checkpoint, require profile/IID NashConv median at most
  0.95, worst ratio at most 1.10 and at least four of six wins separately
  at recall two, three and full. All checkpoints must be within 5% of
  their CPU targets. This is a decision rule for the larger restricted
  fixtures. The one-bid results and all regressions are retained. Compare recall
  depths descriptively using the absolute values at the same CPU.

## Exact evaluation

The evaluator traverses every legal public history in the ten-bid game.
Its mass vectors include each seat's exact prior and its own action reach.
At a challenge it groups the opposing mass by integer contribution
(0 through 7) for the bid. For each own hand, the truthful mass is the
tail starting at the bid quantity minus the hand's count. Twice the
truthful mass minus the total gives the signed utility against that mass
when player 1 challenges. Player 0's challenge reverses the sign.

The fixed-profile EV sums each terminal using both reaches. Each best
response sums at opposing nodes and maximizes over legal actions at its
own nodes after integrating the hidden-hand mass. A branch with zero
frozen own action probability can still be a best response. The response
policy needs only its own hand and the complete public history.
Tests compare the grouped evaluator with the independent dense traversal
from the prior study and check the integer-count tail against direct deal
payoffs.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_recall_bridge.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_recall_bridge.py -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Use `--out-dir` to
write a fresh run separately. Training CPU controls the block counts,
which vary by machine. The receipt records counts and fingerprints for
all 144 checkpoints and the 48 final policy tables are archived. The
tests also reproduce a timed checkpoint by rerunning its recorded
block count with the same seed.

Exact fixture best responses use float64. Full-rule play has 150 reachable
bids. Its [dense table estimates](fixed-strategy-research.md) are 4.22 GiB
at two-bid recall and 156.16 GiB at three-bid recall before graph or working
memory. The existing full-rule response-search admission gate still applies.

## Recorded outcome

The two menus have 1,012 and 1,024 full-history states. At recall two
they have 90 and 92 states, and at recall three they have 253 and 260.
Both menus distinguish all 252 hands by their ten contribution counts.
The [receipt](outputs/recall-bridge.json) records all 144 checkpoints.
The [archive](outputs/recall-bridge-policies.npz) includes every final
policy. The run took 354.66 elapsed seconds and 351.31 CPU seconds,
with a 183.61 MiB Windows peak working set. The 144 exact grouped
evaluations took 9.81 CPU seconds in total.

The ratio columns give median paired profile/IID NashConv. Wins and
absolute median NashConv and block counts use the seven-second target.

| Recall | Ratio at 1 s | At 3 s | At 7 s | Wins | Median NashConv IID / profile | Median blocks IID / profile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.950 | 0.927 | 0.905 | 6/6 | 0.0606 / 0.0553 | 2747.5 / 2700.5 |
| 2 | 0.964 | 0.924 | 0.927 | 6/6 | 0.1415 / 0.1251 | 628.5 / 630.5 |
| 3 | 0.989 | 0.957 | 0.928 | 6/6 | 0.3278 / 0.2923 | 227.5 / 232.5 |
| Full | 0.989 | 0.994 | 0.968 | 5/6 | 0.7595 / 0.7423 | 58 / 58 |

The full-recall median ratio of 0.968 misses the 0.95 threshold.
At q2/490163, full-recall NashConv rises from 0.67280 to 0.67718
with both methods at 58 blocks. The variance reduction seen in
smaller games offers no guarantee of an adaptive improvement here.

Five of the 12 one-second full-recall checkpoints exceed the 5% CPU
tolerance, with a maximum overrun of 12.5%. These trajectories finish
whole frozen blocks. All three- and seven-second checkpoints are within
4.17% and 1.34% respectively. The timing and full-recall quality
conditions both fail. The late checkpoints are useful as descriptive
comparisons and do not pass the combined criterion.

At seven seconds, one-bid recall has the lowest NashConv in all 12
fixture/seed/sampler comparisons. Its median positive-average coverage
on multi-action rows is about 100%. Full recall reaches 69.4% for IID
and 71.3% for profile. The median of the lesser seat's sampled prior
mass at full recall is 85.3% and 86.6% respectively. The absolute
results favor one-bid recall at this budget. The ranking at longer
budgets remains unresolved.
