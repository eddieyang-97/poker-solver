# Audit and validation — 16 October 2026

## Exact-size local river-raise hand review — 22 October 2026

Issue #17 adds a backward-compatible exact integer-cent path and opt-in
`--local-raises` hand review through the existing disposable worker. The compact
150bb case reconstructs £33/£63/£63/£303, a £275 river-start effective stack,
and BTN's extra £80 after a raise to £120. Its public prefix maps to an exact
`c/b4000/r8000` node. A separate explicitly requested jam-to-£275 branch is
present; it is not added implicitly. The old fractional rejection of binary64
40/63 remains; exact mode bypasses the representation problem without rounding.

[Contract](hand-review.md#opt-in-local-exact-size-river-raises),
[measurements](raise-review-results.md) and [requests/receipts](raise-review-results.json)
record actual local execution and an independently trained same-tree reference,
using rational 40/63, 80/143 and 235/143 sizing. At 2,000/4,000 iterations,
product/reference root EVs are -9.26970804/-9.26968372 chips; gaps are
0.00723474/0.00387502, below the unchanged 0.315-chip gate. Largest same-policy
discrepancy is 1.7053e-13 chips against the unchanged 1e-8 gate. These are outputs
under the separate illustrative range file, not inferred population frequencies
or an externally audited GTO solution. Checks and bets remain endogenous, not locked.

Local checks: **132 tests run, 131 passed, one Linux-only check skipped on
Windows**, Ruff and compileall; existing **8/8 raise cases / 48 mixed policies**,
two maximum worker samples and **10/10 no-raise cases plus sensitivity** passed.
All eight legacy 2,000-iteration outputs match pre-change canonical JSON bytes on
this machine. The known 8.7562e-9-chip raise discrepancy is retained. Historical
evidence below is preserved; source receipts identify each measured version.
New final-head CI is pending at this snapshot; it is not substituted by older CI.

Plans/unsupported inputs remain `not_run`; worker failures/timeouts never receive
a computed label. Verified computations retain exact configurations, accepted
tree, node/own reach, action EV baseline, metrics and source/request/result hashes.
Correlated arrivals (#18), locks (#19), hosted raises (#20) and turn feasibility
(#21) remain separate. Existing no-raise solver/dispatch/MCP/security/deployment
are unchanged, and no hosted call or configuration change occurred.

## Local supplied-action range exploration — 21 October 2026

The next Issue #11 follow-up adds a separate local action-frequency/range
explorer, not a strategic solver or hosted endpoint. [Contract and commands](range-explorer.md),
[measured results](range-explorer-results.md) and [decimal outputs/source/profile hashes](range-explorer-results.json)
retain the admitted scope: two/three modeled participants, chronological board
filtering, history-bound legal alternatives, complete supplied frequency rows,
unknown-likelihood gaps and latent cards of modeled folded players. Future
actions/cards and all hole-card claims are excluded from inference. Posterior
marginals are not silently substituted into the independent-range solver.

Actual local checks pass: **117 tests**, Ruff/compileall, **20 randomized exact
Fraction cross-checks**, three-profile analytical sensitivity and two maximum
worker samples (24³ candidate deals, three profiles, 24 models/profile), plus
the existing **10/10 river cases and sensitivity**. Actual timeout termination,
tiny scales, private decimal contexts, support-underflow rejection, impossible
lines, input bounds, model edits and error evidence are covered. The local CLI
enforces a 60-second parent deadline; CPU/RSS bounds and universal runtime are
not claimed. CI retains a separate `range-explorer-validation` artifact; this
local snapshot establishes no real hosted acceptance.

PR #15 review reproduced two P2 failures: ambient Decimal precision 2 made
£6.01 and £6.02 action fingerprints collide, and a supported `HJ` action alias
failed lookup against canonical priors. Every explorer history replay now uses
the private Decimal context. Seats, posts, actions, prior keys and target pairs
normalize supported aliases before binding/inference/reporting, rejecting duplicate
canonical priors. Added tests preserve the caller's precision, reject distinct
penny/subpenny alternatives at precisions 2/6/28, and compare full canonical/alias
reports. All nine existing benchmark profile digests remain unchanged; no numerical
gate changed. Fresh source/raw hashes and timings are retained in the results JSON.

Final reviewed source `1196b9c` passed [CI run 39648506799](https://github.com/eddieyang-97/poker-solver/actions/runs/39648506799):
117 tests, all benchmark/replay stages and nine nonempty artifact uploads. The
downloaded explorer ZIP, three raw reports, five worker sources, four reproduction
sources and nine profile digests verify; the exact receipt is versioned in
`range-explorer-results.json`. PR #15 merged at `ea1db4e`. Issue #11 now marks
completed Phase 1 and local explorer work separately from remaining solver and
hosting gates; [the development roadmap](development-roadmap.md) records the sequence.

A separate compact synthetic 150bb limp-call/check-raise regression preserves
the original 200bb example. It checks £33/£63/£63/£303 pots, canonical actor order,
£275 river-start stacks, £155 final stacks and an £80 call after a raise to £120.
It constructs a permitted local raise tree with the reconstructed board/pot/stack,
without training or adding range-quality/EV claims. The current exact-sizing rule
rejects binary64 `40/63`; the regression preserves that rejection and does not
claim observed-line solver integration. The independent raise suite remains the
numerical correctness gate; this accounting case does not enlarge its corpus.
Fresh local follow-up checks passed **118 tests**, Ruff and compileall, plus the
unchanged independent raise suite (**8/8 cases, 48 mixed-policy comparisons**).
Both existing maximum-dimension workers completed (4.933/4.913 seconds parent
wall, 28,123,136/28,225,536 bytes peak resident memory on Windows/Python 3.14.8).
These are measured repeats, not universal limits or hosted acceptance. The
documented 8.7562e-9-chip action-EV discrepancy remains below the unchanged 1e-8
gate with little margin; the compact accounting test adds no numerical evidence
about realistic arrival ranges. New follow-up CI is separate from PR #15's
verified 117-test source-head run.

The first CI attempt at `938344b` failed in the new CLI test because it assumed
the ignored `.artifacts/` directory already existed. The test now creates its
own independent temporary directory. That attempt reached no benchmark stages
and retained no artifacts; its subsequent missing-upload errors are not evidence
of completed calculations. No product arithmetic or numerical gate changed.

Computed range probabilities depend on uncalibrated supplied priors/frequencies;
no action EV, equilibrium frequency or new solver call is produced. Existing
hand-review dispatch, all solver engines, hosted registrations, deployment,
OAuth and plugin settings are unchanged. True node locking, calibrated models,
automatic solver integration and future turn transport remain separate work.

## Experimental local river raises — 21 October 2026

Issue #13 now has a separate opt-in `RaiseRiverSolver` and disposable local CLI,
supporting check/bet/check-raise and lead/raise with at most one additional raise.
The [game contract and commands](river-raises.md), [measured table](river-raises-results.md)
and [exact requests, profile/source hashes and discrepancies](river-raises-results.json)
document the admitted cent-exact tree, minimums, short all-ins and refunds.
Existing no-raise core behavior, turn solver, hosted registrations, deployment,
OAuth and plugin settings are unchanged. Nothing was deployed.

Local Ruff/compileall and **106 tests** pass. Actual isolated training of pinned
MIT noambrown commit `6a10442877ffc8fd28af93e16e279b9bbdd97b2a` passes **8/8**
raise fixtures, with bidirectional policies, individual best responses, conditional
action EVs, reach and explicit baseline/NashConv conversions. Another **48**
fully mixed policies pass. Both **24×24-combo**, two-bet/two-raise, 5,000-iteration
workloads complete under the separate local 60-second deadline, with actual
CPU/peak RSS/output size retained. The existing **10/10 river regressions and
sensitivity** still pass. These are new local calculations, not hosted acceptance.

The largest conditional-Q difference is **8.7562e-9 chips**, near the unchanged
1e-8 gate. The guide identifies its exact weighted-blocker row and reproduces it
from the reference's total-minus-blocked mass cancellation. No gate, historical
Texas failure or reference source was changed. Rare-branch precision remains
visible; it is not hidden by rounding displayed EVs. The reference is independent
training, not a proven gold standard. Both trainers use CFR+; the adapter reuses
existing reference evaluation helpers, while the two rankers are separate.
The raise benchmark step at `1c4e244` also passes on Ubuntu/Python 3.12.15;
its `river-raise-validation` ZIP digest, ten source hashes, raw-profile hash
and all eight reference-profile digests were verified. The guide/JSON retain
the receipt and actual Linux CPU/RSS/limit measurements. A passing benchmark
step does not establish completion of final-head CI or universal runtime bounds.

## PR #12 review corrections — 20 October 2026

Both P2 findings at `71bc313` were reproduced before fixes. The accounting adapter
now uses the actual contestable wager when fewer than two players have chips
left, including after a fold. With £1/£2 blinds, SB £100 and BB £1 all-in, the
pot is £2, no call or equity threshold is invented, and the entire forced runout
is accepted. Two stacks still able to bet preserve the nominal £2 bring-in and
£2 minimum raise increment. Regressions cover unequal short blinds, both blinds
all-in, antes, refunds and prohibition of betting into an empty side pot.

Range conditioning now retains decimal posterior products and max-normalizes
dispatch weights, avoiding the river core's absolute reach threshold for a
globally scaled range. Two uniform `1e-8` updates on both baseline arrivals give
exactly identical validated requests and complete results to the unconditioned
100-iteration calculation; root check EV remains **−£43.0281**, not `null`.
Three uniform `1e-200` updates preserve support as well. A genuinely unrepresentable
relative weight is rejected rather than silently removed; explicit zero
likelihoods still remove combos. [Measured reproductions](hand-review-fixes.json)
retain inputs, output rows and source hashes.

All **95 tests**, Ruff and compileall pass locally, and the unchanged river
benchmark passes **10/10 plus sensitivity**. Fresh six-query local/hosted evidence
below has been regenerated: all six numerical results remain identical to the
pre-review outputs; two arrival request strings change by common normalization.
The first hosted retry timed out without a payload, then all six calls completed
sequentially and exactly matched the updated local requests/results. The solver
core, turn engine, transports, deployment and auth configuration remain unchanged.
The prior 91-test CI at `71bc313` is historical; review-fix CI must pass separately.

## Post-session hand-review Phase 1 — 20 October 2026

Added a local history normalizer/accountant, transparent range scenarios and
bounded orchestration of the existing river tools for [Issue #11](https://github.com/eddieyang-97/poker-solver/issues/11).
The [workflow guide](hand-review.md) documents schema, bounded prose grammar,
corrections, rake models, known action-likelihood conditioning and explicit
not-run states. Earlier multiway streets are accounted for, never solved.
No solver-core, hosted transport, production configuration, Auth0 or plugin
changes are part of this work; turn transport remains outside scope.

The £1/£2, £400-per-seat no-rake regression reconstructs £57 on the flop, £87 on
the turn/river, £367 remaining effective stack, then £40 to call into £127 and
required equity **40/167 = 23.9520958%**. It preserves the three-player flop until
UTG+1 folds and the £3 contributed by folded blinds.

All **95 tests**, Ruff and compileall pass locally using the project venv
(Windows, Python 3.14.8). The independent river benchmark passes **10/10** with
tree sensitivity completed, using unchanged gates. New tests cover blinds,
antes, dead money, seat/action order, short all-ins, reopening rights, refunds,
effective calls, rake, ambiguity, revisions, blockers, supplied Bayesian weights,
reveal independence, actual bounded execution, CLI output and false/failed
computation labels. These local tests do not establish a final-head CI result.

Actual local execution of the documented CLI ran three 700-iteration
`solve_river` queries and three exact `evaluate_river_call` queries. Full validated
arguments/results, runtime, source hashes and integrity receipts are retained in
local `.artifacts/hand-review-fixed.json`; [versioned evidence](hand-review-results.json)
records the six requests/results and raw-report SHA-256
`5dfa06728dfd40b9b2c46376ccb5a56509571de0c9f14d4cf4a3040cbb1a1f14`.
CI generates fresh full JSON/Markdown as `post-session-hand-review` artifacts.

| Supplied hypothesis | 73 equity vs betting range | Call-minus-fold EV | Call/fold comparison | River CFR NashConv |
| --- | ---: | ---: | --- | ---: |
| Baseline | 13.9130% | −£16.7652 | Fold | £0.0015 |
| Tighter live | 1.0000% | −£38.3300 | Fold | £0.0008 |
| Looser/aggressive | 44.6927% | +£34.6369 | Call | £0.0010 |

The CFR queries also evaluate 88's checking/betting against a full supplied OOP
distribution, not just revealed 73. For baseline/tighter/looser OOP arrivals,
88's check EV is −£41.1644/−£43.0561/−£17.6715 and bet EV is
−£12.4572/−£21.8740/+£10.1781, using the half-starting-pot baseline. These sparse
illustrative games prefer betting; their computed mixtures are not precise
population or full-game GTO frequencies. OOP checks endogenously, not under a
node lock. The separate looser betting hypothesis can favor a 73 call while the
equilibrium profile folds: the two queries use different opponent assumptions.
Earlier-action likelihoods are unknown, explicitly logged, and never fabricated.
The earlier conversation's street-by-street commentary remains unverified.

**Actual hosted acceptance:** three initial attempts through the existing
connector returned authentication-prompt acceptance without numerical output.
After the owner reported verification from ChatGPT, all six calculations above
succeeded sequentially through the authenticated **Poker Solver Hosted**
connector. Every request object and every result field exactly equals the local
execution (JSON equality, no tolerance). The versioned evidence retains request/
result receipts and the hosted raw-report SHA-256
`5c2798ac8ea887b9b4a877cc16bbbfabbe3ea37f64e42389a84a6fd274cf1ae1`;
the full hosted capture is local `.artifacts/hand-review-fixed-hosted.json`. The CLI
itself remains local; no hosted hand-history endpoint or plugin update is
claimed. This reconnect/manual invocation does not establish automatic refresh,
revocation or second-account acceptance. No auth checks were relaxed. Phase 2
range exploration, true node locking and future turn/flop/multiway support
remain open; Issue #11 must not be auto-closed.

## Expanded turn coverage and development resource study — 18 October 2026

Following merged PR #9 (`dd9249297300bc859101859e324de5d9de554599`), expanded
the independent strategic-turn corpus from six to ten cases. New games use
three/four concrete combos per side, weighted collisions, four-flush and trips
boards, and draw-heavy two-size trees. Bidirectional evaluation additionally
checks each player's individual best-response bound; 60 seeded fully mixed
policies test those bounds without relying on convergence. Neither trainer,
product solver behavior nor existing numerical/convergence gates changed.

All ten trained cases pass. Maximum same-policy EV/individual-BR/NashConv
discrepancy is `6.90e-14` chips; largest separately trained root-value difference
is 0.00251755 chips. Largest final NashConv remains 0.02218518 chips in a
100-chip pot under the unchanged 0.50-chip gate. Actual inputs, outputs, source
hashes and all ten reference-profile digests are
[versioned](turn-independent-results.json); raw profiles and hashes were verified.

The local suite runs **75 tests**, with the real Linux allocation test
explicitly skipped on Windows. Ruff and compileall pass. Fresh existing eight
turn fixtures, ten river fixtures plus sensitivity, and all 188 river
decomposition games pass. Six fresh uninstrumented maximum-dimension runs
complete in 12.03–13.35 seconds on Windows, maximum resident peak 34.82 MiB;
[measurements](turn-performance-coverage.json) retain configurations and sources.

A separate development worker applies exact Linux 20-second CPU / 384 MiB
address-space limits before NumPy/product import and a parent 20-second wall
deadline. Six configurations vary combos, sizes and iterations, retaining the
original maximum workloads. Failure and unsupported statuses remain visible;
study success is not hosted acceptance. This Windows machine has no installed
Linux runtime and records six `UNSUPPORTED` probes. CI executes the real Linux
probes, oversized-allocation regression and a separate unlimited cProfile run,
retaining complete `turn-resource-study` artifacts. See
[method, local profile and limits](turn-resource-study.md).

Actual Ubuntu probes at source head `7bba663` in
[run 39131773211](https://github.com/eddieyang-97/poker-solver/actions/runs/39131773211)
complete all six cases within their applied budgets and convergence gates.
The maximum-size pair takes 13.285 / 13.589 seconds parent wall, with peak
virtual memory 109.02 / 108.29 MiB. [Linux evidence](turn-resource-linux.json)
retains actual limits; its archive and source hashes were verified. These
samples do not replace the historical slower observations or establish Render
capacity. CI's separate unlimited instrumented profile also completes.

Three larger product training runs differ between Windows and Ubuntu by up to
0.000136553 chips in root EV. All ten independent reference-profile digests
match exactly. Replaying every CI product policy in both Windows models agrees
within `5.23e-14` chips, and all cross-platform trained-value differences fit
their combined convergence gaps, with overlapping best-response intervals.
[Platform evidence](turn-platform-results.json) records the discrepancies;
the precise training-variation cause remains unisolated. No gate was relaxed.

Production code, deployment, MCP registrations and OAuth remain unchanged.
This does not establish full-range correctness, an audited external reference,
portable performance bounds or authenticated hosted turn acceptance. Historical
Ubuntu samples over 22 seconds remain evidence; later faster samples cannot
erase the unresolved resource/integration gates.


## Independently trained strategic turn reference — 18 October 2026

Following merged PR #8 (`11a6271d91d82fcde5fa619e559c65edf3515720`), added a
development-only full-state turn/river tree, chip ledger, information sets and
CFR+ trainer independent of the product implementation. Its isolated worker
receives only fixture configuration and records no imported product modules.
The existing pinned exhaustive ranker is reused; no upstream turn trainer or
externally audited solver is claimed. See [method and limits](turn-independent.md).

All **67 tests**, Ruff and compileall pass locally. Six strategic turn fixtures
pass at 2,000 product / 4,000 reference iterations. Both trees evaluate each
other's policies and best responses within `6.90e-14` chips; maximum separately
trained root value difference is £0.00022850. Largest final NashConv is
£0.02218518 in a £100 pot, below the unchanged £0.50 gate. Exact singleton
minimax and hidden-hand mixed-shove equilibria pass, including QJ's `19/44`
shove and KK's `1/2` call. Fault injection, hidden-hand pooling, exact chip/tree
mapping, card removal and incompatible-tree rejection are covered.

[Versioned outputs](turn-independent-results.json) retain exact inputs, source
hashes, checkpoints, turn policies and reference-profile digests. Raw profile
byte hash and all six profile/source digests were verified locally. CI runs
fresh training and retains complete profiles in `turn-independent-reference`;
local checks alone do not establish that a future CI run passed. Existing eight
turn fixtures, ten river fixtures plus sensitivity and four decomposition cases
(188 independently trained river games) passed fresh local reruns.

Production code, hosted registrations, deployment and OAuth are unchanged.
This is small-game local validation, not an external audited turn reference or
hosted acceptance. The earlier Ubuntu maximum-dimension measurements exceed
the 20-second hosted budget; that resource gate remains open.

## Turn decomposition and performance follow-ups — 17 October 2026

After PR #7 merged at `3e3a5ae7e72240851cc3d3a4678d6f35cf27fa96`, added a
development harness for independent river-subgame training with turn betting
disabled, plus maximum-dimension local performance workers. Solver core,
transports, production configuration and Auth0 are unchanged.

All **59 tests**, Ruff and compileall passed locally. The existing eight turn
fixtures and ten river fixtures plus separate raise sensitivity passed. New
tests verify weighted chance, zero-mass runouts, explicit independent tree/hand
mapping, fault detection, rejected tree/rounding substitutions, native memory
measurement and timeout reporting. See [method and limitations](turn-followups.md).

Initial Ubuntu CI run `39044753235` at `15cfc13` failed its eight-minute
decomposition step deadline: three cases passed and the fourth reached 36/48
cards. It did not complete acceptance. Based on the logged rate (about 2.8
seconds per river), the development sweep deadline is now 12 minutes; numerical
gates, per-process bounds and hosted limits remain unchanged. Retain this failed
attempt separately from the subsequent final-head result.

Four turn-disabled decomposition cases passed: 188 supported river games were
separately trained by the pinned independent reference, with four additional
zero-mass public cards explicitly recorded. Maximum aggregate EV difference
between separately trained engines was £0.00134293, within its £0.00876999
combined convergence-gap bound. Same-policy aggregate EV/gap discrepancies were
at most about `5.5e-14` chips. Every supported subgame and each aggregate passed
the unchanged 0.5%-of-pot convergence gate. Per-card masses, results and
reference-profile digests are versioned in
[decomposition evidence](turn-decomposition-results.json); full raw worker
exports are retained separately under `.artifacts/` and by CI. This special
case independently constructs and trains river trees, but does not validate
strategic turn betting against a separately trained full turn engine.

Six maximum-dimension subprocess measurements (24 combos/side, two sizes/street,
2,000 iterations, all-river queries) completed in 11.79–12.16 seconds process
wall time on Windows, maximum observed resident peak 34.66 MiB. Full measured
configuration, source hashes, platform and diagnostics are in
[performance evidence](turn-performance-results.json). These numbers are not
hosted resource-limit acceptance or a universal worst-case performance bound.

Ubuntu run `39045573429` at `eede111` passed all computational checks. Its two
maximum-dimension runs took 22.081 and 21.949 seconds process wall time, above
the hosted 20-second budget; turn remains local. Artifact retention did not
work: the default uploader excluded hidden `.artifacts/` paths and emitted
no-files warnings for all five report groups. The workflow now explicitly
includes hidden files within those narrow report paths and errors on missing
reports. Logs from the prior run remain evidence of computation, not successful
report upload. Local raw reference exports were independently hash-verified.

## Initial local turn implementation — 17 October 2026

After river prerequisite closeout merged as
`e2417485d6e6ca246d14d974e4af657a3d432ba8`, implemented a separate local
turn/river CFR+ engine and CLI. No accepted river core, hosted MCP registration,
worker limit, production deployment or OAuth configuration was changed.

The engine enumerates exact per-deal river chance, carries pot/contributions/
remaining stack across streets and solves future river decisions jointly.
Each public river has separate strategies; an output river filter cannot leak
future knowledge into turn decisions. It reports centered action EVs, hand-
conditioned reach, convergence checkpoints, zero-sum residual and NashConv.
The separate all-in-call calculator is valid only when no future betting remains.

**54 tests** passed locally, with Ruff and compileall. Eight fresh turn fixtures
passed at 1,000 iterations: largest policy/BR oracle difference about
`3.7e-14` chips; maximum NashConv £0.03139926 in a £100 pot under the unchanged
0.5%-pot gate. The exact singleton-range backward-minimax check also passed.
Actual local CLI calls returned inspectable computed outputs. See
[turn implementation](turn.md), [versioned results](turn-results.json) and
[readable comparison](turn-results.md).

PR #7 review identified an absolute `1e-14` opponent-reach cutoff that returned
null action EVs for valid, proportionally rescaled arrival ranges. Conditional
EV collection now divides at every positive opponent reach and reserves null
for zero reach. A regression compares singleton checkdown and weighted two-street
games when either or both ranges are multiplied by `1e-15`, including both
players' node EVs, frequencies and reach; impossible blocked branches stay null.
The reported singleton root check EV is −500/11 chips at either weight scale.
All 54 tests and static checks passed after the fix; all eight fresh turn and ten
river fixtures plus separate raise sensitivity passed without changing gates.
The sandboxed suite stalled in the process-admission test; the complete rerun
with normal Windows subprocess access passed. Turn JSON/Markdown evidence was
regenerated with the corrected source hash; the CLI record retains its original
source commit and remains historical acceptance evidence.

The scalar oracle uses the pinned upstream exhaustive hand-rank evaluator but
reads the product public tree and policy. It is not a separately trained turn
solver. External two-range turn cross-validation, larger-range performance,
bounded hosted transport and actual authenticated ChatGPT turn acceptance remain
open gates. The live connector continues to offer only the two accepted river
tools. The earlier river follow-ups also remain visible in the closeout document.

## River milestone status — 17 October 2026

PR #5 is merged as `af3d3984f569e70a2900a2b91fcd11e3619e332f`, after checking
both final-head workflows and the empty review threads. The original private
river pilot and Issue #1's initial ten-fixture acceptance criteria are met.
[River milestone closeout](river-milestone.md) maps each deliverable to actual
evidence and lists the still-open broader-reference and hosting/distribution
follow-ups. This does not claim those follow-ups or turn support are complete.

## Controlled reference experiment — 17 October 2026

PR #4's weighted-blocker diagnostic was reviewed and merged as
`cfd30d772d9d331e28314b109dda2311497d4c77`. Its two release-policy convergence
failures remain unchanged. A [separate averaging experiment](texas-averaging-experiment.md)
now prepares two identified source builds at the same pinned release revision:
an observer baseline and one history-preserving averaging variant. Matched
current/average policy snapshots will distinguish an averaging effect from a
changed training trajectory. Guarded preparation succeeded on the actual clean
source checkout locally; this Windows environment has no Qt/C++ toolchain.
The [dedicated source-build workflow](https://github.com/eddieyang-97/poker-solver/actions/runs/39023271206)
now passed on Ubuntu/GCC 13.3/Qt5. Both actual 40,000-iteration runs completed.
At 4,000/40,000 iterations the observer's JSON equals the original Windows
release exports exactly, retaining NashConv £1.59073955/£1.13173461 (FAIL).
Changing only the averaging multiplier to 1 yields independently evaluated
average NashConv £0.00335872/£0.00005794 (PASS under the unchanged £0.50 gate).
Current strategies match exactly between variants at all ten sampled checkpoints;
both current policies still fail. Same-checkpoint source/independent metric
difference is at most £0.00002164. This isolates a material averaging effect for
this fixture, not a general solver fix or new unmodified-reference acceptance.
All raw checkpoints, build hashes, commands and logs are retained in
[texas-averaging-results.json](texas-averaging-results.json); the detailed
interpretation and reproduction commands are in the experiment document.

Local verification: **45 tests**, Ruff and compileall pass. Tests reject mismatched
checkpoint iterations, changed fixture/commands and nonfinite source metrics;
identical policies cannot be labelled an observed averaging improvement. Actual
recorded policies are re-evaluated with a `1e-9` numerical replay tolerance and
the existing £0.000051 source-output precision allowance. The original accepted
ten-fixture benchmark, sensitivity analysis and Texas pilot replay still pass.
The numerical source-build commit also passed
[normal CI](https://github.com/eddieyang-97/poker-solver/actions/runs/39023271275).
Normal CI now replays the experiment evidence without compiling external source.

## Implementation audit

Audited repository baseline `ef174d8`: README, AGENTS, Python core, stdio/HTTP
adapters, tests, CI and Render Blueprint. The workspace was empty and was cloned
from the primary repository. Baseline core/stdio checks passed; the initial
environment lacked FastAPI, so HTTP tests could not import until dependencies
were installed. No prior poker deployment was listed in Render.

Findings and corrections:

| Finding | Resolution |
| --- | --- |
| HTTP hand-rolled partial MCP; arbitrary protocol version echoed | Official Python MCP SDK 1.30.0 stateless JSON-response transport; tested negotiation, methods, headers, invalid messages, body bounds |
| Static bearer token only; no OAuth metadata | External-provider OAuth resource server, JWT signature/issuer/audience/expiry/iat/scope/user checks, 401 discovery challenges; local static mode explicitly prohibited on Render |
| Thread execution had no hard timeout and queued requests | Disposable subprocess; timeout kills/reaps it; CPU/address-space cap on Linux; one in flight, no waiting compute queue, bounded starts/minute |
| Amounts accepted NaN/Infinity; inconsistent queries detected after solve | Finite positive numeric inputs, strict MCP schema validation, early queried-combo compatibility checks |
| Simultaneous clipped-regret updates converged slowly in polarized benchmark | Alternating CFR+ updates. The initial half-pot benchmark exceeded its 0.5%-pot NashConv test bound at 1500 iterations (0.545%); fixed algorithm passes the same test without relaxing its threshold |
| Few correctness regressions and no independent best-response check | Known category/tiebreak/board-tie and weighted call-EV cases; analytical half-/full-pot equilibrium; exhaustive pure-strategy deviation check of reported NashConv |
| Published private plugin still local | Updated the same private identity to 0.2.0 with hosted OAuth transport after real SDK acceptance; read source back. ChatGPT runtime connection is a separate gate |

The architecture reference was inspected read-only: `README.md`, `src/auth.ts`,
`src/app.ts`, `render.yaml`, `docs/account-linking.md`. Reused the patterns of
stateless MCP, resource metadata, exact-audience signed-token verification,
single-process limits, Free Render and explicit acceptance evidence. Did not copy
travel code, modify that repository, use its credentials, or add a database.

## Automated evidence

Local Windows / Python 3.14 virtual environment: **26 tests passed**, including an
official MCP client → HTTP app → signed ES256 token validation → actual worker →
both solver tools round trip. The HTTP boundary also tests RS256, algorithm
confusion, unsigned/expired/future-issued, wrong issuer/audience/scope/user tokens.
Body limits cover declared and chunked bodies. Timeout tests stop the worker and
prove the next calculation succeeds. Static checks: Ruff E9/F and compileall.
CI runs the same checks on Ubuntu/Python 3.12; remote results are recorded below
after pushing. Local execution required normal Windows subprocess access because
the restricted sandbox blocked asyncio process pipes.

The simple pot-sized analytical game uses board `2c,3d,4h,8s,9c`, OOP `KhKd`, IP
`AsAd,QhJd`, P=B=100. OOP checks. Indifference implies 50% IP air betting and 50%
OOP calls. At 1500 iterations: **50.01%** air bets, **49.93%** calls, root OOP
EV **−25.0001** relative to half pot, NashConv **0.0371 chips / 0.037% pot**.
The half-pot counterpart checks the analytical 1/3 air bets and 2/3 calls.
No external commercial-solver comparison has been performed. Tests bound the
observed approximation; they do not establish correctness for every river game.

## Independent solver benchmarking

**Tracking:** [Issue #1 — independent river-solver benchmarking and differential regression harness](https://github.com/eddieyang-97/poker-solver/issues/1).

The analytical and internal checks above are now supplemented by an offline
comparison with [noambrown/poker_solver](https://github.com/noambrown/poker_solver),
pinned to `6a10442877ffc8fd28af93e16e279b9bbdd97b2a`. Its independently authored
MIT reference subset is retained with license and source hashes under
`benchmarks/vendor/noambrown/`; the hosted application does not import it.

Ten versioned fixtures compare matching zero-rake, no-raise river trees, exact
bet amounts, weighted chance/card removal and normalized half-pot EVs. The
runner trains both engines separately, then independently evaluates the product
policy's root EV, action EVs and best responses. Reports include convergence,
reach, strategy differences, action regret and measured allocation/time costs.
Tree and rounding mismatches are rejected; near-tied frequencies are diagnostic.

All ten cases passed at 1500 product / 4000 reference iterations. The largest
root-EV difference was approximately **0.00111% of pot**. For the same policy,
independent action-EV evaluation differed by at most about `5.2e-15` of pot.
The reference fast evaluator initially raised `KeyError` for disjoint rank sets;
the supported upstream brute-force fallback is used explicitly, with a regression
for that limitation. No vendored algorithm or acceptance tolerance was patched
to force agreement. A fault-injection test confirms that corrupted product
evaluation is detected. The local suite now includes **32 passing tests**.

A separate reference-only one-extra-raise experiment changed OOP root EV by
about **£0.6124 in a £100 pot** for the dry merged fixture. This is a concrete
example of no-raise **modeling error**, excluded from same-tree correctness scores.
The product's action tree and hosted tools are unchanged.

See [benchmarking.md](benchmarking.md) for provenance, normalization, thresholds,
limitations and reproduction; [benchmark-results.md](benchmark-results.md) for
the delta table, and [benchmark-results.json](benchmark-results.json) for full
diagnostics. GitHub Actions runs the reference offline and retains JSON/Markdown
reports. This is a second-engine comparison on a small corpus, not exhaustive
correctness, commercial-GTO equivalence or empirical live-population validation.
The benchmark implementation at `0a3be662624e604cb816365a9b6a41cf9fc62ce8`
passed [GitHub Actions](https://github.com/eddieyang-97/poker-solver/actions/runs/38962276458),
including all 32 tests, static checks and the offline benchmark with sensitivity.

### Issue #1 contract follow-up

Read all two issue comments, including the latest source-verified configuration.
The ten-fixture implementation was already on `main`; this follow-up closes the
separate-process and exact-input evidence gaps rather than claiming a new initial
implementation. The unmodified upstream CLI was actually executed on the exact
£100 polarized input and **failed** with `KeyError: (1, 13, 9, 8, 4)` before
exporting a strategy. The independently executed upstream brute-force option
succeeded in an isolated worker that imports no product code. Its exact input
and actual output are versioned under `benchmarks/reference-polarized*.json`.

At 4000 reference iterations QJ bet **49.9712359%**, KK called **49.9987098%** and
OOP checked **99.9999432%**. Raw exploitability was **£0.0075206912**;
NashConv = twice that, **£0.0150413824**. Analytical targets are 50% QJ betting,
50% KK calls, 100% OOP checking and OOP root EV −£25 relative to half the pot.
The same pinned algorithm/input policy replay has a separate `1e-9` tolerance;
cross-engine frequencies retain the existing 0.04 analytical tolerance, with no
exact-mixture gate on general fixtures. Normalization, hand-order permutations
and weights have dedicated checks. No solver, transport, Auth0 or deployed
configuration was changed. See [benchmarking.md](benchmarking.md) for commands,
the failed CLI invocation, normalization and reference limitations. TexasSolver
cross-validation remains a subsequent milestone, not completed evidence.

Follow-up local verification: **34 tests passed**, Ruff and compileall passed,
and `python scripts/benchmark.py --output .artifacts/issue-1-benchmark --sensitivity`
passed all ten same-tree fixtures plus the separately reported raise experiment.
The pot-sized root EVs were −£25.00007147 (product, 1500 iterations) and
−£25.00000914 (reference, 4000). Product QJ betting / KK calling were
50.005608% / 49.931648%. No same-tree gate failed and no tolerance was widened.
The largest root delta remains about 0.00111% of pot across this small corpus.
Full refreshed outputs, convergence checkpoints and ordered reference profiles
are in [benchmark-results.json](benchmark-results.json); the readable table is
[benchmark-results.md](benchmark-results.md). This local evidence does not imply
hosted service changes or a successful run of the incompatible upstream CLI.

### TexasSolver standalone compatibility pilot — 17 October 2026

Reviewed and merged PR #2 as `99a49cee5ddd169a0fd68e3a0f55ac02b40ed5a7`, after
confirming green CI and no outstanding review requests. Then downloaded the
upstream Windows v0.2.0 console release into ignored local artifacts and inspected
its source tag `95f039c116fa7bcae7fb6c01aca56adb0f24c680`. No external source,
resource tables or binaries were committed, and production configuration and
solver behavior were unchanged.

The original concrete-combo input **failed**, exit 3, with `range str AsAd len
not valid`; no strategy dump was produced. The release accepts rank classes and
drops weights at or below 0.005. Its default implicit all-ins and integer bet
rounding also prevent assuming compatibility with the existing fixture corpus.

A separately labelled £100 pilot used full OOP `KK` versus `AA,QJo:0.5`, with
equal total value/bluff weight and a sole £100 shove. Its implicit all-in adds
no size in this specific tree. The actual executable returned a complete river
policy: QhJd bets 50%, KhKd calls 50% and checks 100%. The strict adapter checked
all decision nodes, player mapping (Texas IP=0/OOP=1), amounts, child sets and
card-keyed frequencies. Product and pinned noambrown CFR+ were separately run on
the same explicit 6/18-combo rank-class fixture.

Independent evaluation of Texas's actual exported policy gives OOP root EV
−£25.00000000 and NashConv about £3.6e−14. These EVs are **reconstructed from the
policy and declared terminal payoffs**, not returned Texas action EV fields.
The actual log reports `2.86102294921875e-06` percent exploitability, normalizing
to £0.00000572205 NashConv. The small log/dump difference is retained and falls
within the unchanged £0.000051 rounding gate; its exact cause is unresolved.

Actual commands, binary/lookup hashes, ordered dump, log and three-engine
comparison: [texassolver-results.json](texassolver-results.json).
[texassolver.md](texassolver.md) describes source inspection, failed input,
normalization, reproduction and limits. CI replays the saved actual policy
without downloading or executing TexasSolver; this does not establish a new
external run. The original concrete game, general blockers/weights and all ten
fixtures remain unverified with TexasSolver. No gold-standard claim is made.

Local verification passed: **37 tests**, Ruff, compileall, all ten original
same-tree benchmarks with the separate raise experiment, the actual standalone
Texas pilot, and offline replay. Three new adapter regressions cover player,
action/amount, child-set, combo and probability mismatches, along with refusal
to silently substitute another fixture. CI explicitly runs offline replay and
does not download or execute the external release.

### Weighted-blocker Texas diagnostic — 17 October 2026

Reviewed and merged PR #3 as `946adaa5314af00ee0d15b4b58ea3329290a302d` after
confirming its head CI passed and no review requests were outstanding. Newer
pinned Texas source still rejects concrete combos; no installed local C++/WSL
build environment was found. The original exact fixture remains blocked.

The next separately labelled diagnostic adds weighted IP KK to the earlier
rank-class game. Actual unmodified Texas runs at 4,000 and 40,000 iterations
returned policies with independently evaluated NashConv **£1.59073955** and
**£1.13173461** in a £100 pot. Both **FAIL** the unchanged £0.50 convergence gate.
Product/noambrown pass the same weighted game at the existing 1500/4000 budgets
(gaps £0.03584237 / £0.01608152). Compatible-pair enumeration confirms 114 pairs,
joint weight 75 and IP KK probability 4% after removal; an analytical policy
has OOP EV −£25 and independently evaluated near-zero NashConv.

The source conditions relative probabilities on compatible opponent weight, so
this has not been identified as a simple missing-blocker bug. A fixed 0.9
strategy-averaging discount was a candidate explanation for oscillation at this
original audit stage; no modified build/ablation had yet run. The subsequent
controlled experiment at the top of this document now isolates an averaging
effect for this fixture while preserving these release FAIL results. All source
inspection, raw outputs, logs and commands are in
[texas-blocker-audit.md](texas-blocker-audit.md) and
[texas-blocker-results.json](texas-blocker-results.json).
The audit CLI exits **1** and writes explicit FAIL reports. Regression replay
does not constitute a passing external solve. No failing fixture was removed,
no gate was widened, and no reference algorithm was patched during this original
audit. Production remains unchanged. This diagnostic remains outside the passing corpus.

Local regression verification: **40 tests**, Ruff and compileall passed. Tests
confirm the recorded external policies still exceed the original convergence
gate; this green regression result does not change their FAIL classification.

## £505 checked-river acceptance study

Board `Ks,9s,5h,Td,Ts`; BTN/IP `AsJh`; pot £505, effective remaining stack £450.
Prior streets and opponent tendencies were not supplied. All ranges are therefore
**illustrative weighted arrival hypotheses**, including value, showdown hands
and missed draws, rather than reconstructed facts. They do not use a revealed
opponent hand as the entire range. `KdQd` is a separate representative OOP
bluffcatcher query, not a statement of the opponent's actual cards.

Reproduce with `python scripts/acceptance.py`. Exact input ranges and complete
computed outputs are committed in [acceptance-results.json](acceptance-results.json).
The three OOP variants differ in full-house and flush weights: some traps, more
traps and fewer traps. Both players have the same allowed sizes. OOP can bet;
read the IP action conditional on its solved check. This is not a solve against
an externally forced checking range.

| OOP range | Allowed bets (£) | AsJh after check: bet frequency | Action EVs relative to £252.50 baseline | NashConv / pot |
| --- | --- | --- | --- | --- |
| Some traps | 450 | 100% jam | Check −252.50; jam −197.99 | 0.001% |
| More traps | 450 | 100% jam | Check −252.50; jam −230.14 | 0.001% |
| Fewer traps | 450 | 100% jam | Check −252.50; jam −169.70 | 0.001% |
| Some traps | 166.65 / 303 / 450 | 12.64% / 62.93% / 24.43% | −41.59 / −41.59 / −41.55 | 0.002% |
| More traps | 166.65 / 303 / 450 | 7.18% / 92.71% / 0.10% | −166.58 / −166.54 / −167.98 | 0.002% |
| Fewer traps | 166.65 / 303 / 450 | 8.77% / 89.91% / 1.32% | −11.13 / −11.03 / −11.31 | 0.003% |

The multi-size action EVs are often very close. These rounded frequencies are
computed average strategies, not precise or unique prescriptions. Adding sizes
also changes OOP's lead/check behavior and therefore its conditional checking
range. In the multi-size “some traps” case KdQd checks only 0.13%, so its later
bluffcatch frequencies at that node deserve particular caution. A small global
gap does not certify every rare-node strategy.

As blocks nut-spade flush combinations; Jh removes J-containing hands. Blockers
remove potential value and bluffs, and their net effect depends on the supplied
ranges and strategies. The observed small-tree preference for bluffing cannot
establish a live-population recommendation, especially if opponents trap more,
call too much, or arrive with different ranges. Those are hypotheses requiring
new computed assumptions, not measured population facts.

Separately, `evaluate_river_call` evaluates KdQd facing £450 against the exogenous
betting range `AsQs,QsJs,Js8s,99:0.5,55:0.25,QJs:0.5` plus five possible bluffs
`AsJh,AsQh,AsQc,AhQh,AhJh`, each at the indicated weight:

| Each bluff's weight | Call EV minus fold | Decision under that range |
| --- | --- | --- |
| 0.1 | −£337.60 | Fold |
| 0.5 | −£24.24 | Fold |
| 1.0 | +£203.49 | Call |

Required equity = 450/1405 = **32.0285%**. These are exact weighted showdown
calculations under assumed betting ranges, not equilibrium frequencies or proof
that the population uses any of those bluff rates. They are separate from the
solver-derived response nodes saved in the JSON.

## Hosted acceptance gates

The separate **Free Render** service is deployed at
[poker-solver-vie0.onrender.com](https://poker-solver-vie0.onrender.com/health),
service `srv-db934j67bikc73bppelg`. Auth0 uses the new dedicated poker tenant,
RS256, the exact `/mcp` audience, a one-hour access-token lifetime, required
consent, a `poker:solve` permission and an owner subject allowlist. No database,
paid service, client secret, signing secret or travel credential was used.

**Real hosted acceptance passed on 16 October:** the dedicated public diagnostic
client completed official-SDK discovery, S256 PKCE, state-checked loopback
callback and authorization-code exchange. Independent JWT verification confirmed
signature, issuer, exact poker audience and scope. After privately allowlisting
the verified owner, the hosted service negotiated MCP **2025-11-25**, listed both
tools and computed actual results. The exact weighted call test returned 1/3
equity and zero incremental EV. The polarized solve returned 50.01% air betting,
49.93% calling and NashConv 0.0371 chips (0.037% pot), matching the local benchmark.
The diagnostic exited successfully and cleared its in-memory token references;
no token, code, verifier or password was saved. The ignored local subject file
contains only a non-credential identity used for allowlisting.

The first diagnostic token exposed a roughly two-second clock offset. Validation
initially rejected it as future-issued; a bounded 30-second clock-skew allowance
resolved that while future-issued-by-ten-minutes tokens remain rejected in tests.
Signing-key fetch caching, rotation, unknown-key throttling and failure denial
also have regression coverage. `/health` now reports `auth_configured: true` and
`/ready` returns 200. Unauthenticated solve requests remain denied.

Deployed implementation `a4ba8e750582899642e468ba6c55d82bcc787d2f` passed
[GitHub Actions](https://github.com/eddieyang-97/poker-solver/actions/runs/38917109865).
The initial implementation also passed
[CI run 38914568790](https://github.com/eddieyang-97/poker-solver/actions/runs/38914568790).

**Current evidence:** hosted SDK acceptance was directly verified; the owner later
supplied the completed conversational £505 report, reproduced below. Raw hosted
tool payload capture, refresh/revocation/reconnect checks, and replacing Auth0's
Google development keys for production SSO/federated logout remain open. The SDK
diagnostic alone does not prove those behaviors. The user approved the diagnostic client's solver-only
grant and subsequently approved the third-party ChatGPT client's solver-only scope
and domain-level Google login promotion; both settings were saved and verified.
Arbitrary client registration is disabled. The same private plugin was published
as 0.2.0, release `pluginrel_6ad238301cb48191bdf3e8d25bcf6f8a`, and its hosted
endpoint, public client ID, scope and preserved identity were read back.
The first actual ChatGPT test found the skill but no callable solver tools;
publication alone has not established a runtime connection. A dedicated custom
MCP connection was therefore registered as private **Poker Solver Hosted**,
`plugin_asdk_app_6ad238f3cce881919faa6ecfcd1faee0`. ChatGPT discovered the correct
OAuth issuer/resource/scope and callback, completed solver-only Auth0 consent,
and displayed a connected notification. OIDC was disabled; no profile/email or
offline scope was requested for the ChatGPT connection. The verified app binding
was added to the original workflow as private 0.2.1, release
`pluginrel_6ad2397100c88191b12f471d1fc68503`, and read back. Source overlay:
`plugins/hosted/`. See [hosting.md](hosting.md).

### Initial ChatGPT attempt and reply-rendering blocker

Submitted the complete £505 request through the explicitly selected **Poker Solver
Hosted** connection. ChatGPT announced four solves (two trees × two range
hypotheses) and three separate call evaluations. The web client then reported
“Connection interrupted. Waiting for the complete answer”. A smaller explicit
call with board `Ks,9s,5h,Td,Ts`, hero `KdQd`, betting range `AsJs,AsJh:0.5`,
pot/bet 100 completed with the activity label “Evaluated River Bluff-Catch Call EV”.
The final reply displayed “This response couldn’t load”. Reloading and requesting
the previous raw result also failed to display it. The app's read-thread tool
reported completed turns but returned unresolved content references rather than
the final text. No returned JSON, frequencies or EVs could be inspected there.

Render logs independently showed authenticated `/mcp` HTTP 200 requests during
the ChatGPT connection and follow-up (16 October, approximately 15:48 and 15:53
Europe/London). This establishes traffic, **not successful calculations or correct
results**; HTTP 200 can contain a structured tool error. The separate official-SDK
diagnostic remains the verified hosted computation evidence. Do not relabel the
local £505 study as a completed conversational run.

For a direct payload audit, retry the prompt below in a fresh ChatGPT chat with
**Poker Solver Hosted** explicitly selected, and retain both tools' returned
payloads. The owner-supplied completed report and numerical reproduction below
supersede the earlier lack of visible results; they do not retroactively make
these failed display attempts successful. No new paid plan, broader scope or
solver credential is required for a retry. Access tokens currently last one hour; refresh is not configured or
verified, so reauthorization may be required. Production Google login keys and
refresh/revocation/reconnect tests are separate follow-up work. The diagnostic
client grant remains available for retesting; it has not been revoked.

The connection/configuration commit `fab6fc0c61f29728e791e0915f14cc013315a38e`
also passed [GitHub Actions](https://github.com/eddieyang-97/poker-solver/actions/runs/38919280695). All 26 local tests, Ruff and compileall passed again
before that commit; the hosted Python implementation remains `a4ba8e7` because
the later changes affect documentation and plugin packaging only.

### Owner-supplied completed ChatGPT report and reproduction

On 16 October the owner supplied the completed ChatGPT response stating that all
four final hosted solves and all three requested call evaluations succeeded. It
included full weighted ranges, 1200 iterations per solve, computed frequencies,
action EVs, root EVs, NashConv, combo counts, own strategic reach and an additional
range-overlap diagnostic. This is **owner-supplied conversational evidence**;
the attachment contains the assistant's report rather than raw MCP payloads.

Ran `python scripts/reproduce_chatgpt_acceptance.py` using those exact ranges and
parameters against the preserved Python engine. All four solves reproduced the
reported frequencies, check/bet/call EVs, root EVs, NashConv and 112/119 OOP/IP
combo counts. The three call evaluations and reversed-overlap diagnostic also
matched. **No numerical discrepancies were found and no solver output or
convergence threshold was tuned.** Complete local inputs/results and discrepancy
list: [chatgpt-acceptance-reproduction.json](chatgpt-acceptance-reproduction.json).
This reproduction independently checks the numbers, not their hosted provenance.

| Reported range/tree | AsJh after check: check / £166.65 / £303 / £450 | Check EV | Best bet EV | NashConv (£) |
| --- | --- | --- | --- | --- |
| Trap-rich, one size | 0.03% / — / — / 99.97% | −245.7149 | −244.7502 | 0.0057 |
| Trap-rich, three sizes | 0.02% / 89.57% / 4.79% / 5.62% | −252.4987 | −233.0067 | 0.0126 |
| Trap-light, one size | 0.02% / — / — / 99.98% | −215.4237 | −210.8820 | 0.0049 |
| Trap-light, three sizes | 0.01% / 30.39% / 19.28% / 50.32% | −252.4580 | −226.8926 | 0.0112 |

These are a separate set of range hypotheses from the earlier six-case study;
their different outputs are not a discrepancy. EVs use the half-pot baseline.
Near-pure betting does not imply a large gain: in the trap-rich one-size case,
jamming improves on checking by only £0.9647. The three bet EVs are nearly tied
within each multi-size solve. Their precise mixtures should not be generalized
to live opponents or called full GTO.

The report correctly distinguishes `own_reach_probability: 1.0` at the IP nodes
from OOP's check/bet probability. It is not an unconditional node-reach estimate;
the endpoint currently does not expose that probability. Keep that limitation
explicit when discussing rare branches.

The betting range `AsQs,QsJs,Js8s,99:0.5,55:0.25,QJs:0.5` overlaps: the later
`QJs:0.5` replaces QsJs's earlier weight with 0.5. With each of the five bluffs
weighted 0.5, KdQd has equity 30.3030%, weighted opponent combos 8.25 and call EV
−£24.2424. Placing `QsJs` after `QJs:0.5` changes its weight to 1, giving equity
28.5714%, weighted combos 8.75 and EV −£48.5714. Both retain 16 distinct combos
after blockers. Added a regression for this diagnostic; **27 tests**, Ruff and
compileall passed. Last-token weighting remains documented behavior.

The report also identified an input-format failure: `Ks9s5hTdTs` was rejected;
`Ks,9s,5h,Td,Ts` succeeded. Use the latter in conversational tool arguments.

For a repeat through the connected hosted plugin, submit:

> Review a past heads-up river: BTN AsJh on Ks,9s,5h,Td,Ts, £505 before river betting,
> £450 remaining, OOP checks. Use plausible full weighted arrival ranges including
> traps, bluffcatchers and misses, state assumptions, and call solve_river with
> both one-size (£450) and multi-size (£166.65, £303, £450) trees. Report actual
> AsJh frequencies, action EVs, NashConv and node reach. Separately evaluate KdQd
> bluffcatching against low/medium/high hypothetical betting-bluff weights using
> evaluate_river_call. Distinguish computation from population speculation.

Save the server version, deployed commit, provider/client identity (no secrets),
tool payloads/results, rejection cases and ChatGPT invocation evidence. Confirm
GitHub Actions passes. Verify token refresh, access removal and reconnect before
claiming reliable private hosted use. No unrestricted GTO claim is warranted.

### Direct authenticated connector acceptance after reconnect

Later on 16 October, invoked the actual **Poker Solver Hosted** connector tools
directly in this chat and retained their returned `structuredContent`, rather
than an assistant's summary. The connection initially requested authentication,
then returned `UNAUTHORIZED` / requires reauthentication. The owner explicitly
reconnected it in their signed-in ChatGPT account. Another auth prompt was
accepted, followed by a network timeout at 20 seconds. A public `/health` request
then took about 29 seconds; after this startup delay, authenticated calculations
succeeded. No scope, allowlist or security check was weakened.

Both diagnostic calls succeeded: the exact call test returned 1/3 equity and
zero call EV; the analytical polarized solve returned 50.01% air betting, 49.93%
calling and NashConv £0.0371. Then all four full £505 solves and all three
bluff-weight call evaluations succeeded sequentially. **Every input and every
returned result field matched `chatgpt-acceptance-reproduction.json` exactly**
(JSON numeric equality, without a tolerance). This closes the raw-payload gap
for those seven calculations. The earlier range-order diagnostic remains local
reproduction/owner-reported evidence; it was not repeated through the connector.

[hosted-acceptance-results.json](hosted-acceptance-results.json) records the actual
seven requests/results plus two analytical diagnostics, endpoint, deployed
Python commit, service version, issuer and app binding. It contains no bearer
tokens, authorization codes, passwords or owner subject. The service remains
version 0.2.0 at `a4ba8e750582899642e468ba6c55d82bcc787d2f`; subsequent benchmark,
packaging and evidence commits require no production redeployment.

The £505 frequencies and EV table above is now directly confirmed by hosted
payloads. For KdQd facing £450 into £505, the three hypothetical betting ranges
returned call EV −£337.60, −£24.2424 and +£203.4884, with required equity 32.0285%.
Those are exact calculations against supplied betting weights, not an inferred
opponent strategy. The full-range CFR solves remain no-raise/no-rake
approximations, and closely tied action EVs do not justify precise live mixtures.

**Remaining operational gates:** explicit reconnect recovery now has positive
evidence, but automatic refresh is neither configured nor verified. Provider
grant revocation/access removal and a second-account connection remain untested.
Auth0 Google login still uses development keys. Free Render cold starts can
exceed the connector's request timeout, so this is a working private pilot with
availability limits. Do not describe it as reliable always-on hosting or a
friends beta that has passed multi-account acceptance.
