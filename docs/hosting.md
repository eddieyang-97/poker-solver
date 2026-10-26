# Hosted MCP and Auth0 setup

The Python solver remains independent. ChatGPT connects over HTTPS to `/mcp`;
the official MCP Python SDK handles Streamable HTTP, initialization and discovery.
Every MCP HTTP method requires a valid bearer access token. There is no database,
session store, custom UI, downstream API, or OpenAI API key requirement.

## Deploy the dedicated Free Render service

Use this repository's `render.yaml`, or create a Python Web Service with:

| Setting | Value |
| --- | --- |
| Repository / branch | `eddieyang-97/poker-solver` / `main` |
| Name / region / plan | `poker-solver` / Frankfurt / **Free** |
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn poker_spot.http_server:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health check | `/health` |
| Environment | `PYTHON_VERSION=3.12.8`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `POKER_MODE=hosted` |
| Auto deploy | Off |

Do not attach a disk or database, upgrade plans, or reuse the travel service.
An unconfigured deployment is intentionally reachable but refuses all computation
and returns 503 on `/ready`. With provider settings but no owner allowlist,
`/mcp` challenges with 401 so initial login can establish the owner's subject;
with no provider it returns 503. `/health` is process liveness and reports
`auth_configured`; it is not proof of usable tools or reachable signing keys.
Free services can sleep and share workspace free-instance hours; cold starts can
disrupt MCP connections. See [Render Free limits](https://render.com/docs/free).

## Configure Auth0 Free

The user selected Auth0 Free on 16 October 2026. An existing provider can host
both products if resources and permissions remain separate. This setup uses a
dedicated poker configuration and makes **no changes to trip-planning-engine**.
Never use a travel token, database password, management credential or signing key
for this solver.

1. Sign in/create an Auth0 Free account. The owner enters passwords and accepts
   signup terms. Keep the provider's standard domain; do not select paid features.
2. In Applications → APIs create **Poker Solver**, identifier equal to the exact
   deployed `https://YOUR-SERVICE.onrender.com/mcp`, using RS256. Add permission
   `poker:solve` with description “Run bounded river study calculations”. Set the
   access-token lifetime to 3600 seconds or less.
3. In tenant Settings → Advanced, enable **Resource Parameter Compatibility
   Profile** and **Include Issuer in Authorization Responses**. Verify discovery
   advertises S256 PKCE and the actual supported client registration method.
   ChatGPT sends `resource`; do not silently accept a userinfo/ID token when the
   requested poker audience is missing.
4. Register the **exact ChatGPT client metadata URL shown by the MCP connection**
   through Applications → Applications → Create Application → Import from URL.
   Preview its identity, redirect URIs, scopes and public token authentication
   (`none` with PKCE); only then approve registration. Use its actual stable or
   callback-specific URL rather than guessing a callback. Auth0 documents manual
   CIMD registration. A regular supplied client with exact registered callbacks
   is an alternative if CIMD is unavailable. Do not use client-credentials grants.
5. Enable the intended login connection for that client. If Auth0 requires a
   domain-level connection for third-party apps, review that access expansion
   before enabling it. Do not enable arbitrary DCR or broaden unrelated clients.
6. Establish the owner's Auth0 identity and copy its exact **user_id** into
   `POKER_ALLOWED_SUBJECTS` in Render. Keep that identifier out of public docs.
   A private plugin alone does not make the HTTP service private; this allowlist
   also rejects other users with otherwise valid tokens.
7. Set the remaining Render environment variables using the tenant's verified
   discovery document: `POKER_RESOURCE`, `POKER_OAUTH_ISSUER` (including its exact
   trailing slash), `POKER_OAUTH_JWKS_URL`. These URLs are configuration, not
   credentials. No Auth0 client secret or private signing key belongs in Render.
8. Redeploy. Confirm `/ready` is 200, unauthenticated `/mcp` is 401 with a
   `WWW-Authenticate` resource-metadata challenge, and the metadata names the
   intended issuer, exact audience and `poker:solve` scope.

Auth0 owns sign-in, consent, authorization code replay protection, S256 PKCE,
refresh and client registration. This repository implements the resource server,
not those provider endpoints. The actual provider flow must still be verified.

Sources: [Auth0 MCP](https://auth0.com/ai/docs/mcp/overview),
[resource parameter settings](https://auth0.com/ai/docs/mcp/get-started/call-your-apis-on-users-behalf),
[CIMD registration](https://auth0.com/docs/get-started/auth0-overview/create-applications/register-applications-with-cimd),
[Auth0 pricing](https://auth0.com/pricing),
[OpenAI authentication](https://developers.openai.com/plugins/build/auth).
The OBO/downstream API portions of Auth0's example are not needed here.

## Claude public OAuth client (26 October 2026 preflight)

Registered with owner approval on 26 October 2026, separately from the unchanged
**Poker Solver ChatGPT** client:

| Public setting | Saved configuration |
| --- | --- |
| Application | **Poker Solver Claude**, third-party strict, Native/public |
| Client ID | `tpc_7RwSTacTTJwxRBUAPgZWEV` |
| Grant | Authorization Code only; Refresh Token off; Client Credentials unavailable |
| API | Existing **Poker Solver**, delegated `poker:solve` (1/1), no anonymous access |
| Login | Existing domain-level `google-oauth2`; database connection disabled |
| Client secret | Leave blank in Claude; public-client token authentication `none` |

Saved callback (read back after leaving and reopening Settings):

```text
https://claude.ai/api/mcp/auth_callback
```

This callback is confirmed by [Anthropic's authentication documentation](https://claude.com/docs/connectors/building/authentication#callback-urls).
Do not add speculative `claude.com`, wildcard or diagnostic loopback callbacks.
Claude Code's local callback is a separate setup outside this onboarding flow.
Retain consent, the existing Poker Solver API audience
`https://poker-solver-vie0.onrender.com/mcp` and delegated permission `poker:solve`.
The existing domain-level Google connection was already available; no connection
promotion was needed. No client secret was revealed, copied or supplied. Auth0's
Native/public grant controls identify token authentication as `none`; an actual
Claude code exchange has not yet verified this integration boundary.

Browser-read public discovery on 26 October confirmed issuer
`https://dev-p1mh4uh1le8zh2am.us.auth0.com/`, authorization endpoint `/authorize`,
token endpoint `/oauth/token`, S256 support and token authentication `none`.
It advertises neither `registration_endpoint` nor
`client_id_metadata_document_supported`. Use **Use your own OAuth client** in
Claude, rather than automatic registration or its published identity. Leave
the secret blank. The [custom connector guide](https://claude.com/docs/connectors/custom/add-unlisted#choose-authentication-settings)
documents both the two-step dialog and the older **Advanced settings** layout.

Auth0 advertises `offline_access`; Claude may append it to the requested scope.
Refresh issuance and rotation have not been configured or tested for this client.
Authorization code only is enabled; expect explicit reconnect after expiry;
do not enable API offline access or alter the working ChatGPT client merely to
make this onboarding pass. If refresh is subsequently enabled, use rotating,
expiring refresh tokens and independently verify reconnect/revocation behavior.

Live metadata confirmed the exact resource and only `poker:solve`. `/ready`
reported ready; `/health` reported `turn-pilot-v1` at commit
`920d2bf2c54226caf16c8572bb531a9b2a91a489`. These are configuration/liveness
observations, not authenticated Claude acceptance. No deployment settings were
changed. See [distribution flow](distribution-flow.md) for individual identities,
allowlisting and actual river-tool acceptance requirements.

A manual authorization preflight with this client, exact callback/resource,
`poker:solve` and S256 reached **Log in | Poker Solver Claude** with Google
sign-in. It stopped before login/consent and used no token exchange; it was not
initiated by Claude and proves no authenticated tool execution. In the signed-in
Claude account, **Add custom connector** was disabled and an existing custom
**Trip Planning** connector was connected. No connector was removed or modified.
Use an eligible account with an available custom-connector slot for acceptance;
do not change the travel integration or upgrade plans as part of this setup.

## Update the existing private plugin

The existing private personal plugin `poker-spot-study` was updated in place to
0.2.1, release `pluginrel_6ad2397100c88191b12f471d1fc68503`, on 16 October 2026.
[Open the plugin](https://chatgpt.com/plugins/plugins_6ad187c711c081919843668ed33c8a8d).
Its hosted source was read back after publication; identity and private audience
were preserved. Repository-root manifests remain the local development package.
The published overlay is tracked in `plugins/hosted/`; omitted legacy account
source files are preserved by Plugin Creator updates.
Its root manifest includes author/developer metadata added during publication;
use the **current account source**, not the older repository manifest, for updates.

The published `mcp.json` server uses:

```json
{
  "type": "streamable-http",
  "url": "https://poker-solver-vie0.onrender.com/mcp",
  "extensions": {
    "com.openai": {
      "auth": {
        "type": "oauth",
        "client": {
          "mode": "provided",
          "clientId": "tpc_uZ1nakgLRZZ4t3ocxR6sUp",
          "tokenEndpointAuthMethod": "none"
        },
        "baseScopes": ["poker:solve"],
        "resource": "https://poker-solver-vie0.onrender.com/mcp"
      }
    }
  }
}
```

The dedicated Auth0 tenant is `dev-p1mh4uh1le8zh2am.us.auth0.com`. The registered
third-party Native public client is **Poker Solver ChatGPT**, with exact callback
`https://chatgpt.com/connector_platform_oauth_redirect` verified from ChatGPT's
public client metadata. Only user-delegated `poker:solve` is granted. Dynamic
registration remains disabled. The owner approved promoting the Google basic
profile/email login connection to domain level for third-party sign-in.
Auth0 development Google keys remain a pilot limitation; use owner-managed
Google credentials before claiming production SSO/federated-logout readiness.

Uploading remote MCP configuration made it visible on the plugin detail page,
but did not expose callable tools in the first web chat. The working web path
required Plugins → Add → Add custom MCP server, using the same endpoint and
provided public client above. OAuth discovery correctly found the issuer,
resource, callback and `poker:solve`; set base/default scope to `poker:solve`,
token authentication to `none`, and OIDC off (no profile/email/offline scope is
needed by the solver). Sign-in reached the named Auth0 client consent and
returned to ChatGPT with a connected notification.

The resulting private connection is
[Poker Solver Hosted](https://chatgpt.com/plugins/plugin_asdk_app_6ad238f3cce881919faa6ecfcd1faee0).
Its verified app ID `asdk_app_6ad238f3cce881919faa6ecfcd1faee0` is bound through
`.app.json` in the existing `poker-spot-study` 0.2.1 package. This preserves the
original workflow identity while providing ChatGPT's registered connection.
The hosted app and package are private; the HTTP owner allowlist is still enforced.

For future updates, bump root and existing compatibility manifests, set local-executor
requirement false, and update the existing compatibility MCP config consistently.
Preserve the plugin ID, name, author/developer identity, skills, assets, private
audience and complete defaultPrompt values. Include the updated river-review
skill. Publish with the observed release ID, then read the source back. Do not
replace the working local plugin with an unconfigured endpoint. No new private
plugin is needed merely to change transport.

## Verify the connection

For the first owner's identity, register a dedicated Native public diagnostic
client with token endpoint auth `none`, authorization-code grant, and only
`http://127.0.0.1:8733/callback` as its callback. Grant it only user-delegated
`poker:solve`. With `POKER_RESOURCE`, `POKER_OAUTH_ISSUER` and its public
`POKER_OAUTH_CLIENT_ID` in the shell, run `python scripts/acceptance_oauth.py`.
Open its authorization URL, verify the named client and consent, and sign in.
The official SDK handles discovery, S256 PKCE, state and token exchange. The
helper independently verifies the token and saves only the owner subject in
ignored `.data/acceptance-owner-subject`. Set that subject privately in Render
and redeploy; the helper then exercises both hosted tools. No password, token,
authorization code, verifier or client secret is saved or printed. Its loopback
listener expires; it is a diagnostic, not a production authorization server.
It does not request refresh tokens. Revoke its test grant after acceptance.

1. Connect the hosted server in ChatGPT with OAuth. Verify the consent names the
   intended poker resource and only `poker:solve`, then complete sign-in/consent.
2. In a fresh chat select the plugin and submit the acceptance prompt in
   [validation.md](validation.md). Inspect actual tool arguments and returned
   calculation output; an assistant's narrative alone is insufficient.
3. Optionally run `python scripts/smoke_hosted.py` with `POKER_RESOURCE` and a
   short-lived `POKER_ACCEPTANCE_TOKEN` in the process environment. It uses the
   official SDK, never prints the token, and calls both tools. Clear that variable
   afterwards. This smoke test does not prove interactive OAuth or ChatGPT use.
4. Verify expired, wrong-audience, wrong-user, wrong-scope and unsigned tokens
   fail. Remove the owner's allowlist entry and redeploy to verify access removal;
   reconnect only after explicitly restoring authorized access.

JWT signature keys are fetched only from the configured HTTPS JWKS URL, bounded
to 64 KiB and a five-second timeout, cached for five minutes with rotation retry
throttling. RS256/ES256 only; required issuer/audience/subject/iat/exp and scope,
with a bounded 30-second clock-skew allowance. The first real diagnostic token
exposed a roughly two-second difference between the Windows and provider clocks.
There is no server-side token revocation database: provider logout does not
invalidate an already issued token before expiry. Use short lifetimes, revoke
refresh grants in Auth0, and remove an allowlisted subject for emergency denial.

The service admits one calculation at a time and 30 starts/minute across all
authorized users in its single process, with no waiting compute queue. Processes
are killed after 20 seconds; Linux additionally caps CPU at 20 seconds and address
space at 384 MiB. JSON body limit: 16 KiB. CFR limits: 1500 iterations, 180 combos
per side, 22500 Cartesian pairs, three sizes. These are private-pilot controls,
not distributed abuse protection. Do not increase Uvicorn worker count without
redesigning admission limits. Public/wider distribution needs further operational
review. Tool errors have `isError: true` and `structuredContent.error.code`.

### Free-instance startup and reconnect

The private owner connection has returned both tool payloads successfully after
an explicit reconnect; see [the direct acceptance evidence](validation.md#direct-authenticated-connector-acceptance-after-reconnect).
It also returned a 20-second network timeout while the Free Render instance was
starting. A manual public `/health` request took about 29 seconds; authenticated
tool calls worked afterwards. When a request times out after idle, allow the
instance to start and retry once. A successful health response alone proves no
tool execution or OAuth acceptance. No periodic keepalive or paid upgrade is
configured.

If the connector explicitly reports `requires reauthentication`, reconnect
**Poker Solver Hosted** in the signed-in ChatGPT account and retry. Accepted
authentication prompts alone did not establish recovery in this session; the
owner's reconnect followed by successful tool results did. Automatic token
refresh remains unconfigured/unverified, so the one-hour access-token lifetime
can require another explicit sign-in. Keep that limitation visible until refresh,
revocation and repeat reconnect tests are completed.
