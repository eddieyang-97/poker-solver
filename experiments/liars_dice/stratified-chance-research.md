# Training quality under stratified private-hand sampling

Issue #49 asks how training budget and public recall affect the quality
of learned policies. This experiment changes the private-hand sampler of
the existing crossed-block trainer on both six-bid house fixtures.
The control draws eight hands independently per seat. The candidate
draws one hand from each of eight equal-mass strata per seat in the
fixture's existing hand-profile order. Each seat draws independent
offsets, and the trainer evaluates all 64 cross-seat pairs.

For a hand with integer multiplicity (w), its interval contains
(8w) tickets. Each of the eight strata contains 7,776 tickets and
supplies one uniform integer ticket. The expected number of occurrences
of that hand per list is therefore (8w/7776). Independence between
seats gives the original expected multiplicity of every crossed pair.
The frozen-block update sums the individual pair contributions, so its
expectation is preserved for both regrets and average-policy updates.
Correlations within each seat's list change. Adaptive training quality
therefore requires measurement.

The experiment uses the axis trainer, batch size eight, recall of one
bid, two bids or full history, and seeds 490131–490133. Each paired run
has checkpoints at 256, 1,024 and 2,048 blocks. The budget covers 36
trajectories and 73,728 training blocks in total. Fixed counts match
sampled pairs and graph passes within a recall setting. Larger recall
graphs cost more per pass. The receipt reports actual training CPU and
wall time separately from evaluation.

The full-history evaluator enumerates both best responses against each
frozen policy. NashConv is their summed value in this zero-sum game.
The [receipt](outputs/stratified-chance.json) records both seats, policy
fingerprints and all matched outcomes. The [policy archive](outputs/stratified-chance-policies.npz)
retains every checkpoint for replay. The tests exhaustively enumerate
a small nonuniform chance law, including a zero-probability hand and
duplicate draws, and evaluate the saved tables independently of training.

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_stratified_chance.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -p test_stratified_chance.py -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. Use `--out-dir` to
generate a fresh receipt and archive in a separate directory. The
comparison is descriptive across two fixtures and three paired seeds.
The installed policies, strategy advice and full-rule search admission
require separate evidence.

## Recorded outcome

| Public recall | Median stratified/IID NashConv at 256 blocks | At 1,024 | At 2,048 | Final wins | Final median training CPU ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| One bid | 0.812 | 0.872 | 0.897 | 4/6 | 0.942 |
| Two bids | 0.800 | 0.758 | 0.734 | 6/6 | 1.004 |
| Full history | 0.803 | 0.857 | 0.762 | 6/6 | 1.002 |

At 2,048 blocks, median full-history NashConv over the three seeds is
0.011253 on q2 and 0.020646 on q3 for stratified sampling, compared
with 0.015819 and 0.024606 for IID. With one-bid recall, stratification
increases final NashConv by 5.2% on q2/490132 and 15.8% on q3/490131.
The two fixtures share rules and all runs use the same profile ordering,
so the observed wins may depend on that ordering.

The run took 236.53 seconds elapsed and 234.23 CPU seconds, including
evaluation and archive creation, with a 46.23 MiB Windows peak working set.
