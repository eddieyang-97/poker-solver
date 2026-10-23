# Poker Solver

[![CI](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml/badge.svg)](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml)

Computed heads-up NLHE **river-only, post-session study** with a Python solver and
MCP tools. This is a restricted no-raise, no-rake river model, not a full GTO solver.
Hosted tools have no preflop, flop, turn, multiway, database, or web UI support.
A separate [experimental local turn/river engine](docs/turn.md) now supports
small two-street studies through a CLI. It is not registered with hosted MCP.
An [independently trained local reference](docs/turn-independent.md) checks ten
small strategic turn games with its own tree and chip accounting. A separate
[local resource study](docs/turn-resource-study.md) probes Linux budgets and
profiles larger workloads. The reference is developed in this repository and
has not been externally audited.

An opt-in [local river raise/check-raise solver](docs/river-raises.md) supports one
additional raise after a bet, explicit finite sizes and cent-exact accounting.
Its separate independent validation corpus is not part of the no-raise benchmark
score. It is not registered with MCP or deployed; hosted tools remain no-raise.

A local [post-session hand-history review workflow](docs/hand-review.md) reconstructs
street-by-street pots/stacks, preserves explicit range assumptions and optionally
executes the existing bounded river tools. It accepts structured hands or bounded
position/action prose, reports missing details and retains exact requests/results.
This implements Phase 1 of [the workflow roadmap](https://github.com/eddieyang-97/poker-solver/issues/11).
An opt-in [local action-model range explorer](docs/range-explorer.md) now evaluates
editable frequency hypotheses, joint card removal across up to three participants
and sensitivity, retaining folded players' latent cards. It computes conditioning
only and never substitutes posterior marginals into the solver. Calibrated
population models, node locking and automatic integration remain follow-ups. Earlier multiway streets
are accounted for, not solved. No hosted tool or plugin behavior changes.

The [development roadmap](docs/development-roadmap.md) tracks local implementation,
solver correctness, range-model quality and hosted acceptance separately.
The local [turn feasibility experiment](docs/turn-feasibility.md) measures full
policies, resource failures and strict exact-game reuse without exposing a tool.
Joint-range/node-locking and advanced hosted tools have their own acceptance gates.
An opt-in [exact-size local raise review](docs/hand-review.md#opt-in-local-exact-size-river-raises)
now prepares and runs the existing one-raise worker from reconstructed river
amounts, with explicitly supplied ranges and no node locking or hosted changes.

**v0.2 implementation:** official-SDK stateless Streamable HTTP, OAuth resource
metadata and JWT verification, bounded subprocess calculations, analytical
regressions and official-client integration tests. Real provider setup, deployment
and ChatGPT connection evidence are tracked in [validation](docs/validation.md).
A passing local SDK test does not establish a working hosted ChatGPT plugin.
The dedicated [Free Render service](https://poker-solver-vie0.onrender.com/health)
is live; real Auth0 S256 OAuth and both hosted tools passed the official SDK
diagnostic. ChatGPT OAuth consent completed for the private **Poker Solver Hosted**
connection, linked to the existing **poker-spot-study 0.2.1** workflow. Conversational
tool execution evidence is tracked separately in validation. After the owner's
explicit reconnect, both connector tools returned inspectable calculation payloads
directly in this chat. All four £505 river solves and three call evaluations
matched the local reproduction exactly; [actual inputs and returned results](docs/hosted-acceptance-results.json)
are retained. Free Render cold starts can exceed the connector timeout. Automatic
refresh, access-removal testing and production Google login setup remain follow-ups.

An [independent river benchmark](docs/benchmarking.md) now compares ten matching
trees with a pinned MIT reference engine, including independently evaluated EVs,
card removal and convergence. CI runs it offline and publishes delta reports.
This small-corpus agreement does not establish full NLHE GTO correctness.

A separate [TexasSolver compatibility pilot](docs/texassolver.md) records an
actual standalone rank-class solve and offline evidence replay. The tested
release rejects concrete combos, so the original single-combo fixture and
general weighted/blocker cross-validation remain unsupported by that pilot.
A separate [weighted-blocker audit](docs/texas-blocker-audit.md) records two
reference convergence failures; they remain outside the passing fixture corpus.
The [controlled averaging experiment](docs/texas-averaging-experiment.md) isolates
an averaging effect on that weighted fixture without replacing those failures.
See the [river milestone closeout](docs/river-milestone.md) for completed
deliverables and the follow-ups that remain before broader use or turn support.

| Tool | Returns |
| --- | --- |
| `evaluate_river_call` | Exact card-removal-adjusted showdown equity, pot odds and incremental call EV against a supplied weighted **betting range** |
| `solve_river` | Alternating CFR+ action frequencies, action EVs, effective bet amounts and NashConv for two supplied weighted **arrival ranges** |

Ranges support `AA`, `AKs`, `KQo:0.4`, `AsJh`, comma-separated. Weights are relative
arrival/betting likelihoods in [0,1], not independently inferred population facts.
Board cards and conflicting hole cards are removed. Overlapping range tokens use
the last token's weight. Raises and rake are excluded; each player may check or
bet one to three pot fractions, capped at remaining effective stack. Facing a bet,
only call/fold is available.

## Run and validate

Python 3.10+; Render and CI use 3.12. Use a project virtual environment:

```sh
python -m venv .venv
# Activate .venv (Windows: .venv\Scripts\Activate.ps1)
pip install -r requirements-dev.txt
python -m ruff check poker_spot tests scripts
python -m compileall -q poker_spot scripts
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
python -m poker_spot example.json
python scripts/acceptance.py
```

In PowerShell use `$env:OPENBLAS_NUM_THREADS='1'` before the test command. Windows
subprocess tests require normal process/pipe access; restricted sandboxes can
prevent asyncio subprocess creation. The suite includes actual worker calls,
timeout recovery, JWT rejection, protocol negotiation and a signed-token official
MCP SDK round trip. It needs no provider credentials or network.

## MCP transports

Local stdio remains available with `python -m poker_spot.mcp_server` and the root
`plugin.json`, `mcp.json`, and `skills/river-review/`. The previously published
private plugin remains local until a tested hosted release replaces its config.

Local HTTP development requires `POKER_MODE=local` and a random
`POKER_MCP_TOKEN` of at least 32 characters, then:

```sh
uvicorn poker_spot.http_server:app --host 127.0.0.1 --port 8000 --workers 1
```

Supply the token in `Authorization: Bearer ...`; accept both `application/json`
and `text/event-stream`. The SDK negotiates protocol versions, handles JSON-RPC
and returns JSON responses; no persistent MCP session or SSE subscription exists.
GET may return 405 as permitted by Streamable HTTP. Local-token mode is disabled
on Render. Hosted solves always require OAuth and an allowed user subject.

## Hosting and ChatGPT

Use the dedicated **Free Render** service in `render.yaml` and **Auth0 Free** for
authorization-code/PKCE, consent and client registration. The service verifies
signature, issuer, exact resource audience, expiry, issued-at, `poker:solve` scope
and the owner subject allowlist. No OAuth signing secrets or client secret are
stored by this service. `.env.example` lists configuration; never commit real
credentials or tokens.

Follow the [deployment, Auth0 and private-plugin setup guide](docs/hosting.md).
For friends-only beta onboarding and later distribution phases, see the [distribution flow](docs/distribution-flow.md). This remains a proposed flow until a second account successfully connects and invokes both tools.
The trip-planning-engine architecture was reviewed read-only for reusable
deployment/authentication patterns; poker-solver has no runtime dependency on it.

| Endpoint | Meaning |
| --- | --- |
| `/health` | Process liveness, including whether auth is configured |
| `/ready` | 200 if configuration is complete; 503 otherwise; does not probe the provider |
| `/.well-known/oauth-protected-resource` | OAuth resource, issuer and scope discovery |
| `/mcp` | Authenticated official-SDK Streamable HTTP tools |

Deployments missing provider configuration refuse MCP traffic with 503. A configured
provider with no owner allowlist challenges with 401 to permit first-time linking,
while denying all tool execution. Missing/invalid hosted
tokens receive 401 and a resource-metadata challenge. No public unauthenticated
solve path exists. A single worker admits one calculation at a time, 30 starts
per minute, a 16 KiB body limit and hard 20-second process timeout. Linux workers
also have CPU/address-space limits. Hosted CFR caps are 1500 iterations, 180
combos per side and 22500 Cartesian pairs. Free Render cold starts and shared
free-instance hours limit availability. There is no paid infrastructure approval.

## Interpret results

`solve_river` EVs use the symmetric **half of the starting pot** baseline; compare
actions at the same node. Negative values can still be preferable to checking.
For a checked river inspect `ip_after_oop_check`. OOP's checking strategy is solved
endogenously, not fixed by an exogenous check range. Check node reach before
interpreting a rare branch. `null` action EV means no opponent reach at that node.

`evaluate_river_call` uses pot **before** the opponent's bet and reports
`equity*(pot+2*bet)-bet` relative to folding. Required equity is
`bet/(pot+2*bet)`. It does not solve equilibrium or infer a betting range.

Small NashConv measures exploitability only inside this supplied game. It cannot
validate ranges, omitted raises, population tendencies, or exact frequencies for
rare hands. Nearly tied EVs can support different mixtures. The
[£505 pot acceptance study](docs/validation.md) records all ranges, assumptions,
computed outputs and remaining integration gates.

MIT licensed. The GitHub repository is public; keep deployment secrets out of git.
