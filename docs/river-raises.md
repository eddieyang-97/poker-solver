# Experimental local river raises: game contract

Issue #13 is a local-only heads-up river milestone. The existing `RiverSolver`,
turn engine, MCP tools, deployment and OAuth remain unchanged. Neither this tree
nor a small convergence gap establishes full-game GTO or validates arrival ranges.

The new opt-in `RaiseRiverSolver` accepts an exact five-card board, weighted
arrival ranges, starting pot, equal **effective remaining** stack, explicit
minimum opening bet, one/two opening bet fractions of the starting pot and
one/two raise fractions. A raise fraction multiplies the **pot after calling**;
that amount is added beyond the call. For pot 100 and opening bet 50, a 0.5
raise fraction adds 100 beyond the call, for a **raise-to 150**. Displayed raises
are total street contributions, not extra chips or multiples of the opening bet.

Both check/bet/check-raise and bet/raise lines are present. Exactly one additional
raise is allowed after the opening bet; its recipient can fold/call only.
Checking remains endogenous. There is no node lock or turn/multiway solving.

All accounting is integer cents. Fractions that produce a non-cent effective
action are rejected. Requested amounts cap at the effective stack; duplicate
actions after capping are rejected. No implicit all-in size is added. An opening
bet must reach the supplied minimum unless it is an actual short all-in. A raise
increment must reach the opening bet unless the raise consumes the effective
stack. A short all-in does not reopen further raising; the one-raise cap also
precludes re-raises after full raises. An all-in opening bet leaves fold/call
only, because no additional chips can be contested.

Terminals retain both gross contributions and uncalled refunds. Called bets and
raises match contributions; fold refunds return the winner's unmatched amount.
Utilities use the existing half-starting-pot baseline: after a fold the winner
receives `pot/2 + loser's contribution`, and a showdown winner receives
`pot/2 + matched contribution`. Ties receive zero. No future rake is deducted.

Initial development bounds: 24 positive board-unblocked combos per side, two
distinct opening sizes, two distinct raise fractions, 20–5,000 iterations and a
60-second disposable CLI-worker wall deadline. These are local bounds to measure,
not claims of hosted capacity. Maximum-dimension measurements must retain actual
runtime, CPU/memory, platform, output size and failures before declaring acceptance.

The pinned MIT noambrown implementation is an independent reference, not a gold
standard. Matching comparisons require `max_raises=2` (opening plus one raise),
`include_all_in=false`, explicit per-player raise fractions and cent-exact action
mapping. It does not enforce the minimum-raise rule itself; incompatible trees
must be rejected rather than adapted. Its integer-chip EV baseline and average
best-response improvement need explicit conversion to chips relative to half-pot
and NashConv. Training runs in an isolated process that cannot import product
modules or consume product policies. Existing sensitivity results and Texas
failures keep their original classification.

Predeclared correctness gates reuse existing scales: same-policy EV/individual
best-response/NashConv agreement within 1e-8 chips, each trained gap at most
0.5% of starting pot, and separately trained values within the sum of their gaps
plus 1e-8 chips. Recommendations are compared through action regret and reach;
equivalent indifferent mixtures need not have identical frequencies. Material
discrepancies are failures to investigate, not reasons to relax these gates.

Implementation, measurements and passing CI are not yet established by this
contract alone. Hosted schema/worker/authentication/live acceptance and turn
raises remain separately gated future work. Educational post-session use only.
