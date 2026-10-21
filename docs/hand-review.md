# Post-session hand reconstruction and river review

This implements Phase 1 of [Issue #11](https://github.com/eddieyang-97/poker-solver/issues/11)
as a local, deterministic workflow. It accepts a structured hand or explicit
position/action prose, reconstructs the chip ledger, applies caller-supplied
range hypotheses and optionally runs the existing bounded river tools. It does
not solve the earlier multiway streets. The hosted service, OAuth configuration,
plugin package and deployed solver are unchanged.

## Reproduce a review

Use the project virtual environment and set `OPENBLAS_NUM_THREADS=1`. In PowerShell:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python.exe scripts/review_hand.py examples/hand-review.txt
.venv/Scripts/python.exe scripts/review_hand.py examples/hand-review.json --scenarios examples/hand-review-scenarios.json
.venv/Scripts/python.exe scripts/review_hand.py examples/hand-review.txt --scenarios examples/hand-review-scenarios.json --run --output .artifacts/hand-review
```

The first command reconstructs only. The second prepares exact tool requests
with `status: not_run`. Only `--run` executes calculations. The final command
writes full `.json` evidence and readable `.md` notes. Without `--output`, JSON
goes to stdout; `--markdown` selects readable stdout. Exit codes are 0 for a
successful reconstruction, plan or completed execution; 1 for failed/partial
execution; 2 for invalid or ambiguous input. A plan's zero exit code does not
mean a solver ran. Never use this workflow during an active real-money hand.

Correct an existing field without rewriting the history:

```powershell
.venv/Scripts/python.exe scripts/review_hand.py examples/hand-review.json --set /players/0/stack=500
.venv/Scripts/python.exe scripts/review_hand.py examples/hand-review.json --set /streets/0/actions/2/to=20
```

The second correction intentionally fails until the later calls are corrected
too. Corrections use existing JSON-pointer paths, preserve the original object
and rerun validation; they never silently repair inconsistent amounts.

## Explicit history input

[hand-review.json](../examples/hand-review.json) is the complete schema example.
Required top-level fields are `context: post_session`, currency, blinds, all
seated players, forced posts, additional unassigned `dead_money`, rake and one
to four consecutive streets beginning preflop. Unknown fields are rejected.

- Positions are UTG, UTG+1/HJ, UTG+2/CO, BTN, SB and BB. Include folded seats
  and their starting stacks. Optional physical seat numbers must cover every
  player, be unique integers 1–10 and agree with clockwise position order.
- Stacks are starting amounts before posts. Blinds, antes and assigned dead
  posts reduce the posting player's stack. Unassigned dead money increases the
  pot without consuming a listed player's stack. Both blind posts are explicit.
- Actions are ordered objects with `player` and `action`. Raises require `to`
  (total contributed on that street); bets require incremental `amount`. Calls
  accept incremental `amount`, total `to`, or the unambiguous computed amount
  owed. Supplying both is rejected. `all_in`, when supplied, must match chips
  actually remaining. Amounts are exact nonnegative pennies, not rounded guesses.
- Cards accept ASCII or Unicode suits and `10`/`T`. Cards must be unique across
  the board and known hands. Own cards use `knowledge: hero`; later reveals use
  `knowledge: showdown`. These facts never generate an opponent range.
- Postflop order follows positions; a table seated with only two players has
  BB act first postflop. An earlier multiway pot preserves all participants
  until they fold. Short raises track reopening rights, calls respect remaining
  stacks, uncalled chips are refunded and all-in runouts prohibit empty-side-pot
  betting. Gross side-pot contribution layers are reported without awarding
  pots; they exclude unassigned dead money and precede rake deductions.
  A short all-in blind uses its actual contestable wager once only one stack
  can still act; the nominal big blind remains the bring-in while two stacks
  can contest further chips. A player who already covers all all-ins has no
  phantom call or empty-side-pot betting option.
- Rake is mandatory: `{"model":"none"}`, a fixed `amount` at a named postflop
  `street`, or a percentage `rate`, `cap`, `street`, `rounding: floor_cent`.
  These are explicit **one-time deductions at the start of that street**, not a
  general casino rake schedule. Further future rake is not modeled by river CFR.
  Unsupported/missing rake is not silently assumed away.

Each street reports start/end pot, players, stack balances, contributions,
pending actor and heads-up effective stack/SPR. Multiway SPR is left undefined.
No required-equity scalar is invented for a multiway decision. An effective
all-in call removes the opponent's uncallable excess from the contested pot.

[hand-review.txt](../examples/hand-review.txt) demonstrates the bounded prose
grammar: labelled context/currency/blinds/stacks/players/known cards/rake/dead
money, followed by street lines of semicolon-separated position/action phrases.
For example, `UTG+2 3-bets to £18`, then `UTG calls £12`. Uniform `Stacks: 200bb
each` explicitly means £400 each at £2 BB. The prose shortcut creates the two
normal blind posts; use JSON for antes, asymmetric stacks, other posts or rake.
An effective-stack amount alone does not establish all starting stacks and is
returned for clarification rather than silently assigned to every seat.
It is not a general natural-language model. Unrecognized lines/actions, repeated
metadata and missing details are retained as clarification issues, and no tool
is dispatched. Unlabelled narratives/pronouns should first be converted into
this explicit representation with material assumptions confirmed by the user.

## Range hypotheses and provenance

[hand-review-scenarios.json](../examples/hand-review-scenarios.json) supplies three
editable hypotheses: baseline, tighter live and looser/aggressive. These sparse
concrete-combo ranges are illustrative sensitivity cases, not measured live
frequencies, full preflop ranges or a solved theoretical prior. Preflop position,
the small three-way 3-bet and flop/turn actions motivate discussing possible
ranges; they do not uniquely determine any of these weights. All earlier action
likelihoods are explicitly unknown in this example.

An arrival hypothesis has `range`, textual `provenance` and optional `updates`.
An update contains an `event`, `provenance` and either `likelihoods: null` (record
a gap, make no update) or a complete concrete-combo map of probabilities in
[0,1]. For supplied probabilities:

```text
relative posterior(h) = prior(h) × supplied P(observed action | h, history)
```

For example, weights 1 and 0.5 with likelihoods 0.25 and 0.5 both become 0.25.
The adapter retains unnormalized products as `posterior_weights_decimal` strings
and divides each surviving product by the largest before dispatch. `weights`
and the tool's range string contain those normalized relative weights (1 and 1
in this example). Decimal products preserve very small uniform likelihoods;
common scaling must not erase conditional action EVs. Missing likelihoods,
invalid probabilities and relative weights too small for the solver's floating
representation are rejected without silently dropping a positive combo. No action model is
manufactured from prose. Board blockers are removed explicitly; call evaluation
also removes the caller's own cards. Opponent showdown cards do not remove
alternative hands from the range or determine ex-ante weights. Changing a
revealed hand changes only its displayed own-hand query, provided that hand
exists in the declared arrival range.

The report separates supplied facts, computed accounting, supplied range/
population assumptions and actual numerical executions. Every calculation
retains exact validated arguments, complete output, elapsed time, runtime and
LF-normalized source hashes. Request/result SHA-256 hashes detect accidental
edits; they are **integrity checks, not signed proof that an arbitrary uploaded
report executed**. `run_review` always constructs and executes fresh requests;
it cannot ingest user-supplied results or a `verified` flag. Plans, failures and
unsupported decisions never receive the computed label. Full raw reports stay
in local/CI artifacts; [versioned evidence](hand-review-results.json) retains
concise measurements and request/result/source digests.

## Solver boundary and interpretation

The initial adapter dispatches only actual pending heads-up river decisions
whose river began heads-up. Its equilibrium query supports the observed
check/bet line, using the river-start pot, remaining effective stack, exact board
and observed bet fraction. It rejects unsupported sizing rather than rounding
or substituting another tree. Calling EV additionally requires the caller's
known hand and a **separate supplied betting range** for the actual bettor.
Other streets and unsupported lines retain an explicit not-run reason. No
local turn solver or new MCP registration is involved.

`solve_river` is a river-start, no-raise equilibrium approximation. It solves
OOP's check frequency endogenously: an observed check is **not locked**. Inspect
OOP's `oop_facing_ip_bet_*` and IP's `ip_after_oop_check`; own strategic reach is
not the probability of the observed history. EVs use the half-starting-pot
baseline and the existing four-decimal rounding. `null` EV means no opponent
reach, not zero EV. NashConv assesses this supplied restricted game only.

`evaluate_river_call` instead computes incremental call-minus-fold EV versus
the supplied betting range. It does not optimize raises or solve equilibrium.
Its result can favor calling even when the separately solved equilibrium
profile folds: those are different opponent-range assumptions. The displayed
88 betting decision is likewise against an OOP distribution, never just 73.
A revealed 88 beats 73 on this board; calling 73 requires sufficient other
weaker hands in the hypothesized betting range.

Execution uses the existing `Runner` and disposable river worker, with existing
input/resource/time bounds. Sequential local runs do not establish hosted OAuth
or ChatGPT acceptance. Separately, after the owner reconnected the existing
ChatGPT connection, all six prepared requests succeeded through the authenticated
**Poker Solver Hosted** connector and matched local results exactly. See the
[measured validation](validation.md) and versioned hosted receipts. The CLI does
not call that connector, and no hosted history endpoint or new plugin release is
claimed. No credentials or auth settings were changed; automatic refresh,
revocation and second-account testing remain separate operational gates.

## Scope left open

The first local Phase 2 follow-up is the separate [action-model range explorer](range-explorer.md):
editable supplied frequencies, validated history bindings, joint card removal
and sensitivity across participants. It never silently turns correlated posterior
marginals into independent solver arrival ranges. The Phase 1 adapter above stays
unchanged. Calibrated models, automatic integration, true node locking and
separately gated future turn transport remain open in Issue #11. This
workflow provides no verified preflop/flop or multiway strategy, no population
calibration, no new external solver comparison, and no new hosted feature.
