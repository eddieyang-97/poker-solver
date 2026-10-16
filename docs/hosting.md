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
An unconfigured deployment is intentionally reachable but refuses `/mcp` and
returns 503 on `/ready`. `/health` is process liveness and reports
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

## Update the existing private plugin

The existing personal plugin `poker-spot-study` is editable. Inspected release:
`pluginrel_6ad187c88ed48191a1c023d4863f3cce`, version 0.1.0. It uses local stdio.
Its root manifest includes author/developer metadata added during publication;
use the **current account source**, not the older repository manifest, for updates.

After hosted auth works, change that source's `mcp.json` server to:

```json
{
  "type": "streamable-http",
  "url": "https://YOUR-SERVICE.onrender.com/mcp",
  "extensions": {
    "com.openai": {
      "auth": {
        "type": "oauth",
        "client": {"mode": "cimd"},
        "baseScopes": ["poker:solve"]
      }
    }
  }
}
```

Bump root and existing compatibility manifest to 0.2.0, set local-executor
requirement false, and update the existing compatibility MCP config consistently.
Preserve the plugin ID, name, author/developer identity, skills, assets, private
audience and complete defaultPrompt values. Include the updated river-review
skill. Publish with the observed release ID, then read the source back. Do not
replace the working local plugin with an unconfigured endpoint. No new private
plugin is needed merely to change transport.

## Verify the connection

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
throttling. RS256/ES256 only; required issuer/audience/subject/iat/exp and scope.
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
