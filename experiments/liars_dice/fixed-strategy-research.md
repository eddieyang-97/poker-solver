# Fixed-strategy graph validation and recall inventory (#49)

This milestone implements and independently checks a small fixed-strategy graph
trainer. It does not train a new five-dice house-rule policy. The next experiment
is a bounded one-bid-recall trainer, conditional on the checks below; three-bid
recall is not a practical dense starting point.

## Reference and rule compatibility

The structural reference is Neller and Hnath's
[FSICFR paper](https://cs.gettysburg.edu/~tneller/papers/acg2011.pdf).
Its useful idea is to freeze policy probabilities while accumulating forward
reach and computing backward values on a directed acyclic graph. Our experiment
uses **signed cumulative regret and simultaneous updates**, not the paper's
Algorithm 2 visit-normalized regret recurrence. It is an FSICFR-inspired
implementation, not a reproduction of the paper's published training results.
Both bounded-recall representations are imperfect-recall abstractions; the
perfect-recall equilibrium guarantee does not apply to them.

The independent executable reference is **OpenSpiel 2.0.2**, its C++ CFR trainer,
tabular best-response/NashConv evaluator and expected-return evaluator. The
Apache-2.0 wheel is installed only in an ignored, isolated research environment.
No third-party source or binary is vendored, and no runtime/CI dependency is
added. `outputs/fixed-strategy.json` pins the actual wheel, binary and relevant
packaged C++ source hashes, plus dependency versions. The driver verifies that
the supplied wheel contains the same evaluated binary and packaged sources.
This is execution of the published binary, not a fresh source build.

| Property | Matched OpenSpiel reference | Confirmed house game |
| --- | --- | --- |
| Private dice | One die each, 3 or 6 sides | Five six-sided dice each |
| Wild face | Highest-numbered face | Ones, only in 飞 for non-one claims |
| Modes | None | 飞 and 斋 |
| Raise order | `reset-face`: quantity, then face | Same-mode quantity/face plus cross-mode rules |
| Opening / cap | Quantity 1 / 2 | Quantity 3 / 14 |
| Special counts | None | Per-hand six/seven bonuses |
| Terminal utility | One challenge, winner +1 / loser -1 | Same single-round utility |
| Subsequent rounds | Not modeled | Fresh independent round |

Neither reference fixture is the paper's complete changing-dice match. The paper
also orders wild-face bids differently. We explicitly match OpenSpiel's selected
variant; published Dudo values cannot be substituted for this game. The existing
one-face reference supplies a general full-history tuple-tree evaluator, not a
claim that its original game is identical to either fixture.

## Algorithm and independent checks

`PublicGraph` keys nodes by `(seat, public suffix)`, using complete history when
recall is `None`. Policy/regret rows additionally use **only the acting player's
own private hand**. The last bid fixes legal actions and terminal scoring.
Strictly increasing bid rank makes the graph acyclic, including quantity-reducing
house-rule mode switches. Early histories shorter than the recall limit are
retained in full; longer histories merge by exactly the last m bids and seat.

For each frozen policy pass, separate forward arrays sum player-0 and player-1
reach across all paths to each node. Backward values use player-0 utility. Each
action's regret increment is its advantage times the **opponent's** summed reach
and chance weight, summed over hidden opponent hands. The average-strategy
increment uses the **acting player's** summed reach. All increments are applied
after the complete pass; regrets remain signed. No regret clipping, smoothing,
visit multiplier or probability threshold is inserted.

The tiny trainer enumerates private deals exactly in matrix scratch. It never
stores a distinct policy row for each opposing hand. This exact-deal matrix design
is deliberately rejected for the 252-hand full game by a tiny-reference guard;
the next trainer must sample chance correctly instead of allocating that scratch
over the full house-rule graph.

The scalar oracle recursively walks every complete history and private deal,
independently accumulates reach and pools increments into the abstract rows. It
does not use graph reach arrays or shared continuation values. Tests compare
every regret/average entry and root EV for full recall, one-bid and two-bid recall,
including zero-probability branches and repeated updates. In particular, an
opponent-unreachable path is not automatically counterfactually irrelevant.

External parity traverses every private pair and legal public tree in both
engines, checking chance distributions, legal actions, actor, own-information
strings, terminal outcomes and utilities. Both trainers start independently from
uniform play. OpenSpiel uses its alternating-update CFR; our trainer updates
simultaneously. Equal iteration numbers are not identical algorithms or equal
work budgets, and timing is not a speedup claim.

Every exported candidate is evaluated by both the existing full-history
tuple-tree evaluator and OpenSpiel's C++ evaluator. The two values for EV and
NashConv must agree within `1e-10`. Each perfect-recall trainer must achieve
NashConv <= 0.06 after the configured run; this predeclared tiny-game gate is not
a full-game quality requirement. No convergence gate is falsely applied to the
bounded-recall controls. We compare evaluated policies rather than demanding
identical mixed frequencies from different training algorithms.

Full three-sided policy tables are retained for all four trainers/controls.
Ordinary CI replays these tables and verifies receipt/source hashes without
installing OpenSpiel. That is offline replay, not new external training. Six-sided
policies retain canonical hashes, exact inputs and fresh independent evaluations;
rerunning the driver regenerates them. Training is deterministic exact chance
enumeration, so no training seed or sampling confidence interval is applicable.
The randomized recurrence probe records seed 490001.

## Observed tiny-game results

The recorded run completed 1,000 iterations for each trainer/control on each
fixture. All game-parity checks passed: 576 decision / 567 terminal states for
the three-sided game and 147,456 decision / 147,420 terminal states for six sides,
including all 9 and 36 private pairs respectively.

| Sides | Trainer / recall | EV, seat 0 | Full-history NashConv | Training wall seconds |
| --- | --- | ---: | ---: | ---: |
| 3 | Independent OpenSpiel CFR | 0.110525 | 0.001692 | 0.81 |
| 3 | Graph, full recall | 0.106552 | 0.006251 | 1.53 |
| 3 | Graph, last bid | 0.107065 | 0.044867 | 0.56 |
| 3 | Graph, last two bids | 0.107358 | 0.005423 | 0.92 |
| 6 | Independent OpenSpiel CFR | -0.027389 | 0.005318 | 119.83 |
| 6 | Graph, full recall | -0.026647 | 0.038396 | 212.88 |
| 6 | Graph, last bid | -0.001180 | 0.469941 | 2.83 |
| 6 | Graph, last two bids | -0.025298 | 0.180511 | 11.69 |

NashConv is the sum of both players' best-response improvements; exploitability
under this repository's convention is half. These are full-history evaluations
of the specified tiny games, not restricted-recall response bounds. Both
perfect-recall baselines pass the predeclared 0.06 gate. The independent trainer
converges faster here; no graph speed advantage over OpenSpiel is established.
The bounded-recall cases are cheaper but the six-sided results expose substantial
remaining vulnerability. Similar self-play EV does not establish strategic
strength, and the three-sided two-bid result does not prove abstraction harmless.

Maximum graph/scalar increment error was 4.45e-16; independent EV/NashConv
comparisons differed by at most 2.09e-16. The complete experiment took **387.31
wall / 382.55 CPU seconds**. Process peak working set was **481,161,216 bytes
(458.87 MiB)**, including both trainers and all evaluation/export work. This is
not a per-policy serving footprint or a pass under a hosted 384 MiB limit. A
three-sided pilot preceded the complete run; its numerical results agree. An
initial driver setup attempt used an incorrect packaged source filename and
failed before training; the completed receipt pins the corrected driver.

## House-rule inventory

`recall_inventory.py` counts reachable actor parities and legal suffix paths by
dynamic programming, without allocating private-hand/action tables. A separate
explicit graph traversal verifies the one- and two-bid results in tests.

| Recall | Public states incl. seat | Infosets (252 hands) | Legal action entries | Two float64 tables |
| --- | ---: | ---: | ---: | ---: |
| 1 | 300 | 75,600 | 5,706,288 | 91,300,608 bytes / 0.085 GiB |
| 2 | 22,346 | 5,631,192 | 283,347,540 | 4,533,560,640 bytes / 4.22 GiB |
| 3 | 1,102,051 | 277,716,852 | 10,479,494,088 | 167,671,905,408 bytes / 156.16 GiB |

These are calculated dense regret/average storage sizes, **not measured RSS**.
They include forced-action rows, keep both seats distinct and preserve all legal
actions. They exclude graph metadata, current strategies, scratch, allocator
overhead and checkpoints. Float32 halves these two arrays but requires separate
numerical validation and does not make the three-bid baseline small. The paper's
state counts concern a different game and representation.

## Reproduction

From the repository root, create an isolated environment and download the wheel
appropriate to its Python/platform. For the recorded Windows/Python 3.14 run:

```powershell
.venv/Scripts/python.exe -m venv .deps/fsicfr-env
.deps/fsicfr-env/Scripts/python.exe -m pip install -r experiments/liars_dice/requirements-reference.txt
.deps/fsicfr-env/Scripts/python.exe -m pip download --no-deps --only-binary=:all: open_spiel==2.0.2 -d .deps/fsicfr-download
$env:OPENBLAS_NUM_THREADS='1'
.deps/fsicfr-env/Scripts/python.exe experiments/liars_dice/run_fixed_strategy.py --iterations 1000 --wheel .deps/fsicfr-download/open_spiel-2.0.2-cp314-cp314-win_amd64.whl
.venv/Scripts/python.exe -m unittest discover -s experiments/liars_dice/tests -v
```

On another platform use its wheel filename and virtualenv executable. The
receipt captures dependency versions and exact artifacts; verify those when
comparing floating-point output. The default driver runs 1,000 iterations on
both 3- and 6-sided 1v1 fixtures. It writes running/completed/failed status and
checks that source hashes did not change during the run. Failure leaves the
completed earlier cases and failure reason on disk, not a success receipt.

The process peak includes the external trainer, graph trainers, policy exports
and independent evaluators, not just a trainer's allocation. Per-trainer timings
exclude evaluation/checkpoints; total wall/CPU includes parity and evaluation.
These are local Windows measurements, not hosted budgets or Linux acceptance.

## Next implementation decision

Proceed first with a standalone one-bid-recall house-rule training experiment:
all 252 hands, every legal bid, chance-sampled forward/backward passes, bounded
arrays, explicit cumulative/averaging equations, multiple seeds and checkpoint
exports. Validate the chance estimator against this exact-deal reference before
long training. Retain the existing population and probability controls.

Evaluate using full-history responders in the unabstracted house game. The
trainer may forget history; the evaluator must not inherit that restriction.
Use independent held-out responses and #47's continuation bounds, retaining the
strongest valid lower bound for each frozen target. Lower lower bounds or wins
against the training opponent do not establish lower true exploitability.

Two-bid training requires a measured memory/time case first. Defer dense
three-bid training, GPU acceleration and ReBeL-style value learning. A learned
table needs a separately versioned research artifact and adapter; the accepted
snapshot loader supports the specific historical prior/Bayesian population.
No automatic export into #50, model replacement, recommendation feature or
deployment follows from this study. #49 remains open for strategy-quality work.
