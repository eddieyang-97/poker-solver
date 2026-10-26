# Poker Solver

[![CI](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml/badge.svg)](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml)

**Post-session, educational heads-up NLHE decision analysis**, with a deterministic Python solver and private MCP transport. This is a **constrained river game**, not full GTO or a calibrated opponent model. Realistic ranges, omitted betting lines, multiway play and off-equilibrium outcomes require separate assumptions and verification.

## What works, and where

| Capability | Current supported boundary |
| --- | --- |
| **Hosted river tools** | Private `solve_river` (no-raise/no-rake, caller-supplied weighted ranges) and `evaluate_river_call` (equity / pot-odds calculation). Auth0 OAuth + subject allowlist; real private ChatGPT calls to both tools are recorded in [acceptance evidence](docs/validation.md). Cold starts and client refresh/revocation remain practical limits. |
| **Local river extensions** | Opt-in [river raises](docs/river-raises.md) and [exact-size hand review](docs/hand-review.md); separate numerical reference cases, **not** part of hosted river tool semantics. |
| **Local hand/range research** | [Hand reconstruction](docs/hand-review.md) and [action-frequency range explorer](docs/range-explorer.md). Declared hypotheses, exact pot accounting and card conditioning; no population calibration, automatic range substitution or node locking. |
| **Experimental local turn** | [Turn/river solver](docs/turn.md), [independent reference](docs/turn-independent.md), [resource/feasibility](docs/turn-feasibility.md), and [reuse experiments](docs/turn-reuse.md). Development only by default; source policy or near-neighbour EV is not necessarily target-game equilibrium. |
| **Optional hosted turn pilot** | Separately configured `solve_turn_v1` via [opt-in factory](docs/turn-pilot.md), narrower than local turn. **Stage B has not passed** actual hosted latency/headroom gates despite pinned-game computation; default HTTP/stdio registrations remain river-only. [Current timeout evidence](docs/turn-hosted-timeout.md) and [release decision](docs/turn-pilot-release.md). |

**Current work and remaining acceptance:** [GitHub Issues](https://github.com/eddieyang-97/poker-solver/issues) are the only actionable queue. [#25 reuse](https://github.com/eddieyang-97/poker-solver/issues/25) has owner-merged research evidence pending issue disposition; [#26 hosted turn](https://github.com/eddieyang-97/poker-solver/issues/26) remains open for a viable acceptance/release decision. [Development scope](docs/development-roadmap.md) explains future milestones without repeating PR histories. New solver correctness is not evidence of deployment, useful range modelling or working connected-client tools.

## Local quickstart

Python **3.10+**; CI and Render use 3.12.

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

For PowerShell, set `$env:OPENBLAS_NUM_THREADS='1'` before the tests. Windows restricted shells may block subprocess fixtures. All routine tests run with local/fictional data and no live provider keys. [Numerical/independent benchmark reproduction](docs/benchmarking.md) and [full evidence index](docs/validation.md) explain the extra gates and recorded failures; a local green test is not provider acceptance.

## MCP and hosted operations

- Local stdio: `python -m poker_spot.mcp_server` with root `plugin.json`, `mcp.json` and `skills/river-review/`.
- Local HTTP: set `POKER_MODE=local` and a random `POKER_MCP_TOKEN` of at least 32 characters, then run `uvicorn poker_spot.http_server:app --host 127.0.0.1 --port 8000 --workers 1`. Send bearer auth and appropriate MCP content-type headers. **Never use local-token mode on Render.**
- Hosted: dedicated [Free Render service](https://poker-solver-vie0.onrender.com/health) and Auth0 Free, validating JWT signature, issuer, exact `/mcp` audience, expiry, `poker:solve` and approved subject. No unauthenticated solver calls. `/health` means liveness, `/ready` verifies configuration, `/.well-known/oauth-protected-resource` advertises OAuth, and `/mcp` runs the authorized Streamable HTTP tools.

One hosted worker at a time, 30 calculation starts/minute, 16 KiB request body, 20s wall/process time and Linux CPU/384 MiB address-space limits. Production river CFR permits at most 1,500 iterations, 180 combos per side and 22,500 pairs. The separate, narrower turn pilot has its own contract; **do not conflate these limits**. Free service cold starts may exceed connector timeouts; no paid plan is authorized.

See [hosting and release](docs/hosting.md), [CI/deployment operations](docs/releases.md), and [friends-only onboarding design](docs/distribution-flow.md) for current instructions. A custom connector or approved account requires actual OAuth completion and a computed tool result before claiming ChatGPT/Claude acceptance. There is no runtime dependency on the trip-planning-engine project.

## Read results correctly

- `solve_river` action EVs use the **half-starting-pot baseline**. Compare actions at the same node; checking is endogenous. Reach can be zero, in which case an action EV is `null`; don't interpret rare-node frequencies as precise predictions.
- `evaluate_river_call` uses pot **before** the bet: EV versus folding = `equity * (pot + 2 * bet) - bet`; required equity = `bet / (pot + 2 * bet)`. It does **not** infer the opponent's betting range or solve equilibrium.
- Low NashConv measures exploitability **inside the stated game** only. [£505 acceptance scenario](docs/validation.md#505-checked-river-acceptance-study) uses explicitly hypothetical weighted arrivals, not an observed range. See [benchmark evidence](docs/benchmarking.md) and [limits](docs/validation.md).

This is a public MIT-licensed repository. Keep credentials and private hand/account data out of commits and artifacts; use post-session analysis only.
