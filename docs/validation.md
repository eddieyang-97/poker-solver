# Audit and validation — 16 October 2026

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

**Still pending:** observable ChatGPT tool results and the conversational
£505 acceptance, refresh/revocation/reconnect checks, and replacing Auth0's Google
development keys for production SSO/federated logout. The SDK diagnostic does not
prove those behaviors. The user approved the diagnostic client's solver-only
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

### Actual ChatGPT attempt and current blocker

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

To close this gate, retry the prompt below in a fresh ChatGPT chat with **Poker
Solver Hosted** explicitly selected once reply rendering works, inspect both
tools' returned payloads, record the full range assumptions and compare the
results. No new paid plan, broader scope or solver credential is required for
that retry. Access tokens currently last one hour; refresh is not configured or
verified, so reauthorization may be required. Production Google login keys and
refresh/revocation/reconnect tests are separate follow-up work. The diagnostic
client grant remains available for retesting; it has not been revoked.

The connection/configuration commit `fab6fc0c61f29728e791e0915f14cc013315a38e`
also passed [GitHub Actions](https://github.com/eddieyang-97/poker-solver/actions/runs/38919280695). All 26 local tests, Ruff and compileall passed again
before that commit; the hosted Python implementation remains `a4ba8e7` because
the later changes affect documentation and plugin packaging only.

After connecting the hosted plugin, submit:

> Review a past heads-up river: BTN AsJh on Ks9s5hTdTs, £505 before river betting,
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
