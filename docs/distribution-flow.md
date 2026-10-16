# Distribution flow

Status: **design and pilot runbook**, not yet a validated friends/public launch. Last updated 16 October 2026. The owner completed Auth0 OAuth consent and hosted SDK calls, but ChatGPT conversational result rendering has not yet passed acceptance (see [validation](validation.md)).

## Goal and scope

A friend should be able to use the existing hosted solver from their own ChatGPT account without cloning this repo, installing Python, running a server, or joining the owner's private `poker-spot-study` plugin.

**Three distinct layers:**
1. The public GitHub source repository is readable but does not authorize solver use.
2. The **custom MCP connection** in each ChatGPT account points to the hosted endpoint; the owner's private `Poker Solver Hosted` entry is not automatically installed for friends.
3. Auth0 authenticates the person and issues a scoped bearer token; the poker server independently checks that token's issuer, exact audience, scope and allowlisted **user subject**. Successful login alone does not grant computation.

The initial distribution mechanism is **Add custom MCP server**. Do not require installing/distributing a plugin package for the friends-only pilot. Do not assume a private plugin page link is a public invitation or that MCP server URL knowledge grants access.

## Phase 1 — Friends-only beta (target: 2–3 friends)

### Friend-facing installation (after invitation is approved)

1. Open [ChatGPT Plugins](https://chatgpt.com/plugins).
2. Select **Add** (or +), then **Add custom MCP server** (formerly Create MCP App).
3. Enter the MCP endpoint:

   ```text
   https://poker-solver-vie0.onrender.com/mcp
   ```

4. Complete Auth0 authentication and consent for **Poker Solver ChatGPT** with only **`poker:solve`**. Do not grant unrelated access.
5. Select the connected MCP server in a new chat and test **`evaluate_river_call`** on an agreed, post-session sample. Check that the tool returns actual JSON/calculated values, not just a connection badge or AI-generated explanation.
6. If login succeeds but tool calls show **401 Unauthorized**, contact the maintainer to verify the Auth0 subject allowlist. If the ChatGPT reply fails to render, report it separately; an HTTP 200 request alone is not evidence of computation.

**OAuth client configuration fallback:** The current Auth0 tenant has **dynamic client registration disabled**. Simply pasting the endpoint may not be enough if ChatGPT's connection flow requires client details. The owner connected using the pre-registered **public Native client** documented in [hosting.md](hosting.md), with OAuth client ID `tpc_uZ1nakgLRZZ4t3ocxR6sUp`, token endpoint authentication **none**, scope **`poker:solve`**, resource `https://poker-solver-vie0.onrender.com/mcp`, and **OIDC off**. The redirect URI is ChatGPT's registered `https://chatgpt.com/connector_platform_oauth_redirect`. This is a *public client ID*, not a secret. UI fields may differ. Verify a second user's actual flow before sharing these steps as guaranteed plug-and-play instructions.

### Maintainer onboarding

1. **Preflight:** Check `/health` and `/ready` and verify a real authenticated MCP calculation from the owner's account. See [hosting](hosting.md) and [validation](validation.md). Do not invite friends while the conversational ChatGPT acceptance remains unresolved.
2. Invite one tester at a time. Ask them to complete the Auth0 sign-in. Obtain their exact verified Auth0 **`user_id`** from the Auth0 user management dashboard (or another controlled, verified identity workflow); do not infer it from their email address.
3. Add their user subject to the **comma-separated** Render secret `POKER_ALLOWED_SUBJECTS`, retaining the owner's subject and existing invitees. Do not commit identities, credentials or token values to GitHub.
4. Apply/redeploy the Render configuration, check `/ready`, and validate that the new friend can call both tools. Auth0 consent can be completed before allowlisting, but the solver must reject unauthorized users until their subject is added.
5. Record a minimal access register outside the public repo: invitee identity, verified subject, date, scope, approval, validation result, and revocation date. Do not collect/store their ChatGPT conversation or access tokens.
6. Test a **non-invited** account cannot solve even if OAuth login succeeds; test owner access still works after every allowlist change.
7. Give friend-facing usage instructions explaining that the tool is **post-session study only**, estimates only a restricted no-raise, no-rake, river-only game, and depends on explicitly supplied ranges.

### Revocation and troubleshooting

- To revoke use, remove the exact user subject from `POKER_ALLOWED_SUBJECTS` in Render and apply/redeploy. Verify authenticated tool calls are rejected. The server checks the allowlist on every request; deleting a ChatGPT connection alone is not the server-side control.
- Existing access tokens have up to approximately **one hour** lifetime; server-side allowlist removal denies them regardless of the token's remaining lifetime once the new config is active. Revoke the relevant Auth0 grant/refresh token as appropriate, and check user-initiated disconnect.
- Auth0 refresh, revocation/reconnect and second-user ChatGPT tests are **not yet accepted**. Google social login currently uses Auth0 development keys, so production SSO and federated logout are not yet ready. Do not tell testers these work until separately checked.
- On **401**, check token resource/audience, issuer, permission `poker:solve`, allowlisted `sub`, and consent. On **503**, check OAuth configuration/`/ready`. On compute timeout/busy, retry later; do not raise compute limits as a quick fix. On ChatGPT "response couldn't load", capture client error and verify *actual* tool payload independently before calling the test passed.

### Phase 1 acceptance checklist

- [ ] Owner ChatGPT conversation returns inspectable `evaluate_river_call` and `solve_river` payloads (not merely Auth0 consent / SDK diagnostic).
- [ ] Friend A connects from a separate ChatGPT + Auth0 identity and executes both tools.
- [ ] Friend B repeats onboarding with no cross-user access or credentials.
- [ ] Unlisted account is rejected; allowlist removal blocks a previously invited account.
- [ ] Disconnect/reconnect and token expiry/refresh behavior observed and documented, including any required reauthorization.
- [ ] Basic cold-start, concurrency, timeout and rate-limit behavior tested under a few simultaneous beta calls.
- [ ] Maintainer records the tested steps/screens and error cases; update this document from real evidence.

Service constraints: Free Render cold starts; one calculation in flight globally, **30 starts/minute** across all allowed users, 20-second worker timeout, 16 KiB request limit, and constrained CFR ranges/iterations. These controls are suitable only for a small invitation pilot, not open access.

## Phase 2 — Unlisted distribution (not implemented)

Target: users can install via a shared, unlisted app/connection entry without individual manual allowlisting. Confirm ChatGPT's actual sharing/install capability and applicable policies first; **unlisted-public installation is not established by our private plugin publication**.

Before launch: owner-approved onboarding or self-service authorization; per-user quotas and abuse safeguards; OAuth connection/refresh/revocation validation; production-ready sign-in; logging and operational recovery without leaking hands/tokens; capacity and cost assessment. Keep the protected MCP endpoint; do not remove OAuth/authorization to reduce onboarding friction.

## Phase 3 — Public distribution (not implemented)

Only if useful after a beta: confirm discovery/publication requirements; independent account onboarding, rate limiting and compute-budget enforcement; production SSO and support; legal/licensing and educational-use presentation; privacy/retention and security review; monitoring and incident handling; capacity plan beyond the single Free instance.

## Decisions and caveats

- Preferred pilot installation matches the observed ChatGPT/Robinhood pattern: **Plugins → Add → Add custom MCP server → endpoint → authenticate**. It is a proposed process for friends until a second account is actually tested.
- Keep the poker repository, Render service and Auth0 resource independent of `trip-planning-engine`.
- No code download, public plugin publication or additional service is required just to *attempt* a small friends pilot.
- Current private `Poker Solver Hosted` MCP connection and `poker-spot-study` are owner-only integrations. Never distribute the owner's credentials, tokens or private plugin source bundle as a substitute for individual OAuth login.
- The current MCP backend has no database and no durable per-user quotas. Multi-user usage shares the same single-process capacity limits.
- Any claim of "available to friends" requires second-user login plus actual callable tool results, not just a live `/health` endpoint.

Related: [hosting and OAuth setup](hosting.md), [validation evidence](validation.md), [README](../README.md).
