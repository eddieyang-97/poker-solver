# Development milestones and acceptance boundaries

Track implementation, strategic validation and deployment separately. A completed
local engine may be useful and independently tested while remaining unsuitable
for hosted use. Low NashConv measures convergence for the supplied game; it does
not validate the realism of arrival ranges or action-likelihood assumptions.

## Current delivery status

| Deliverable | Implementation and validation | Range-model quality | Deployment |
| --- | --- | --- | --- |
| No-raise river tools | River milestone accepted; analytical and independent same-tree checks | Caller-supplied assumptions; sensitivity required | Private owner ChatGPT pilot verified; cold starts and OAuth lifecycle gates remain |
| Hand-review Phase 1, PR #12 | Accounting, bounded prose, explicit scenarios and supported river dispatch completed | Declared likelihoods only; unknowns remain gaps | Local workflow; existing hosted interface unchanged |
| Action-model explorer, PR #15 | Merged; final source `1196b9c`, 117 tests and full CI passed; nine profiles verified | Joint conditioning under supplied hypotheses, including folded-player cards; no calibration | Local CLI only; no solver dispatch or marginal substitution |
| River raises, PR #14 and Issue #17 | Local one-raise engine; fractional/exact-cent inputs and opt-in review; existing independent suite plus one exact-tree check | Supplied independent arrival ranges; no forced observed line | No MCP registration or hosted acceptance |
| Turn engine | Local two-street implementation; PR #10 expanded independent coverage and retained resource failures | Supplied ranges; larger games remain less validated | No MCP registration; feasibility is tracked separately in Issue #21 |

Issue #21's [turn delivery feasibility study](turn-feasibility.md) compares full
on-demand output costs with exact-game reuse. It proposes a conservative measured
small-game candidate and defers a production catalog without demand evidence;
neither outcome authorizes a hosted tool or establishes Render capacity.
Owner-merged PR #30 records that feasibility decision. Issue #26 now implements
a separately opted-in [local MCP turn pilot](turn-pilot.md), choosing live-only
and retaining a [separate release gate](turn-pilot-release.md). Stage A merged in
PR #31 at `d0eb869`; that exact river-only baseline is live. The owner authorized
Stage B on 23 October: a separate hosted factory and acceptance harness are
prepared for review, without changing the default entry point or production
settings. Actual hosted turn acceptance remains open.

Evidence: [validation](validation.md), [river closeout](river-milestone.md),
[hand review](hand-review.md), [range exploration](range-explorer.md),
[river raises](river-raises.md), and [turn reference](turn-independent.md).
No deployment, authorization or resource budget changes follow from this table.

## 1. Close the range-explorer milestone and reconcile tracking

PR #15 merged at `ea1db4e13dd46cc1a7e2fc5b26f305498285f45e` after reviewing
the fixes for amount-context and position-alias binding. Its exact tested source
is `1196b9c52663e1aa38b87798ce1b3d88503ba485`; [CI run 39648506799](https://github.com/eddieyang-97/poker-solver/actions/runs/39648506799)
passed all stages and retained nine artifact groups. The downloaded explorer ZIP,
source/raw hashes and all nine profile digests verify against the local evidence.
This source review is not an external audit of the action models or their quality.

[Issue #11](https://github.com/eddieyang-97/poker-solver/issues/11) records Phase 1
and the local explorer as completed, and remains open for later integration.
Preserve the original 200bb three-bet fixture and its existing acceptance evidence.

One compact additional test covers the user-specified synthetic 150bb limp-call
case: £1/£2, exactly £300 stacks and zero rake; three players reach the £33 flop,
one folds after the £15 bet/call, the turn/river start at £63, and a river
check/bet £40/raise **to £120**/call ends at £303. BTN calls another £80;
both river players start with £275 and finish with £155. HJ/CO aliases normalize
to their canonical positions. No hole cards or realistic range model are needed.

The test in `tests/test_history.py` checks accounting and construction of a
supported local raise tree using the reconstructed board/pot/stack. Constructor
canary hands are test plumbing, not inferred opponent ranges. It performs no
training or EV comparison and creates no additional strategic benchmark fixture.
Reuse the existing independent raise suite for numerical correctness.

The fractional API still rejects binary64 `40/63`, rather than rounding it.
Issue #17 adds a separate exact integer-cent mode and the compact accounting
test now also verifies the observed `c/b4000/r8000` branch, while preserving the
old fractional rejection. Its [separate strategic check](raise-review-results.md)
uses explicit range hypotheses and an independently trained matching reference.
Neither the accounting test nor that agreement validates those range assumptions.

## 2. Integrate the local hand reviewer with river raises

Issue #17 implements this local opt-in path; acceptance remains subject to its
PR review/merge. [Contract and commands](hand-review.md#opt-in-local-exact-size-river-raises)
and [measured evidence](raise-review-results.md) describe exact sizing, retained
inputs/results and observed-but-unlocked semantics. No deployment follows.

Construct supported explicit trees from the reconstructed decision point.
Address exact amount representation before claiming support for the £40/£120
line; reject unsupported sizes and trees. Compare a raise to £120 with a proposed
jam only in separate solver scenarios where both actions are legal and admitted.
Keep the compact accounting regression independent of this strategic research.

Retain exact configurations/results, board and chip ledger, remaining effective
stack, sizing semantics, node/action mappings, convergence and reach. Compare
checking, calling, folding and raising only at their appropriate information sets
with a stated common EV baseline. An endogenous check in an equilibrium solve is
not a forced observed check. Keep supplied range and observed-line assumptions
visible, and mark unexecuted/unsupported comparisons explicitly.

## 3. Add joint-range inputs and genuine node locking

Accept explicitly correlated deal distributions without silently replacing them
with independent marginal arrivals. Define forced/locked action semantics and
their effect on training, best responses and diagnostics. Independently test
card removal, range updates, conditional action EVs and deviations after locks,
including off-equilibrium observations and zero-support cases. Distinguish a
counterfactual deviation value from a posterior conditional on an impossible line.

Report whether convergence applies to an unconstrained game or a specified
constrained game. Independently validate that conditioning and deviations produce
the intended game. Calibrating action models against actual populations is a
separate evidence requirement from solver correctness.

## 4. Establish separate hosted acceptance for advanced engines

Only after payload/schema, resource, real timeout, concurrency, authorization and
authenticated ChatGPT acceptance, expose a separate raise-enabled tool. Preserve
the validated no-raise interface. Local 60-second raise-worker measurements do not
change the hosted 20-second budgets or justify an automatic increase.

[PR #10](https://github.com/eddieyang-97/poker-solver/pull/10) has merged at
`cc5c70d`. Preserve its measured maximum-workload timeouts and platform
discrepancies; [Issue #21](https://github.com/eddieyang-97/poker-solver/issues/21)
tracks feasibility under current budgets. Establish turn safety and performance
separately; neither a green resource-study command nor a faster individual run
establishes portable hosted capacity. Keep production and OAuth changes gated by
their actual acceptance evidence and existing user authorization.

## 5. Later flop and multiway research

Start with bounded heads-up flop/turn/river games and independent validation.
Only then scope multiway research. Six-max 150bb multiway solving is a separate
compute and correctness milestone, not an extension implied by earlier-street
accounting, joint range conditioning, or heads-up convergence results.
