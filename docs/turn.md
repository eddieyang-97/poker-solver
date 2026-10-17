# Experimental local turn/river solver

The required private river pilot and initial Issue #1 benchmark milestone were
completed first; [river closeout](river-milestone.md) records the evidence.
This is a new, bounded local implementation. The accepted river core, hosted
MCP tool registrations, Render service and Auth0 configuration are unchanged.

## Model and use

Fixed weighted arrival ranges on a four-card board. Each street permits check,
bet, call and fold, with no raises or rake. Turn decisions precede observation
of the river. Each public river has separate decision strategies; they are
batched for computation, not combined into one information set. River play is
solved jointly with turn play, rather than solving independent rivers first.

Run from the repository root in the existing development environment:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/solve_turn.py examples/turn.json
.venv/Scripts/python scripts/solve_turn.py --all-in-call examples/turn-all-in.json
.venv/Scripts/python scripts/benchmark_turn.py --output .artifacts/turn-benchmark
```

The example ranges are tiny illustrative study hypotheses, not inferred player
ranges or a reconstruction of the earlier £505 river hand. A `river_card` in
the input filters the displayed future node rows only: **it does not condition
the turn solve on knowing the future card**. Omit it to display every legal
river for queried hands; omit queried hands to get summary diagnostics only.

The all-in-call command is deliberately separate. It enumerates exact showdown
equity and incremental call EV against the supplied betting range only when
the effective all-in leaves no further betting decisions. It is not a general
non-all-in turn calling recommendation. In the example, KK has exactly two
winning rivers out of 44 against AA, so call EV is `300 * 2/44 - 100`, about
−86.363636 chips. The caller supplies the assumption that this is terminal.

Python API: `poker_spot.turn.TurnSolver(...).solve(...)` and
`evaluate_turn_all_in_call(...)`. Each solver instance accepts one solve; use a
fresh instance to compare configurations. CLI input errors return structured
`INVALID_INPUT` JSON on stderr and exit 2. Successful calculations exit 0;
a successful solve does not imply that its convergence gap is acceptable.

## Chance, chips and outputs

After four turn cards, there are 48 possible public river cards. For **each
compatible pair of two-card hands**, exactly 44 are legal. The engine sums those
pair-conditioned outcomes with probability 1/44; it does not remove the union
of all cards appearing anywhere in either range. Public-card observations
therefore condition the opponent's range correctly. Zero-weight and blocked
range entries are removed using the existing range syntax and last-token rule.

Turn calls carry the matched contributions forward. If each player contributed
`b` on the turn, the river pot is `P + 2*b` and the remaining stack is `S - b`.
A turn all-in call enumerates the showdown runout without further decisions.
Uncalled bets are refunded. River bets are fractions of that updated river pot.
Sizes cap at the remaining stack; equal capped amounts become one explicit
amount-labelled action. `effective_bets_by_public_history` discloses every
normalized action amount, including such coalescing. No extra all-in sizing
is inserted.

Alternating CFR+ updates use nonnegative regret clipping, linear own-reach
averaging and explicit chance weights. Results include root OOP/IP EVs, raw and
nonnegative NashConv, zero-sum residual and convergence checkpoints. EVs use
half the **initial turn pot** as the centered baseline and include all subsequent
contributions. Queried hands include action frequencies, conditional action EVs
and node reach probability **given that hand**, including both players' actions
and chance. Conditional EVs use every positive opponent reach, with no absolute
arrival-weight cutoff; rescaling a range must not remove supported action EVs.
Impossible-opponent branches return null action EVs; low/zero-reach
strategies should not be treated as precise recommendations.
Action EVs hold later decisions to the average continuation policy after that
one action; they do not optimize all future deviations. A rarely reached
continuation can therefore be poorly converged even when the root NashConv is
small. Best-response diagnostics optimize future decisions separately.

Limits: at most 24 expanded combos per side, 0–2 distinct fractions in `(0,3]`
per street, 20–2000 iterations, positive finite pot/stack up to 1e9, range text
up to 8,000 characters. An empty sizing list is an intentional checkdown street.
These are development bounds, not a hosted resource/security acceptance. The
CLI is synchronous; it is not exposed to untrusted network requests.

## Validation and remaining gates

Tests cover known runout outs and exact all-in indifference; weighted blockers
and chance normalization; two-street pot/stack accounting and fold refunds;
scalar re-evaluation of policy EVs and best responses; an independently computed
singleton-hand backward-minimax value; public-river information separation;
fault injection; invalid inputs and bounds. River display filters cannot change
turn strategies. Existing HTTP authorization/protocol tests continue to verify
that `solve_turn` is not a hosted tool.

The development oracle uses the pinned noambrown exhaustive best-five-of-seven
rank evaluator. Its scalar traversal never reads the product's validity,
showdown or chance matrices. It computes root policy values and best responses
by explicit opponent/runout enumeration. It **does read the product public tree
and average policy**, so separate tests check the tree's chip semantics. This is
not an independently trained external turn engine, an independent tree generator
or a proof of CFR convergence. The singleton-range minimax check has no hidden
private information and is not a general two-range reference solver.

Eight versioned fixtures cover known checkdown outs, turn shoves, two-street
play, multiple sizes, a draw-heavy board, paired/four-flush boards, cross-range
blockers and duplicate capped shoves. The same-policy numeric allowance is
`1e-8` chips for independent arithmetic; it is unrelated to convergence. The
initial convergence gate retains the river study's **0.5% of initial pot**.
Reference/analytical failures must remain visible, not be erased by tuning gates.
CI runs fresh local solves and the oracle, retaining JSON and Markdown reports.

### Recorded validation

The [JSON results](turn-results.json) and [readable table](turn-results.md) retain
actual inputs/outputs at 1,000 iterations, scalar oracle values, convergence
checkpoints, input/source hashes and elapsed time. All eight fixtures passed.
These reports were refreshed after the PR #7 range-weight cutoff fix. Regression
tests also compare equivalent singleton and weighted two-street games after
scaling either or both arrival ranges by `1e-15`, preserving node EVs,
frequencies, reach and genuinely impossible branches.
The largest independently calculated policy/BR difference was approximately
`3.7e-14` chips. The largest final NashConv was £0.03139926 in a £100 pot,
below the declared £0.50 gate. Numeric agreement checks evaluation of a given
policy; it does not validate convergence against a second turn trainer.
The [CLI acceptance record](turn-cli-results.json) separately retains both
actual example command inputs and returned JSON, source hashes and Python version
from its recorded earlier source commit; it is historical CLI acceptance evidence.

The exact singleton-range backward-minimax game on `Js,Ts,2c,3d`, OOP `AsKs`,
IP `QhQd`, P=100, S=150, half-pot sizing on each street has value
`−300/11 = −27.27272727` for OOP. At 1,500 CFR+ iterations the engine computed
−27.27324314 with NashConv £0.00079902, containing the exact value within its
best-response gap. This is a separate exact small-game check, not an external
range-vs-range turn-solver result.

Before hosted turn support: obtain a separately trained matching external turn
reference or stronger independent evidence; review larger-range performance and
hard worker limits; add strict MCP schemas and transport/authorization tests;
perform real authenticated hosted and ChatGPT acceptance. No turn tool,
deployment, plugin publication, paid infrastructure or security relaxation is
included in this local milestone. No preflop, flop, multiway or web UI is added.
