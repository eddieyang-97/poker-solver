# Independently trained strategic turn games

This local development milestone adds a separately implemented turn/river game
and CFR+ trainer. Unlike the earlier scalar oracle, it constructs its own tree,
chip ledger, chance transitions and information sets. Unlike river decomposition,
all ten differential fixtures permit strategic turn betting. It is new code in
this repository, not an externally audited turn solver or a proven gold standard.
Product solver code, hosted tools, deployment and OAuth configuration are unchanged.

## Reproduction and provenance

From the project development virtual environment:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark_turn_independent.py --output .artifacts/turn-independent
.venv/Scripts/python -m unittest discover -s tests -p test_turn_independent.py -v
```

Defaults are 2,000 product and 4,000 reference iterations. Reference development
bounds are four explicit combos per player, two sizes per street, 200,000
concrete nodes and 10,000 iterations; its isolated subprocess has a 120-second
deadline. These are trusted development limits, not hosted admission controls.

`benchmarks/turn_reference.py` and `turn_reference_worker.py` do not import
`poker_spot`. The child receives only the explicit fixture configuration and
iteration count; it never receives the product tree, regrets or policy. The
parent adapter cross-evaluates policies only after separate training. The worker
records its PID, loaded product modules (required to be empty), runtime, source
hashes, tree dimensions, checkpoints and full profile. The parent verifies the
exact configuration, source-file set and hashes.

Only the exhaustive hand-rank evaluator is reused from the MIT-licensed,
hash-verified noambrown reference pinned to
`6a10442877ffc8fd28af93e16e279b9bbdd97b2a`. Its river trainer is not used as a
turn trainer. Vendored sources and license remain unchanged. Nothing under
`benchmarks/` is a hosted dependency.

## Independent model and comparisons

The root samples compatible private deals with probability `w0*w1/Z`. Each
deal has exactly 44 legal rivers with conditional probability `1/44`, including
after an all-in. Information sets contain the actor's hand and complete public
history; they exclude the opponent's hand and unrevealed river. Concrete copies
are pooled before CFR+ regret clipping and before best-response maximization.
Average strategies use linear iteration weighting, chance and own strategic
reach, excluding the opponent's strategic reach. Best responses include chance
and opponent reach and make one legal choice for the entire information set.

An immutable state machine accounts for both streets' contributions. Terminal
OOP utility is collected chips minus own contributions minus half the initial
pot. IP utility is its negative. Called bets increase the next street's pot and
reduce remaining stacks; uncalled bets refund algebraically. Bet amounts must
be exact integer cents at every future history. Sub-cent inputs or future bets,
raises, rake and an implicit extra all-in are rejected. Sizes cap at the stack;
identical capped amounts coalesce explicitly in both trees. The adapter verifies
exact action amounts, actors, streets, hand weights and all supported private
hand/public-card contexts. It rejects incompatible trees without rounding or
substituting inputs. Profile hand, row and action order are mapped explicitly.

Each fixture checks:

- Product policy evaluated in the independent tree; independently trained
  reference policy evaluated in both trees; child/parent evaluation consistency.
  Same-policy EV, each individual best-response bound and raw NashConv must
  agree within `1e-8` chips.
- Each engine's raw NashConv (sum of both best-response gains) at most 0.5% of
  initial pot. It is not divided by two or by the number of deals/runouts.
- Separately trained root values within the sum of their convergence gaps plus
  numerical allowance; both cross-play directions inside the appropriate
  policies' best-response security bounds.
- For analytical games, the exact value inside both best-response intervals,
  with value error bounded by the measured gap. Selected analytical frequencies
  use the existing river benchmark's absolute `0.04` allowance; no general
  frequency agreement is required for nonunique or low-reach strategies.

Fault tests corrupt only the product evaluator and require discrepancy detection.
Further tests cover hand/action permutations, missing/duplicate profile rows,
tree substitution, hidden-hand best-response peeking, exact outs, all-in chance,
pot carry/refunds, invalid inputs and future rounding rejection.

## Analytical checks and measured results

The singleton game `Js Ts 2c 3d`, `AsKs` versus `QhQd`, P=100, S=150,
half-pot sizing each street has 16 winning and 28 losing rivers. Backward
minimax on the independently constructed tree gives `-300/11` OOP value.

The hidden-hand terminal-turn game uses `2c 3d 4h 8s`, OOP `KhKd`, IP equally
weighted `AsAd` and `QhJd`, P=S=100, pot-sized turn bets and no river bets.
KK wins 2/44 against AA and always against QJ. After OOP checks, AA always
shoves, QJ shoves `19/44`, and KK calls `1/2`. QJ's shove indifference gives
the half-frequency call; KK's call indifference gives
`(1 - 3*(2/44))/2 = 19/44`. Against an OOP lead, AA calls and QJ folds.
The exact profile has value `-475/22` and independently evaluated NashConv zero.
Thus this checks hidden-hand mixing as well as singleton perfect-information
play. It does not establish general two-range uniqueness.

The original six cases below were established in PR #9. The
[expanded coverage and resource study](turn-resource-study.md) adds four games
with three or four combos per player, and 60 seeded random-policy evaluations.
The current [recorded outputs](turn-independent-results.json) and
[readable table](turn-independent-results.md) contain actual local solves on
Python 3.14.8 / NumPy 2.5.4. All ten cases pass. The original six are singleton
minimax, weighted dry board, draw board with two sizes, weighted cross-range
collision, paired board with stack caps, and terminal turn shoves. Those six
have at most two combos per side. The paired fixture permits two turn sizes and is a different tree
from the earlier one-size `paired_short_stack` fixture.

Maximum same-policy discrepancy is `6.90e-14` chips. Maximum independently
trained value difference across the expanded corpus is £0.00251755. Largest
final NashConv is £0.02218518 in a £100 pot, below the unchanged £0.50 gate.
In the mixed analytical game,
product/reference QJ shove frequencies are 0.43160770 / 0.43163558 and KK call
frequencies 0.49979573 / 0.50015499; these are computed approximations to
19/44 and 1/2, not invented equilibrium outputs.

The summary versions all inputs, checkpoints, full turn policies and canonical
reference-profile SHA-256 digests. Full product/reference profiles remain in
ignored local artifacts and the `turn-independent-reference` CI artifact.
The recorded local raw file is `.artifacts/turn-expanded-final.profiles.json`,
SHA-256 `4ec216d2ac63ec3cd1105149a1ee329890091a5f504dad81b9a1690193973104`.
Source hashes, raw byte hash and all ten profile digests were checked against
the current files. Fresh CI output has its own runtime, timings and raw hash.

## Limits and remaining gates

This independently constructs and trains small same-tree strategic turn games.
It strengthens the earlier product-tree scalar oracle and turn-disabled
decomposition. It remains an in-repository implementation of the same CFR+
algorithm and shares the pinned exhaustive ranker with other development
references. Shared assumptions or mistakes remain possible; it is not formal
verification, an external audited turn comparison, full-range acceptance or
evidence that the restricted tree matches richer poker strategy.

The PR #9 local suite had 67 passing tests. Existing checks also passed:
eight turn policy fixtures, ten river fixtures plus raise sensitivity, and four
decomposition cases with 188 independently trained river games. No numerical
gate was relaxed. Prior measured maximum-dimension Ubuntu workloads exceed
22 seconds and the hosted 20-second budget. This milestone neither optimizes
nor accepts hosted resources. Transport schemas, bounded worker integration,
authentication tests and real hosted/ChatGPT turn acceptance remain future work.
