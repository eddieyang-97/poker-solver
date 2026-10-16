# poker-solver

[![CI](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml/badge.svg)](https://github.com/eddieyang-97/poker-solver/actions/workflows/ci.yml)

Decision-focused **heads-up Texas Hold'em river analysis** backed by a lightweight, restricted-tree CFR+ solver. Designed to supply *computed* frequencies and action EVs to conversational poker review—not to replace a general-purpose NLHE solver.

**Status: published MVP v0.1 (not deployed).** The river engine, stdio MCP adapter, HTTP MCP adapter and local tests work. A hosted Render instance and ChatGPT OAuth connection have **not** yet been deployed or verified. No preflop/flop/turn solve, multiway analysis, raises, rake, or live-game opponent modeling is included.

## What it can do

| Tool | Function | Interpretation |
| --- | --- | --- |
| `evaluate_river_call` | Exact river showdown equity and incremental call EV against a *supplied betting range*, with card blockers | Exact under the given assumptions; **not** a GTO calculation |
| `solve_river` | Approximate equilibrium with CFR+ given both river arrival ranges and 1–3 allowed bet sizes | Frequencies/EVs describe the **restricted no-raise river subgame**, not unconstrained GTO |

A river solve supports OOP check/bet, IP check/bet after a check, and fold/call facing bets. The tool returns per-hand action frequencies, action EVs and a NashConv diagnostic. Input ranges are **not** inferred from earlier streets: you must supply plausible ranges *at the start of the river*.

### Example: evaluate Carrie's bluff-catch

```python
from poker_spot.core import evaluate_river_call

result = evaluate_river_call(
    board="Ks,9s,5h,Td,Ts",
    hero_hand="KdQd",
    villain_betting_range="QJs,AsJh:0.5,AsQd:0.5,AsJs",
    pot=505,
    bet=450,
)
print(result)
```

**Important:** The betting range is hypothetical and does not represent an independently verified range for the hand.

## Quickstart

Requires Python 3.10+ (deployment example uses Python 3.12).

```bash
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
python -m poker_spot example.json        # example restricted river solve
```

### Local MCP (stdio)

```bash
python -m poker_spot.mcp_server
```

The program reads newline-delimited JSON-RPC messages from stdin and emits MCP tool responses to stdout. The root `plugin.json`/`mcp.json` and `skills/river-review/` are retained from the local ChatGPT Desktop MVP.

### Local HTTP MCP

```bash
export POKER_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export OPENBLAS_NUM_THREADS=1
uvicorn poker_spot.http_server:app --host 127.0.0.1 --port 8000
```

In another terminal, using the same token:

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $POKER_MCP_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

`GET /health` returns 200 only when the token is configured. The stateless `/mcp` endpoint implements JSON responses for basic initialize, discovery and tool calls, and 202 for notifications. **It is a deliberately small MCP HTTP implementation, not yet certified against ChatGPT's hosted connection/OAuth handshake.** Callers need a way to send an Authorization bearer header. There are no persistent MCP sessions or SSE streams.

For a browser client sending an `Origin` header, the origin must appear in `POKER_ALLOWED_ORIGINS` (comma-separated); absent Origin is allowed if authorized. No unauthenticated solve requests are accepted. Limitations include no rate limiter across instances, no global compute timeout, and no production OAuth authorization server. Keep it private until the protection and compatibility checks are complete.

## Deploy to Render

`render.yaml` uses a **separate Python Web Service** on Render's Free tier, in Frankfurt, one Uvicorn worker, with `/health` health checks. It does **not** reuse the trip-planning engine deployment and does not require Supabase or PostgreSQL.

1. In Render, create a Blueprint from [this repository](https://github.com/eddieyang-97/poker-solver) and review `render.yaml`.
2. Set a long random `POKER_MCP_TOKEN` as a Render secret; **do not put it in git**. Verify `/health` and an authorized `/mcp` call. Deployment is intentionally manual (`autoDeployTrigger: off`).
3. **Before ChatGPT integration:** verify client transport and add OAuth 2.0 authorization/resource metadata if needed for the hosted private plugin. Use the patterns in [trip-planning-engine](https://github.com/eddieyang-97/trip-planning-engine), not its travel-specific database logic. The pre-existing private local poker plugin has not automatically been switched to this endpoint.

An authenticated HTTP endpoint is **not automatically a working hosted ChatGPT plugin**. That final connection and authorization work remains a separate milestone.

### Clone for development

```bash
git clone https://github.com/eddieyang-97/poker-solver.git
cd poker-solver
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Repo layout

```text
poker_spot/
  core.py             Range expansion, showdown evaluator, CFR+ river solving
  mcp_server.py       Local MCP stdio adapter and tool schemas
  http_server.py      Authenticated stateless HTTP MCP adapter
  __main__.py         Run example solve from a JSON file
tests/
  test_core.py        Hand ranks, pot odds, CFR smoke checks
  test_mcp.py         Stdio JSON-RPC handshake/tool calls
  test_http.py        HTTP auth, MCP calls, request bounds
.github/workflows/ci.yml
render.yaml
AGENTS.md
```

## Modeling conventions and limits

- Inputs are heads-up *river-node* ranges, not showdown hands alone; they can use `AA`, `AKs`, `KQo:0.4`, `AsJh`, and comma-separated combinations. Cards use `Ks`/`Th` notation.
- `solve_river`'s EV baseline is symmetric relative to splitting the already committed pot. Compare action EVs **at the same node**. NashConv reports exploitability only against strategies in this fixed tree.
- For `evaluate_river_call`, `pot` is before the bet and `bet` is the amount to call. Pot-odds threshold = `bet / (pot + 2*bet)`.
- Hosted solve limits: up to 1,500 iterations; up to 180 combos per range; up to 22,500 pair combinations as an upper bound; one solve at a time per process. These bounds reduce but do not eliminate denial-of-service/compute risks.
- Missing game-tree branches (raises) and range assumptions may distort recommendations even when CFR convergence is good.
- **Educational/post-session analysis only.** Do not rely on this tool for decisions during live real-money play.

## Next milestones

1. Keep GitHub Actions green (initial CI passed on the scaffold commit).
2. Deploy a private Render service and test authenticated remote MCP calls.
3. Integrate ChatGPT-compatible OAuth (or confirm a supported alternative) and validate real connector calls.
4. Benchmark several river spots against an independent solver and expand input-range diagnostics.
5. Evaluate adding turn/flop solving with an established engine behind the same MCP interface.

The GitHub repository is currently **public**. Keep deployment secrets out of git.

MIT licensed (see `LICENSE`).
