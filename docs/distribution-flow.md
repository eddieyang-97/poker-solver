# Distribution flow

Status: **design and pilot runbook**, not yet a validated friends/public launch. Last updated 16 October 2026. The owner completed Auth0 OAuth consent and hosted SDK calls, but ChatGPT conversational result rendering has not yet passed acceptance (see [validation](validation.md)).

## Goal and scope

A friend should be able to use the existing hosted solver from **their own ChatGPT or Claude account** without cloning this repo, installing Python, running a server, or joining the owner's private `poker-spot-study` plugin.

**Three distinct layers:**
1. The public GitHub source repository is readable but does not authorize solver use.
2. A **custom remote MCP connection** in each user's ChatGPT or Claude account points to the hosted endpoint. The owner's private ChatGPT `Poker Solver Hosted` entry does not automatically install for friends or transfer to Claude.
3. Auth0 authenticates the person and issues a scoped bearer token; the poker server independently checks that token's issuer, exact audience, scope and allowlisted **user subject**. Successful login alone does not grant computation.

The initial distribution mechanism is **Add custom MCP server** in ChatGPT or **Add custom connector** in Claude. Do not require installing/distributing a plugin package for the friends-only pilot. Do not assume a private plugin page link is a public invitation or that MCP server URL knowledge grants access.

## Phase 1 — Friends-only beta (target: 2–3 friends)

### ChatGPT: friend-facing installation (after invitation is approved)

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

### Claude: friend-facing installation (planned; not yet tested)

**Short instructions to send a friend (only after the maintainer registers a Claude OAuth client and approves their account):**

1. Open [Claude](https://claude.ai) → **Customize → Connectors**. On individual accounts, choose **+ Add → Add custom connector**. On Team/Enterprise, an organization owner/admin first adds **Custom → Web** under Organization settings → Connectors; members then connect it from Customize → Connectors.
2. Name the connector **Poker Solver** and enter:

   ```text
   https://poker-solver-vie0.onrender.com/mcp
   ```

3. Review the detected authentication settings, select **Sign in now** (or **Sign in when needed**), and **do not select No sign in**. For **OAuth client**, use the *separately registered Claude public OAuth client* provided by the maintainer under **Use your own OAuth client**; do **not** reuse the ChatGPT-only client ID. Do not enter an OAuth secret for a public PKCE client or share a bearer token in headers.
4. Complete Auth0 authentication and approve only **`poker:solve`** for the poker MCP resource.
5. In a Claude conversation, enable **Poker Solver** via **+ → Connectors**, then ask Claude to list the available tools and invoke **`evaluate_river_call`** with explicit sample inputs. Verify an actual calculated result rather than the assistant's narrative alone.
6. Report whether connector creation, OAuth consent, enablement, and tool execution succeeded independently. Send screenshots of errors **without tokens, authorization codes, or other credentials**.

**Important setup caveat:** Claude offers **Use Claude's published identity (Recommended)**, **Register automatically**, and **Use your own OAuth client**. Our Auth0 setup currently disables dynamic client registration; **Register automatically** should not be assumed to work. Whether Auth0 accepts Claude's published client metadata identity has **not** been proven here. The pragmatic pilot path is a separately pre-registered Claude OAuth **public client**, with exact redirect URI(s) confirmed from Claude's published metadata or actual connection flow. The reported Claude web redirect is `https://claude.ai/api/mcp/auth_callback` (some clients may use `claude.com`); **verify it rather than adding a guessed or wildcard callback**. The private ChatGPT OAuth client, with its ChatGPT-specific redirect, is not a substitute.

**Current status:** Claude has not completed an Auth0 authorization-code/PKCE flow or a live solver-tool call in this project. The step-by-step instructions are a test plan, **not** a claim that Claude is already supported. Free accounts may have a single-custom-connector limit; organization plans may restrict connector creation to admins.

Claude documentation: [Get started with custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) and [Use connectors to extend Claude](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities).

### Maintainer onboarding

1. **Preflight:** Check `/health` and `/ready` and verify a real authenticated MCP calculation from the owner's account. See [hosting](hosting.md) and [validation](validation.md). Do not claim either client is accepted until it returns inspectable computed results. For Claude, first register a separate public OAuth client in Auth0 with its **verified exact** Claude redirect, authorization-code + S256 PKCE, only `poker:solve`, and no client secret; keep ChatGPT's existing client unchanged.
2. Invite one tester at a time, specify **ChatGPT or Claude** as the test client, and ask them to complete the Auth0 sign-in. Obtain their exact verified Auth0 **`user_id`** from the Auth0 user management dashboard (or another controlled, verified identity workflow); do not infer it from their email address.
3. Add their user subject to the **comma-separated** Render secret `POKER_ALLOWED_SUBJECTS`, retaining the owner's subject and existing invitees. Do not commit identities, credentials or token values to GitHub.
4. Apply/redeploy the Render configuration, check `/ready`, and validate that the new friend can call **both tools in their chosen client**. Auth0 consent can be completed before allowlisting, but the solver must reject unauthorized users until their subject is added.
5. Record a minimal access register outside the public repo: invitee identity, verified subject, **client (ChatGPT/Claude)**, date, scope, approval, validation result, and revocation date. Do not collect/store their ChatGPT conversation or access tokens.
6. Test a **non-invited** account cannot solve even if OAuth login succeeds; test owner access still works after every allowlist change.
7. Give friend-facing usage instructions explaining that the tool is **post-session study only**, estimates only a restricted no-raise, no-rake, river-only game, and depends on explicitly supplied ranges.

### Revocation and troubleshooting

- To revoke use, remove the exact user subject from `POKER_ALLOWED_SUBJECTS` in Render and apply/redeploy. Verify authenticated tool calls are rejected. The server checks the allowlist on every request; deleting a ChatGPT connection alone is not the server-side control.
- Existing access tokens have up to approximately **one hour** lifetime; server-side allowlist removal denies them regardless of the token's remaining lifetime once the new config is active. Revoke the relevant Auth0 grant/refresh token as appropriate, and check user-initiated disconnect.
- Auth0 refresh, revocation/reconnect, second-user ChatGPT tests and **any Claude end-to-end test** are **not yet accepted**. Google social login currently uses Auth0 development keys, so production SSO and federated logout are not yet ready. Do not tell testers these work until separately checked.
- On **401**, check token resource/audience, issuer, permission `poker:solve`, allowlisted `sub`, and consent. On **503**, check OAuth configuration/`/ready`. On compute timeout/busy, retry later; do not raise compute limits as a quick fix. On ChatGPT "response couldn't load", capture client error and verify *actual* tool payload independently before calling the test passed.

### Phase 1 acceptance checklist

- [ ] Owner ChatGPT conversation returns inspectable `evaluate_river_call` and `solve_river` payloads (not merely Auth0 consent / SDK diagnostic).
- [ ] Friend A connects from a separate ChatGPT + Auth0 identity and executes both tools.
- [ ] Friend B repeats onboarding with no cross-user access or credentials.
- [ ] Claude-specific Auth0 public client registered with an independently verified callback (no reuse of the ChatGPT-only client).
- [ ] Claude connector creation → consent → enablement → both tool responses verified from a second account; record differences from ChatGPT.
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

- ChatGPT pilot installation matches the observed Robinhood pattern: **Plugins → Add → Add custom MCP server → endpoint → authenticate**. Claude pilot installation follows **Customize → Connectors → Add custom connector → endpoint → authenticate**. Both are proposed for friends until independently tested.
- Keep the poker repository, Render service and Auth0 resource independent of `trip-planning-engine`.
- No code download, public plugin publication or additional service is required just to *attempt* a small friends pilot.
- Current private `Poker Solver Hosted` MCP connection and `poker-spot-study` are owner-only integrations. Never distribute the owner's credentials, tokens or private plugin source bundle as a substitute for individual OAuth login.
- The current MCP backend has no database and no durable per-user quotas. Multi-user usage shares the same single-process capacity limits.
- Any claim of "available to friends" **on either platform** requires second-user login plus actual callable tool results on that platform, not just a live `/health` endpoint.

Related: [hosting and OAuth setup](hosting.md), [validation evidence](validation.md), [README](../README.md).
