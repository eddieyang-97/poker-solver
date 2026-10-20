# Experimental local river raises

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

## Run a recorded local study

Use the project virtual environment, with `OPENBLAS_NUM_THREADS=1`:

```powershell
.venv/Scripts/python.exe scripts/solve_river_raises.py examples/river-raises.json --output .artifacts/river-raises-example.json
.venv/Scripts/python.exe scripts/benchmark_river_raises.py --performance --output .artifacts/river-raises
.venv/Scripts/python.exe scripts/benchmark.py --sensitivity --output .artifacts/raises-river-regressions
.venv/Scripts/python.exe -m ruff check poker_spot tests scripts benchmarks/raises.py benchmarks/raise_reference_worker.py
.venv/Scripts/python.exe -m compileall -q poker_spot scripts benchmarks
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The scenario requires `context: "post_session"`; this command is for reviewing
past hands. The library class is `poker_spot.raises.RaiseRiverSolver`. Its
constructor takes the eight configuration fields in the example excluding
`context`, `iterations`, `oop_hand` and `ip_hand`; pass the latter three solve
arguments to `.solve()`. Use a fresh instance for each training run. The CLI
executes it in a disposable worker and returns structured `computed`, `not_run`
or `failed` output. A timeout terminates the worker. On Linux that worker also
enforces 60 seconds CPU and 384 MiB **address space**, not resident memory.
Windows measurements have a wall deadline but no CPU/address-space enforcement.
Direct library use has dimension/iteration bounds but no process deadline.

Amounts are chips (the examples can be read as pounds), not big blinds. The
engine accepts expanded rank-class ranges within its combo bound; the independent
comparison adapter deliberately accepts explicit concrete combos only. Requests
are limited to 65,536 characters, ranges to 8,000 characters each; pot, stack and
minimum bet must be positive, cent-exact and at most 1,000,000 chips.

Node histories use cents: `c/b5000` is OOP checking then IP betting 50;
`b5000/r10000` is OOP betting 50 then IP adding 100 beyond a 50 call, to 150.
The output includes exact gross/settled/refund ledgers and action metadata.
Conditional action EVs and frequencies are displayed to four decimals, NashConv
chips to four and percent-of-pot to three; benchmark gates use unrounded values.
`own_reach_probability` conditions only on that player's prior strategy. The
separate `joint_reach_probability` includes both ranges, blockers and both
players' actions. An off-path mixture may be arbitrary; `null` EV means zero
compatible opponent reach, not a zero-valued action.

## Measured validation — 21 October 2026

[Versioned numerical results](river-raises-results.json) retain all eight exact
requests, reference checkpoints/profile digests, LF-normalized source hashes,
individual best-response EVs and discrepancies. The [readable table](river-raises-results.md)
separates this corpus from the existing no-raise score. Full ordered product and
reference policies remain in `.artifacts/river-raises.profiles.json`; the report
records its byte SHA-256. CI retains fresh reports/profiles in the separate
`river-raise-validation` artifact. Timing fields are measurements, so the full
export hash need not be identical on a new run; canonical player-profile hashes
exclude runtime metadata. This local evidence alone does not establish CI.

All **106 tests**, Ruff and compileall passed. The eight independently trained
games and 48 seeded fully mixed policy checks passed the unchanged gates.
Fixtures cover polarization, symmetric value/air, weighted blockers, two sizes,
paired and flush boards, short all-in raises and all-in opening bets. The largest
trained NashConv was 0.016081 chips in a 100-chip pot. The polarized half-pot
fixture has analytical OOP EV **−100/6**: raising KK loses to value and folds
bluffs, so a check-raise adds no value to calling. Product/reference EVs were
−16.66674454/−16.66668682. Exhaustive per-hand pure best responses and a separately
carried scalar chip ledger also pass, as do injected payoff/tree/policy faults.
The original ten no-raise river cases and sensitivity still pass.

The actual example uses weighted four-combo ranges with blockers, not a revealed
opponent singleton. For OOP AsAd after checking and facing 50, the computed
raise-to-150 frequency is 1.0, call EV 100 and raise EV 121.492. Own check reach
is 0.1261; the complete node has joint reach about 0.18184. Separately, queried
IP KsKh bets 39.94% after a check and calls the check-raise 35.38%, with call EV
−100.0733 versus fold −100. These near-indifferent mixtures are finite-training
outputs for these assumptions, not precise GTO or live population frequencies.
The independent profile's queried action regrets and joint hand/node reaches
are retained alongside the product's; mixtures need not agree at indifference.

There is a small, explicitly investigated numerical discrepancy. For the
reference-trained weighted-blocker policy, OOP AsAd calling at `b5000/r10000`
has EV 200 exactly by the terminal formula. The reference evaluator gives
200.0000000087562, a difference **8.7562e-9**, below but close to the unchanged
1e-8 gate. Its total-minus-blocked compatible mass is
2.3472582283412535e-7, versus explicit compatible enumeration
2.3472582284234655e-7. Substituting these into
`(25000 * explicit_mass - 5000 * reference_mass) / 100 / reference_mass`
reproduces the discrepancy exactly. This identifies floating-point cancellation
in the reference's blocked-mass subtraction for this row. No reference source,
product payoff, fixture or tolerance was altered to make it pass. Smaller reach
or another platform may expose a larger error and must be investigated.

Two maximum-dimension Windows samples used 24 combos per side, two opening/two
raise sizes, 5,000 iterations, 14 public nodes and both hand queries. They took
3.822/3.705 seconds including process startup, 3.438/3.344 seconds CPU and
27.00/26.61 MiB peak resident memory, returning 13,495/13,477 result bytes.
These measured samples support a bounded local pilot under a deliberately
separate 60-second deadline. They are neither a universal worst-case guarantee
nor acceptance under the hosted 20-second budget; Linux measurements and actual
applied limits belong in CI evidence.

Hosted schema/worker/authentication/live acceptance and turn raises remain
separately gated future work. The engines share the rank evaluator and CFR+
algorithm family, so agreement is not proof of all poker semantics. No external
raise-capable TexasSolver acceptance is claimed. Educational post-session use only.
