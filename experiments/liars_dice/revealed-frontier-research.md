# Revealed-hand frontier bounds (#49)

The prepared gap search from [#61](response-kernels-research.md) uses
challenge as a feasible continuation at unexpanded nodes and treats every
unresolved outcome as a win for its upper value. This study replaces that
optimistic value with the value of a relaxed continuation. In the relaxed
game, the responder learns the opposing hand when it reaches the frontier.
The target still plays the same frozen policy.

For each known deal, the oracle backs up the maximum at responder turns
and the target's expected value at opponent turns. It computes these
values in reverse public-graph order. At an unexpanded node the search
averages the values over the actual unnormalized opponent-hand reach.
Every feasible continuation is available in the revealed game, so this
value bounds the feasible best response from above. The original
reach-weighted +1 cap remains available and the search takes the smaller
upper value. These are float64 structural bounds.

Full-history targets keep every public history separate in the oracle.
The validated cached one-bid target can share known-deal values across
histories with the same acting seat and last bid. The legal continuations
and the frozen target's behavior agree under that key. Search beliefs
still use full histories, and the deployed lower plan uses only the own
hand and full public history. Revealed values can change expansion
priority. They never supply the lower plan's actions.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_revealed_frontier.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The
[receipt](outputs/revealed-frontier.json) records source and target
fingerprints, bounds, work counts, independent replay results and timing
blocks for the six #60 targets. The control and candidate use the same
prepared claim and branch kernels. The fixture schedule uses caps
1, 2, 4, 8 and 16, plus a 4,096-node closure check against the exact
hidden-hand best response. A separate scalar per-deal recursion checks
the oracle's matrices on a full-history target and on a cached one-bid
target.

The new frontier's pilot gate requires a median ratio of summed upper
slack of at most 0.70, no matched-cap increase in the upper endpoint above
0.02, and at most 1.25 times the prepared control's CPU to reach an
interval width of 0.02, including oracle construction. Upper slack is the
distance from the upper endpoint to the exact fixture best response. The
CPU comparison reports the median of three block ratios. Each block
contains 48 fresh solves per target and seat. The receipt separates
oracle construction from search, so readers can also evaluate reuse.

The oracle checks state, memory and pair-edge limits before allocating
the dense table. A separate static inventory counts 300 states and
22,644 action edges for the full-rule one-bid graph. With 252 hands per
seat, that implies about 147.3 MiB of estimated pair-matrix storage per
seat, including scratch, and 1.438 billion deal/action combinations.
Those counts estimate the graph workload. Process memory and runtime
depend on the actual target and execution.

## Recorded outcome

The revealed frontier reduces summed upper slack in all 12 seat/target
cases. The median slack ratio is 0.376 and the median summed-width ratio
is 0.469. The largest matched-cap upper increase is 1.39e-17 from
roundoff. All 24 exhaustive intervals match the independent best response
within 2.23e-16 at both endpoints. All 168 independently replayed lower
values agree within 3.34e-16.

| Operating point | CPU including oracle setup | Search-only CPU | Wall time including oracle setup |
| --- | ---: | ---: | ---: |
| Cap 16 | 3.078× | 1.135× | 3.161× |
| Width ≤ 0.02 | 4.821× | 1.037× | 4.769× |

Ratios compare the revealed frontier with the prepared +1 control.
The candidate reaches width 0.02 with fewer expansions in 9 of 12 cases
and the same number in the other three. Search-only CPU is close at that
precision, while constructing the table exceeds the 1.25× gate. The
full-rule pilot remains deferred. The static full-rule inventory above
is the only new full-rule measurement in this milestone.

The fixture study took 30.57 wall seconds and 30.28 CPU seconds with a
54.00 MiB Windows peak working set.
