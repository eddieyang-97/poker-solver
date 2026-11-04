# Training noise and recall: matched restricted-house-game ablations (#49)

This study follows accepted PR #54, whose one-bid full-game policies retained
NashConv lower bounds above 1.65 after 5,000 sampled iterations. It compares
longer training and more history on explicitly smaller games. It does not solve
or certify the unrestricted five-dice game.

## Fixed fixtures and lossless private compression

Both players still independently roll five fair six-sided dice, with the owner-
confirmed fly/zhai scoring, per-hand bonuses, raise rules and single-round +/-1
utility. Each fixture retains only six named bids:

| Fixture | Allowed quantities/modes, each on faces 2 and 4 |
| --- | --- |
| q2 | 3 fly, 2 zhai, 4 fly |
| q3 | 3 fly, 3 zhai, 5 fly |

Legal actions are the intersection of those bids with the original legal action
set, plus challenge after a bid. Quantity-two zhai cannot open in q2. Bid fields
and legal raise ordering are unchanged; fixture IDs are renumbered in the table's
listed order, which is also the internal action enumeration. Omitted bids are unavailable,
and the last retained bid forces a challenge. Thus these are **action-restricted
games**, not ordinary full-game subgames or estimates of unrestricted NashConv.
Both fixtures exercise within-mode face ordering and both mode-switch directions.
Their low quantity limits do not test the full strategic effect of high bonus bids.

For this limited action set, two private hands with the same contribution to
**every retained bid** have identical payoffs and feasible behavior. They can be
merged losslessly: opponent dice are independent, and no other hidden hand detail
affects a future action or payoff. The 252 multisets collapse to 56 profiles,
retaining integer chance multiplicities out of 7,776. This compression is invalid
in the unrestricted game, where other faces/bids distinguish the hands.

The losslessness statement concerns payoffs and full-history evaluation of
profile-based policies, including unrestricted perfect-recall best responses.
It is not a claim that every **imperfect-recall** policy over 252 distinct hand
labels has an equivalent 56-profile behavioral policy: otherwise irrelevant
private labels can supply persistent private correlation. All three recall
levels here deliberately use the same 56-profile policy class. This controls the
comparison but is another reason not to transfer its conclusions directly to
#54's 252-hand policies. The expanded-type regression verifies evaluated values,
not equivalence of those two imperfect-recall learning spaces.

Tests enumerate all 7,776 ordered raw rolls using independent scoring, compare
profile multiplicities, directly check action fields, and compare EV and both
full-history best responses with an uncompressed 252-type version of q2. No
private-dice information is discarded beyond proven payoff equivalence in these
restricted games.

## Matched experimental design

Each fixture is trained at recall 1, recall 2 and full public history, with exact
private profiles. The implementations reuse #53's exact-deal recurrence and
#54's chance-sampled recurrence through bounded layout adapters. Existing source
and numerical receipts remain unchanged. Both methods use the same uniform
initialization, signed cumulative regrets, simultaneous frozen-strategy passes
and reach-weighted average-policy deployment.

Exact training enumerates all 56^2 private-profile pairs per iteration. Sampled
training draws one independent pair from the true weighted distribution. Three
fixed seeds (490021/22/23) use the same private-deal sequence across recall levels.
Checkpoints are 1,000, 5,000 and 20,000 iterations; none is selected after observing
results. Exact runs are deterministic and do not duplicate identical seeds.

Matched iteration counts isolate the effect of replacing expected updates with
sampled updates, **not equal data or equal compute**: exact iterations integrate
3,136 private pairs, sampled iterations one. Per-run CPU/wall times and table or
scratch estimates are reported, allowing the cost difference to be assessed.
The exact trainer has a 64 MiB array estimate guard, sampled tables a 32 MiB guard,
and both have a 1,000-public-node graph guard. These are allocation bounds for
these declared fixtures, not whole-process limits or serving budgets.

At each checkpoint, the independent tuple-history evaluator computes both-seat
best responses and NashConv with **full public history**, not with the trainer's
recall restriction. Chance is completely enumerated in float64. No sampled
evaluation interval or limited-response lower bound is substituted. Ordinary
floating-point tolerance remains; this is not rational or interval-certified
arithmetic. Perfect recall has the usual CFR convergence setting; imperfect
recall has no general guarantee.

Tests compare every adapter's update against scalar tree traversal and the
nonuniform-chance expectation of sampled updates. Final policies for all 24 runs
are exported as complete public-history tables, with file hashes. Ordinary CI
reloads and independently evaluates every final policy and checks source hashes.
The exports deliberately unroll abstract policies: the evaluation never forgets
history even when the trained policy does.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_recall_ablation.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/liars_dice/tests -v
```

Use the ordinary project virtual environment; no optional OpenSpiel dependency
is needed. PowerShell uses `$env:OPENBLAS_NUM_THREADS='1'`. The main driver records
source/rule/fixture definitions, chance weights, projections, all methods/seeds/
checkpoints, full-history values, resource measurements and explicit status.
The 1,200-second guard checks between iterations/evaluations, not as a hard kill.
An interruption records incomplete status and completed earlier work, never
implicit success. A two-iteration one-seed setup pilot preceded the main run.

All costs are local Windows measurements. Process peak includes training,
evaluation and policy serialization. No provider, Linux address-space or client
acceptance is implied. No hosted model, recommendation, NLHE or deployment change
is part of this research.

## Interpretation limits

A residual gap under exact-deal training shows that chance sampling alone does
not explain that run's remaining weakness. It does **not** prove a lower bound
on every policy representable at that recall: imperfect-recall learning dynamics
can also be responsible. Conversely, good results in these short fixtures cannot
explain away #54's full-game failure, with its much longer histories, branching,
unseen rare hands and omitted high-quantity interactions. No tiny-game outcome
automatically warrants allocating multi-GiB full-game two-bid tables.

## Recorded results

All 24 runs completed all three checkpoints. At 20,000 iterations:

| Fixture | Recall | Exact-deal NashConv | Sampled NashConv range, three seeds |
| --- | --- | ---: | ---: |
| q2 | 1 | 0.008347 | 0.037280–0.053151 |
| q2 | 2 | 0.000329 | 0.032491–0.046538 |
| q2 | Full | 0.000305 | 0.031606–0.046711 |
| q3 | 1 | 0.052406 | 0.076425–0.093786 |
| q3 | 2 | 0.002344 | 0.052910–0.068595 |
| q3 | Full | 0.000501 | 0.052881–0.065144 |

These are full-history evaluations of the restricted fixtures, not full-game
response lower bounds. Seed ranges are observed ranges, not confidence intervals.
Every checkpoint and both-seat BR/EV values remain in the receipt; no run is
selected or omitted. The q3 exact one-bid curve increases from 0.042243 at 1,000
to 0.046212 at 5,000 and 0.052406 at 20,000, showing that more iterations alone
need not improve this imperfect-recall training result.

The sampled full-history controls remain much weaker despite retaining history,
so recall loss alone cannot explain the remaining gap in those runs. Conversely,
the larger exact one-bid residual cannot be blamed solely on chance sampling.
It implicates history merging and/or its learning dynamics; it does not prove
that every one-bid policy must have that gap.

Compute costs are different. Final q2 exact full-history training used 149.17 CPU
seconds versus 38.34–44.39 for sampled full history; q3 used 185.36 versus
52.36–54.25 seconds. At a nearby measured cost in q2, the exact full-history
5,000-iteration point uses 37.08 CPU seconds and has NashConv 0.000902, below all
20,000-iteration sampled full-history results. This is a measured nearby-budget
comparison on this fixture, not an equal-time or full-game speedup claim.

The entire run used **1,154.71 wall / 1,148.53 CPU seconds**, process peak working
set **53,108,736 bytes (50.65 MiB)**, including evaluation and exports. The final
24 policies are retained as full-history tables. LF line endings are pinned for
their exact file-byte hashes on Windows as well as Linux.

## Research decision

Prototype a bounded **variance-reduced chance update** next, for example sampling
own-hand blocks while integrating opponent hands, and validate its expected
increments against these exact fixtures before any full-game pilot. Compare
measured CPU, coverage and full-history responses with the existing sampler.
Keep recall 1/2/full controls: reducing variance will not automatically repair
imperfect-recall learning effects.

Do not jump directly to multi-GiB full-game recall-2 tables or merely multiply the
old iteration budget. Conditional integration/blocking needs its own measured
memory/time case and information-set correctness tests. The short-fixture results
and 56-profile policy class do not diagnose every cause of the original 252-hand
full-game failure. Keep #49 open; no strategy promotion, recommendation feature,
hosted model change or deployment is accepted by this study.
