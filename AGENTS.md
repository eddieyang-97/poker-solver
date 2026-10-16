# Repository instructions

- Scope: HEADS-UP NLHE river-only constrained decision analysis. The engine is not a full GTO solver.
- Keep the core deterministic and dependency-light; separate game logic from MCP transports.
- Never invent equilibrium frequencies or quote action EVs without computed outputs.
- Results depend on caller-supplied river arrival ranges and simplified no-raise tree.
- Maintain tests for card removal, rank evaluation, pot odds and transport authorization.
- Bound resource use on hosted endpoints. Secrets are environment variables only.
- Do not enable publicly unauthenticated solve requests or publish user-supplied tokens.
- HTTP uses the official MCP SDK in stateless JSON-response mode. Keep OAuth issuer, exact resource audience, expiry, signature, scope and subject allowlist checks on every MCP request.
- The external OAuth provider owns authorization-code/PKCE, consent, refresh and client registration. Do not build a homegrown authorization server or reuse travel credentials.
- Static tokens are local development only (`POKER_MODE=local`); never allow that mode on Render.
- Hosted tool calls run in disposable processes: 20s wall/CPU budget, Linux 384 MiB address-space cap, no waiting compute queue, one worker, 30 calculations/minute process-wide. Keep range and payload bounds.
- `/health` is liveness; `/ready` checks configuration. A healthy process does not establish an authenticated ChatGPT integration.
- Before commits run `python -m ruff check poker_spot tests scripts`, `python -m compileall -q poker_spot scripts`, and `OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v` using the project virtual environment.
- Preserve the local plugin until the remote endpoint and OAuth connection work; package remote configuration separately. Preserve existing plugin identity, private audience, metadata and prompts.
- Root manifests are the local development package; `plugins/hosted/` tracks the published account overlay and verified ChatGPT app binding. Preserve both, and read current account source/release before future guarded updates. A package upload alone did not register callable web tools; the custom MCP connection is a separate dependency.
- Only Free Render/Auth0 resources are authorized. Do not upgrade plans or modify trip-planning-engine.
- Record actual evidence and unresolved gates in docs/validation.md; do not label SDK/ASGI tests as real ChatGPT or hosted OAuth acceptance.
- Educational/post-session use only; do not add live real-money in-hand assistance.
