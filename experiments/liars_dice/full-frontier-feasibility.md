# Bounded full-rule frontier feasibility (#49)

[The #63 owner review](https://github.com/eddieyang-97/poker-solver/pull/63#issuecomment-6778611143)
requested full-rule-shaped feasibility evidence while retaining the
1.25× fixture admission gate. This study exercises the factored
one-reply bound on fixed query corpora. It uses the confirmed 252-hand
game and the archived axis and reference policies for seed 490061.
Targets and probabilities match the #59 fingerprints.

- **Opening fan-out.** For seat 0, enumerate every legal own opening and
  every positive-reach target reply. For seat 1, enumerate positive-reach
  target openings. Exclude challenge terminals at the opponent turn.
  Each observed bid scales the prior by the frozen target's actual
  likelihood.
- **Reachable-state inventory.** For every reachable nonopening
  seat/last-bid key, use its shortest legal full history with actual
  opponent reach and its longest legal full history with prior stress
  weights. The latter ensures coverage even where a path has zero
  target support. A prior stress query is a synthetic input, separate
  from the historical posterior.

Both methods use exact challenge scoring at forced challenge nodes.
At other nodes the prepared control uses reach-weighted +1. Factored
reply scores immediate challenges and uses +1 after any opponent
raise. It can give a looser upper bound than a fully revealed
continuation at other histories. Neither workload chooses a responder
action, runs a response search, or generates a new game-level bound.
Aggregate sums of returned vectors are reproducibility checksums.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_full_frontier_feasibility.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The
[receipt](outputs/full-frontier-feasibility.json) pins the source and
target fingerprints, query hashes, support counts, timings and resource
measurements. Every query is checked on eight declared responder hands
against direct maximization over legal actions, with separately scored
raw dice and the scalar frozen-policy API. All 252 factored values per
query are also checked between immediate challenge and reach-weighted
+1.

There are five alternating timing blocks per target, seat and workload.
Factored uses 2 fresh passes per block for seat 0 opening fan-out, 16 for
seat 1 opening fan-out and 12 for each inventory. Prepared uses 32,
2,048 and 1,024 respectively, because the first timing pass showed
zero-tick CPU readings on its smallest workloads. Each method's block
totals are divided by its own pass count. A fresh pass constructs an
empty oracle and measures its creation and queries together. Cache reuse
within a pass is included. Input construction and independent checks are
outside the timing. The receipt retains process CPU and wall time in
nanoseconds. The host CPU clock still has finite resolution. These
ratios measure kernel overhead at fixed work, while the fixture gate
compares complete searches at matched interval precision.

Each pass allows at most 25,000 opening candidates, 32 MiB of estimated
pair-cache and scratch storage, and two billion counted pair operations.
Separate inventory probes lower the limits to 1 MiB and four million
pair operations and must stop without returning a value for the failed
query. The process guard runs between batches. Separate fresh subprocesses
run the same fixed workload once for each method to measure whole-process
peak memory with a 60-second timeout. Pair-cache estimates and whole-process
peaks describe different resource scopes.

## Recorded outcome

All 22,148 fixed queries complete for both methods across the two
targets. Each seat 0 opening batch has 10,332 queries. The inventory
reaches 150 bids and 150 legal actions. The 177,184 independent values
agree within 5.56e-16. For all four target/seat cases, the 1 MiB probe
stops after 12 completed queries and the four-million-operation probe
stops after 14.

| Workload | Queries per target | Prepared median wall per pass | Factored median wall per pass |
| --- | ---: | ---: | ---: |
| Seat 0 opening | 10,332 | 13.7–19.9 ms | 574–736 ms |
| Seat 1 opening | 144 | 0.176–0.188 ms | 79.4–81.2 ms |
| Inventory, either seat | 298–300 | 0.367–0.378 ms | 90.2–98.4 ms |

Ranges span the applicable target/seat medians. Factored seat 0 opening
wall time spans 541–838 ms across individual blocks. The smallest
process CPU total for any timing block is 0.344 seconds after extending
prepared repetitions. The fixed-pass overhead is largest when the
query batch has few leaves over which to spread cache construction.

The largest cache-plus-scratch estimate is 18.52 MiB and the largest
counted workload is 1.366 billion pair operations. Both fall below the
declared per-pass limits. In separate processes, prepared and factored
peak at 221.04 and 220.92 MiB, respectively. Those process peaks include
loading the policies and building the full query arrays. Their small
difference does not isolate the oracle's memory. The complete study
takes 85.25 wall seconds and 81.19 parent CPU seconds with a 223.88 MiB
parent peak.

The measurements establish feasibility for these fixed corpora only.
The [#63 fixture admission result](frontier-cost-research.md) remains a
no-go. A search that chooses which frontiers to evaluate still needs
its own cost and bound-quality evidence.
