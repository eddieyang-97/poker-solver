# Chance-sampled one-bid-recall house-rule training (#49)

This experiment trains fresh behavioral policies for the confirmed five-dice
game using one-bid recall, exact private hand types and every legal action. It
follows the independently checked graph recurrence in merged PR #53. It is an
offline research candidate; the imperfect-recall abstraction has no general
equilibrium guarantee and does not change the MCP analysis model.

## Training definition

The abstract key is `(seat, own exact multiset, last bid)`, plus the opening.
Both actor parities are retained. The reachable graph has 300 public nodes,
75,600 information sets and 5,706,288 legal hand/action entries. Two contiguous
float64 arrays for signed cumulative regrets and average strategies use exactly
**91,300,608 bytes**, excluding graph metadata, scratch and frozen copies.
The allocation guard applies to those two arrays; it is not a process-memory
limit. Frozen output and verification copies are measured in the process peak.

Each iteration samples two private hands independently from the actual weighted
252-multiset distribution. It freezes the current regret-matching policy, then
visits **every** public graph edge. Forward passes accumulate each player's reach
over merged paths. Backward passes compute player-0 values, counterfactual regret
increments weighted by the opponent's reach, and average-strategy increments
weighted by the acting player's reach. Updates apply only after the full pass and
only to the sampled own-hand row for each seat. Policy choice never receives the
realized opposing dice. The deal is used for terminal utility and expectation.

There is no action sampling, importance-ratio division, regret clipping, warm
start, pruning or probability guide inside training. The chance distribution is
the sampling distribution, so its weight cancels in the sampled update. Tests
sum updates over **nonuniform** tiny-game chance outcomes and compare every entry
with the exact-deal graph trainer. Both regret and averaging expectations match.
Sampling introduces variance; this is not an exact full-deal training pass.

The output is the normalized accumulated **average policy**, not the final
regret-matching policy. Unvisited own hands use a uniform legal-action fallback;
receipts report unseen type counts, their prior mass and every hand's sample
count for both seats. Training completion is not a coverage or convergence gate.

## Reproducible policies and evaluation

Three predeclared training seeds (490011, 490012, 490013), checkpoints at 1,000 and
5,000 iterations, and independent evaluation seeds are fixed before the main run.
No checkpoint or seed is selected after observing results. The numerical receipt
records exact source hashes, rules, software/platform, training costs and maximum
summed graph reach. Final policies are exported losslessly to compressed NumPy
archives with schema/rules/hand/state/action identity, normalized float64
probabilities, file SHA-256 and raw little-endian probability-array SHA-256.
Loading rejects incompatible layouts/rules and invalid distributions. Exported
policies are reloaded and compared exactly before reporting success. No archive
is a hosted/runtime import.

Every checkpoint is tested with #47's **full-history** continuation responder,
using depth one and 32 expanded own public nodes per seat. Each expanded node
retains every legal raise and nonzero opponent response. At an unsearched frontier
the feasible policy challenges and the optimistic upper value is +1. Thus the
sum of the two response values supplies a NashConv lower bound; the sum of upper
values supplies a structural upper bound, all evaluated in float64 without
outward rounding. The responder retains complete histories, even though its
target policy forgets them. This is not a best response restricted to one-bid
recall, and it is not an exact unrestricted BR computation.

The extracted full-history response policies are independently replayed with
2,000 fresh sampled games per seat. Replay reads raw dice for terminal scoring,
not the search count histograms or returned bounds. Individual 95% Hoeffding
intervals are recorded. They are not simultaneous intervals across all tests;
occasional misses are retained and flagged rather than deleted or treated as
deterministic implementation failures. Exact deployable-payoff/BR equality is
also tested on the tractable one-face fixture. Full-rule replay is sampled, not
an exact 63,504-deal deployment certificate.

Final candidates are additionally tested in both seats against predeclared
probability-only opponents with thresholds 0.3 and 0.7. These fixed held-out
opponents are independent of training; they do not establish broad strategic
robustness. Uniform and probability-0.5 controls receive the same continuation
search budget. Smaller response lower bounds alone never establish stronger
play. The historical guide lower bound (~1.3078) and frozen 23-policy interval
[1.474843, 1.928530] remain valid for their respective unchanged targets; a weaker
new diagnostic does not supersede those results or make the targets comparable
by lower endpoints alone. Historical corpora are preserved.

## Reproduce and scope

From the repository root, using the normal project environment:

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_recall_training.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. No OpenSpiel installation is
required for this experiment. Defaults are all three seeds, both checkpoints,
2,000 replay games and 32 search nodes per seat. The 900-second experiment guard
checks between iterations and major evaluations; it is not a hard deadline.
The driver durably records running/completed/incomplete status, completed
checkpoints, failures and process peak memory, and rejects source changes during
execution. A completed receipt must not be inferred from a successful earlier
checkpoint. The pilot used 20 iterations, 200 replay games and 8 search nodes;
it was a setup check, not part of the main quality comparison.

All evidence is local Windows/Python. Process peak includes training arrays,
exports, reload verification and evaluations across seeds, not just a serving
policy. No Linux address-space, provider, live client or hosted-budget claim is
made. The accepted frozen-policy analyzer and its model are unchanged.

## Recorded results and decision

The complete run finished in **299.67 wall / 297.52 CPU seconds**, with measured
process peak working set **319,746,048 bytes (304.93 MiB)**. Training alone used
65.69, 67.19 and 66.64 CPU seconds for the respective 5,000-iteration seeds. The
remainder includes controls, checkpoint evaluation, sampling, exports and reloads.
These are observed offline costs, not a comparison with a hosted budget.

| Seed | Iterations | Full-history NashConv lower | Structural upper |
| --- | ---: | ---: | ---: |
| 490011 | 1,000 | 1.822073 | 1.934355 |
| 490011 | 5,000 | 1.652970 | 1.873628 |
| 490012 | 1,000 | 1.826253 | 1.936746 |
| 490012 | 5,000 | 1.655147 | 1.872147 |
| 490013 | 1,000 | 1.821973 | 1.935405 |
| 490013 | 5,000 | 1.658396 | 1.871141 |

All six learned checkpoints remain substantially exploitable. Similar outcomes
across seeds do not establish convergence. The falling diagnostic lower bounds
do not prove a reduction in true exploitability between checkpoints. Every
extracted-response replay fell within its individual 95% Hoeffding interval;
those sampled checks do not replace exact full-rule deployment certification.

For final policies, all twelve held-out probability-opponent payoff means were
negative, ranging from **-0.367 to -0.057** in the candidate's utility. Intervals
and exact evaluation seeds remain in the receipt; these are not simultaneous
significance claims. The weakest negative mean's individual interval includes
zero. The equally budgeted uniform control has NashConv interval approximately
[1.964717, 1.998010]; the prior-0.5 control's new probe gives [0.442889, 1.901628].
The latter is a weaker diagnostic than its retained historical lower bound, not
evidence that the old guide became stronger.

Coverage improved but is incomplete: at 5,000 iterations, unseen types still use
uniform play. Counts, actual per-type samples and prior mass are retained for
each seat. The three compressed final snapshots total 16,071,824 bytes; each is
lossless float64, carries full rules/layout identity and is versioned alongside
the receipt. This footprint differs from the two training arrays and process
peak. Ordinary tests load and verify the snapshots and source fingerprints.

**Decision:** accept this as a reproducible bounded training/negative-quality
experiment. Do not promote these policies as recommendations, a new MCP model or
full-game GTO. The current run does not separate finite training/coverage limits
from intrinsic recall loss. Before increasing representation size, compare
longer seeded learning curves with richer-recall controls on tractable matched
fixtures, keeping full-history response evaluation. Dense two-bid tables remain
a separate memory/precision design question; further compute is not automatically
a quality improvement. Keep #49 open for stronger strategies and quality bounds.
