# Issue #26 — local turn MCP pilot, Stage A

**Local implementation, no production release.** The owner merged feasibility
PR #30 at `20129d8f0e31298857e0e73e1b834b6f180b3dd9`. Its slower Linux samples
retain both 24-combo timeouts, despite faster successful runs. The measured
two-combo/one-size game has headroom; it does not establish a universal bound.
See [the historical receipts and decision](turn-feasibility.md).

Choose **C, bounded live-only**. There is no cache, approximate match, database,
catalog packaging or miss fallback. #25 remains deferred without organic exact
repeat demand. Cache hit/miss/stale/corrupt classifications are inapplicable to
this path; changed inputs always describe a fresh game. This pilot is useful for
small pedagogical range/sizing comparisons only. Two-combo ranges do not model
normal full-width poker arrivals; neither synthetic coverage nor low NashConv
validates their realism. General hosted turn remains no-go.

## Explicit opt-in and authentication

The existing `poker_spot.http_server:app` and stdio adapter still list exactly
`solve_river` and `evaluate_river_call`. No environment flag activates turn.
Tests use `create_app(settings, turn_pilot=True)`; the constructor refuses this
opt-in whenever `RENDER` is set. A separately reviewed Stage B code change is
necessary before hosting. No Render start command, provider/client, subject,
scope, published plugin or account configuration changes in this milestone.

To serve the local prototype, configure the existing **local development**
authentication (`POKER_MODE=local`, a private `POKER_MCP_TOKEN` of at least 32
characters) in your own shell, then run with Python 3.11+:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/serve_turn_pilot.py --port 8765
```

This binds only `127.0.0.1`, one worker; no unauthenticated mode is provided.
Never reuse, print or commit production credentials. The official-client test
instead uses ephemeral signed JWTs and a mock local JWKS key, with the **actual**
resource verifier: signature, issuer, exact audience, expiry, scope and owner
allowlist remain mandatory before body processing/admission. This proves the
local integration boundary, not live Auth0 refresh/revocation or ChatGPT consent.

## Versioned contract

Tool `solve_turn_v1`, schema/result version `turn-pilot-v1`:

- Four-card `board`; both complete explicit `oop_range`/`ip_range` arrays with
  1–2 concrete hand/weight rows. Positive finite weights in `[1e-6,1]`, kept
  exactly as supplied after binary64 parsing. Duplicate or board-blocked rows,
  unsupported rank-class syntax and combos with no compatible opponent reject.
  No silent dropping, range inference, posterior marginal substitution or locks.
- Integer `pot_cents`/`stack_cents`, 1–1,000,000 each. Start **before turn betting**.
  Each street takes 0–1 pot fraction in `(0,3]`; the river fraction uses its
  updated pot. Explicitly disclosed stack capping preserves the local engine's
  semantics; no additional jam is inserted. All normalized bets must be exact
  cents under private Decimal arithmetic; fractional cents reject, never round.
- Exactly **2000 iterations**, no caller trade of convergence for speed. Heads-up,
  no raises/rake; all 48 public rivers, exactly 44 legal per compatible deal.
- Optional `views`, at most four `{player, hand, node, river_card}` rows. Hand
  must be in that player's full range; node/actor must match the built tree.
  River nodes require a legal single card; turn nodes forbid one. Board/own-hand
  blocked views reject. A river excluded by every compatible opponent returns
  zero reach and **null EVs**, not an invented conditional answer. An empty view
  list returns diagnostics/identity/tree amounts, without strategies.

[Example request](../examples/turn-pilot.json). `turn` is OOP's initial node;
`turn/check` is IP after an endogenous OOP check. A called turn bet continues at
`turn/bet_50/call/river` for a £50 bet. Public bet labels use exact cents with
unnecessary trailing zeros removed: £30.10 is `bet_30.1`, £45.15 is `bet_45.15`.
The pilot maps these identifiers onto the existing numerical tree; float repr
artifacts are not public aliases. Node/action labels and disclosed effective-bet
histories/amounts share this convention. Terminal contributions, training order,
policies and EV calculations are unchanged. Label collisions or a float tree
whose topology differs from the exact-cent tree reject before training (including
an exact turn all-in that leaves a spurious binary64 residual river). The tiny
internal float/cent consistency allowance never admits fractional-cent inputs.
These are tree identifiers, not free-form observed actions. An unsupported label rejects **before
training**, rather than mapping to the closest amount or forcing an action.
Future-card filters affect output alone, never the turn information set.

Each computed response includes full game configuration, effective tree amounts,
2000-iteration checkpoints/root EVs/best-response NashConv, 44-per-deal chance,
solver/source/runtime identities, request/result hashes and at most four rows of
average strategy, conditional EV and own/opponent/chance reach. EVs remain
centered on half the **initial turn pot**, including both streets' contributions.
Action EV fixes average future continuations; it does not optimize future
deviations. Low-reach EVs/mixtures can be inaccurate despite a tiny root gap.

`game_identity_sha256` excludes output views, but includes complete ordered
weighted ranges, board, money/tree, iterations, source hashes and Python/NumPy.
No suit, range-order, weight-scale or monetary-scaling equivalence is assumed.
This is provenance, **not** a cache lookup or signed execution attestation.
`result_sha256` covers the returned solution excluding itself and the separately
added nondeterministic `execution` receipt. `request_sha256` hashes the fully
validated/default-filled request. Source hashes normalize CRLF to LF.

## Failure and resource behavior

| Outcome | Return behavior |
| --- | --- |
| Admitted, root gate passes | `source=computed_on_demand`, `status=computed`; bounded views |
| Root gap exceeds unchanged 0.5% of initial pot | `status=insufficient_convergence`, same computation source, diagnostics but **no strategy/EV rows**; MCP `isError=true` |
| Invalid/out-of-subset inputs or views | Structured `invalid_input`; no speculative result |
| Busy / rate limited | Shared `busy` / `rate_limited`; no waiting queue |
| Parent deadline | `timeout`; child killed and reaped, slot released |
| Memory, killed worker, oversize output | `resource_limit`, `worker_failed` or `output_limit`; no solution |
| Other non-Linux/non-Windows platform | `unsupported`; no computation |

Windows calculations are explicitly **unlimited local validation**. Their receipt
says `budget_enforced=false`; no Linux or hosted budget acceptance follows.

The pilot reuses the existing runner's **single admission slot and 30/minute
allowance across all three tools**. It cannot create a separate queue or evade
river admission. The isolated `-I` child is launched as a direct script, avoiding
package/NumPy import before Linux hard/soft **20s CPU, 384 MiB AS** limits. Its
environment strips credentials and Python path overrides; threads stay at one.
The parent deadline is at most 20s through spawn, read/parse/solve/BR/projection,
serialization and reap. Cancellation during spawn captures and reaps the child;
cleanup after a deadline is awaited before releasing admission.

Input body stays **16 KiB**. Solution JSON is capped at **24 KiB**, worker envelope
26 KiB; parent stdout reading is bounded. Four views deliberately avoid the
281 KB all-runout response seen in #21. The study measures actual duplicated
text/structured SDK envelopes against a conservative **64 KiB local gate**.
That is an engineering bound, not a verified current ChatGPT payload contract.
Actual client acceptance and cold-start/network latency remain Stage B gates.
CPU/memory snapshots precede final envelope write/exit; kernel limits continue
through exit, and parent wall includes reap. Stage timings retain bootstrap/
imports, read/parse, validation/training/BR/projection/receipts and serialization.

## Reproduce and assess

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python -m unittest discover -s tests -p test_turn_pilot.py -v
.venv/Scripts/python scripts/benchmark_turn_pilot.py --output .artifacts/turn-pilot
.venv/Scripts/python scripts/benchmark.py --sensitivity
.venv/Scripts/python scripts/benchmark_turn.py
.venv/Scripts/python scripts/benchmark_turn_independent.py
```

The local study measures two fresh-process samples of four existing independently
checked games: singleton draw/overpair, weighted dry, weighted collisions and
terminal turn all-in. Full requests, results, SDK bytes, stage timings, limits,
checksums and source hashes are retained. These are four declared **synthetic**
study questions, not an estimate of real-user coverage. Two combos and one size
are upper admission limits, not proof every such configuration converges or fits.
Actual tight timeout followed by recovery and five rejected input classes run
in the study. The insufficient-convergence boundary is fault-injected in unit
tests; #21 retains an actual 20-iteration unconverged solve. We do not claim an
observed failing 2000-iteration admitted game if none was measured.

The CI `resources` job runs this actual runner study on Linux, extending the
existing `turn-resource-study` artifact; all eleven groups and exact four-job
fail-closed `test` dependency set remain. No gates are skipped or relaxed.
Unchanged ten-game independent training, 188-game decomposition, same-policy
checks, original six resource probes and all river/raise regressions still run.
This independent reference is in-repository, not externally audited. General
24-combo correctness and realistic arrival-range quality remain unestablished.

See [validation](validation.md) for observed runs, and the separate
[release decision and pending gates](turn-pilot-release.md). Stage A does not
complete Issue #26's hosted acceptance; keep the issue open.

Source `a9ade24` passed [Linux CI 39936495563](https://github.com/eddieyang-97/poker-solver/actions/runs/39936495563):
164 tests, all numerical gates and eleven artifacts. The eight bounded pilot
samples took 1.147–3.548s parent wall, <=3.521s CPU, <=119.83 MiB AS, and <=10,837
SDK bytes. [Pinned measurements and receipts](turn-pilot-results.json) retain
every sample and the two fresh maximum-workload timeouts. This is standalone
Linux/shared-runner evidence, not actual Render or client acceptance.
