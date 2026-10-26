# Production releases and recovery

This is the **current operational runbook**, not the initial rollout diary. [Issue #23](https://github.com/eddieyang-97/poker-solver/issues/23) and [PRs #24/#27](https://github.com/eddieyang-97/poker-solver/pull/27) contain historical activation decisions and evidence. `AGENTS.md` governs owner authorization and solver/tool boundaries.

## Applied topology and invariants

- Existing dedicated **Free Render** `poker-solver` service (Frankfurt, single worker) plus **Auth0 Free**. The owner confirmed **no Render Blueprint** governs the service; `render.yaml`'s example `autoDeployTrigger: off` must not be mistaken for the **applied service setting**.
- Owner-applied Render **After CI Checks Pass**, effective `autoDeployTrigger: checksPass`, was independently read back on **22 October 2026**. GitHub reported protected `main`, though fine-grained rules were not available through the connected API (403). Check applied settings again before consequential releases; recorded read-back is not a perpetual guarantee.
- The required GitHub Actions **`test`** context must be an unconditional fail-closed aggregate of numerical, reference and artifact jobs; path/neutral/skipped shortcuts must not release code. [CI contract](ci-throughput.md). A green PR/head alone is not the merged-main test or Render deployment.
- Ordinary owner-reviewed protected-`main` changes to **already-approved hosted-compatible code** may follow the CI-gated policy. **New tools, enabled experimental factories, Auth0/allowlist/security changes, additional users, worker limits, plugin distribution, paid plans and infrastructure** require separate owner approval. A docs PR does not authorize those changes.

## Approved standard release checks

1. **Before merge:** inspect the exact PR diff, risk, numerical/fixture/benchmark receipts and **current head** required `test`; resolve material review findings. Confirm expected deployed tool/factory surface, source SHA, owner authorization and the effect of an ongoing calculation's interruption.
2. **After owner-approved merge:** verify unconditional required `main` CI for the **merged commit**. Compare its finish time against Render's automatic-deploy event/start time (must be **after** green CI), exact checked-out commit, startup/Live state and configured effective release policy. If CI was skipped/neutral, no auto event exists or the ordering is wrong, classify the release as **unverified** and investigate; do not infer it succeeded from a passing badge.
3. **Public, read-only river-app smoke:** for a known-approved 40-character SHA on the standard river-only deployment, run:
   
   ```sh
   python scripts/smoke_release.py https://poker-solver-vie0.onrender.com FULL_APPROVED_40_CHARACTER_GIT_SHA
   ```
   
   This performs bounded unauthenticated GET checks against `/health` (exact SHA, reported `river-only` engine), `/ready` (configured) and `/mcp` (401 plus the expected OAuth resource challenge). It does **not** perform an authenticated tool call or prove client compatibility. A Render-provided SHA header/field is public provenance, not cryptographic attestation. A Free-tier cold start may need a separate check and **at most one read-only retry**.
4. **Owner-approved authenticated smoke:** use `scripts/smoke_hosted.py` with an existing owner session/token to call the two authorized river tools and verify **returned numerical values**, then discard credentials. Never do authenticated calculations as part of public CI or publish the token. A new-user OAuth signup, refresh/revocation, Claude connection or permission change is **not** implied.
5. **Experimental turn factory:** if a separately approved release uses `create_hosted_turn_pilot_app`, `/health` may report `turn-pilot-v1` rather than `river-only`; do **not** relabel an incompatible river smoke as a passing turn pilot. Use [Stage B acceptance](turn-pilot-release.md) with real Linux/Render/ChatGPT resource/latency/numerical gates and the same explicit owner scope. Stage B's pinned-game latency/headroom was observed **failing** even after the computation succeeded; [measurements](turn-hosted-timeout.md).

### What remains unverified

Exact completed deployment evidence is release- and revision-specific. The initial [manual baseline and CI-gate activation](https://github.com/eddieyang-97/poker-solver/issues/23) are recorded historically; a successful future auto-release should have its own merged SHA/CI/Render/Live receipts. **Failed-CI nondeployment** must be demonstrated with safe permitted provider/nonproduction evidence, **not** by deliberately breaking protected production `main`. Do not claim the negative case was tested if it was not.

## Pause and recover

- If unexpected deploys, mismatched SHA, incomplete CI or auth failures appear, **stop new changes**; with explicit authorization set the existing Render service **Auto Deploy = Off** and verify the effective value. Determine which factory/tool, code SHA and Auth0 audience/allowlist the service actually runs. Reconcile `render.yaml` separately if ever adopting Blueprint management.
- For a compatibility break, owner-approve either a tested exact-SHA manual rollback or a forward repair; recheck startup, readiness, unauthenticated denial, authorized existing tool output and appropriate connected-client usage. Do not assume reverting code restores prior external Auth0 settings, user permissions or plugin bindings.
- Workers are stateless and disposable; a deploy or idle wakeup may interrupt ongoing calculations. Never claim seamless reconnect or retry a paid/mutating external action generically; this project does not have a trip/booking database, but user-facing timeouts still require honest outcome reporting.

Latest historical exact-SHA, manual baseline and setting activation receipts: [Issue #23](https://github.com/eddieyang-97/poker-solver/issues/23), [PR #27](https://github.com/eddieyang-97/poker-solver/pull/27) and the [frozen original release record](https://github.com/eddieyang-97/poker-solver/blob/920d2bf2c54226caf16c8572bb531a9b2a91a489/docs/releases.md). This runbook does not authorize changing production or paid infrastructure by itself.
