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
