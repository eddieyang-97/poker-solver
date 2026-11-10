# Lower-cost revealed-hand frontier bounds (#49)

[The dense revealed-hand oracle](revealed-frontier-research.md) tightened
fixture best-response bounds, but its setup cost exceeded the full-rule
pilot gate. This study compares it with three demand-built variants on
the same six frozen targets and both seats.

| Method | Frontier upper value |
| --- | --- |
| Prepared | Weighted +1 with the prepared claim and branch kernels |
| Dense | The complete revealed-hand continuation, built in reverse graph order |
| Lazy | The same continuation, cached only for queried states and their dependencies |
| Reply | Exact challenge outcomes through one opponent reply, with +1 on any opponent raise |
| Factored | The same one-reply bound, using a rule mask and an opponent probability vector |

The reply bound considers immediate challenge and every legal raise by
the responder. After a raise, a known true claim has upper value +1. A
known false claim has upper value `1 - 2p`, where `p` is the frozen
opponent's challenge probability for that hand and public history. An
opponent raise receives +1 at this cutoff. This yields a valid optimistic
continuation and can leave more slack than the dense oracle.

The factored version identifies deals where the current bid is true and
every legal raise is false. Only those deals can have an upper value below
+1. On them, the loss term is twice the minimum challenge probability over
the available raises. With no legal raise, that probability is one. The
cache stores boolean rule masks separately from the opponent-hand vectors.
It contracts the mask with the vector weighted by the actual opposing
reach, without constructing the float payoff matrix for a search query.

The demand-built policy values cache by complete public history for
full-history targets. Only the validated cached one-bid target shares
known-deal matrices by acting seat and last bid. The search averages
these matrices against the actual history-dependent opposing reach.
All lower choices still use the responder's own hand and public history.
The demand-built oracles check a 192 MiB pair-matrix estimate and a
two-billion pair-edge work limit, including pending matrices and scratch.
A cap raises an error before returning an incomplete value.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_frontier_cost.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The
[receipt](outputs/frontier-cost.json) pins sources and the #62 fixture
receipt. Caps 1, 2, 4, 8 and 16 compare partial bounds. A 4,096-node cap
checks closure against the independently enumerated hidden-hand best
response. Every recorded lower plan is independently replayed. Separate
tests check exact cache parity and calculate the reply cutoff with
scalar payoffs and probabilities.

Cold timings use three rotated blocks of 48 fresh searches per seat
and target at cap 16 and the first integer cap reaching width 0.02.
Dense table construction is timed as setup. Lazy construction happens
during search and counts toward cold CPU. The #62 thresholds are
unchanged: median summed upper-slack ratio at most 0.70, maximum upper
increase at most 0.02 and cold width-target CPU ratio at most 1.25,
all relative to the prepared control. Pair-matrix estimates include
temporary storage and are separate from process-wide working set.

## Recorded outcome

The lazy exact bounds reproduce dense endpoints exactly. Direct reply
differs from dense by at most 6.94e-18 at recorded caps, and the factored
reply matches direct reply within 1.11e-16. This agreement concerns the
recorded fixture bounds. The one-reply cutoff can give a looser value at
other public histories. All 420 independent lower replays match within
3.34e-16. Both endpoints of all 60 exhaustive intervals match the
independent best response within 2.23e-16.

| Method | Median summed upper slack vs prepared | Cold CPU vs prepared at width ≤ 0.02 | Cold CPU vs dense at width ≤ 0.02 | Largest estimated matrix footprint |
| --- | ---: | ---: | ---: | ---: |
| Dense | 0.376 | 4.559× | 1.000× | 1,705,984 B |
| Lazy | 0.376 | 3.100× | 0.700× | 1,655,808 B |
| Reply | 0.376 | 1.853× | 0.401× | 501,760 B |
| Factored | 0.376 | 1.265× | 0.276× | 49,728 B |

All four alternatives have median summed interval width 0.469 times the
prepared control. Factored uses at most 4.6% of the dense matrix estimate
in every paired case. At the precision target, its cold CPU ratios
against prepared are 1.206, 1.265 and 1.400 across blocks. Median cold
wall time is 1.297 times prepared. The median CPU exceeds the 1.25× gate,
so the full-rule pilot remains deferred. Timing and matrix storage
estimates are for the six fixtures.

The complete fixture study took 83.32 wall seconds and 81.94 CPU seconds,
with a 55.56 MiB Windows peak working set.
