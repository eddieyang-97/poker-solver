# CI-gated release preparation and activation

Status (22 October 2026): preparation merged; Issue #23 records owner-applied
`checksPass` activation, while automatic-release ordering and failed-CI
nondeployment acceptance remain open. Earlier off-state observations below are
historical. Follow [operations #23](https://github.com/eddieyang-97/poker-solver/issues/23)
for applied-state evidence. `AGENTS.md` remains authoritative for approvals.

Issue #28's [concurrent CI design and measurements](ci-throughput.md) retain
the exact required `test` check as a fail-closed aggregate of every numerical
and artifact job. No branch protection or Render setting is changed by that PR.

## Read-back baseline, not assumed platform state

GitHub `main` at `959af0c633b2a98775a751a08d98e62521145553` was **unprotected** (`protected:false`, no active rulesets), although the `test` workflow was green. The existing unconditionally running GitHub Actions job `test` covers Ruff, compilation, tests, the independent river and raise suites, turn resources and historical replay gates; some resource studies retain explicitly failed/time-out *subcases* and must not be misreported as hosted acceptance.

The actual Render account's **existing** `poker-solver` service (`main`, Frankfurt, Free, one Uvicorn worker) reported `autoDeployTrigger: off`. Its latest live **manual** deployment was commit `a4ba8e750582899642e468ba6c55d82bcc787d2f` from 16 October, not the latest `main`. Source `render.yaml` also says `off`. Neither a green repository test nor the YAML proves a newer version has reached Render. The Render connector's service read does **not** establish the Blueprint Auto Sync setting; inspect that in Render's Blueprint settings before any activation.


Subsequently, [PR #22](https://github.com/eddieyang-97/poker-solver/pull/22) merged on 22 October at `50f439b0b23b7bfa9693b9547266fc75c7469569`; the ops PR was updated to incorporate it without removing Issue #17's added `AGENTS.md` instructions. GitHub now reports `main` as `protected:true`, but this integration lacks read access to detailed protection rules (403), so strict CI, bypass and review settings still need independent verification. The new main CI was initially in progress. Render auto-deploy remains off.

**Do not change the active service or synchronize the Blueprint as part of this preparation PR.** Experimental turn/raise/range work merged to main is not thereby authorized for hosted MCP registration. No authorization/credentials or paid service change is included.

## Public read-only smoke (only after an approved deployment)

Once the deployment containing the new `/health` metadata is live, and an exact full SHA is authorized:

```sh
python scripts/smoke_release.py https://poker-solver-vie0.onrender.com FULL_APPROVED_40_CHARACTER_GIT_SHA
```

The command uses only unauthenticated GET `/health`, `/ready` and `/mcp`, with no redirects, a 60s timeout per request, bounded responses, and sanitized errors. It checks that the public `RENDER_GIT_COMMIT` matches the approved commit exactly, `engine=river-only`, `auth_configured=true`, readiness 200 and unauthenticated MCP 401 with OAuth resource metadata challenge. A sleeping Free instance may need time to wake; if the first GET times out, separately confirm startup before **one safe read-only retry**. Never retry a metered or mutation request as a generic smoke step.

A successful result **does not prove authenticated tool access or interactive ChatGPT consent**. With a separately authorized existing owner session/token, use `scripts/smoke_hosted.py` to exercise the two current tools, validate their outputs, and discard the token after use. That authenticated smoke includes computations and is deliberately not part of public CI. No new login, grant, plugin publishing, or live provider test is implied.

The health commit field is the Render-provided Git SHA, or `null` if absent/malformed in a local or old environment. It is *public source provenance*, not authenticated attestation. A prior deployment lacking the metadata fails the new exact-SHA smoke, as intended.

## Release checklist — owner-gated stages

1. **Protect `main`** with an applied GitHub ruleset requiring PRs, strict/up-to-date unconditional `test` check from GitHub Actions, resolved review threads, blocked force pushes/deletion and no bypass. Zero required formal approvals may suit a sole maintainer; explicit owner review remains standard. Independently read back `protected:true` and the actual rules. If admin permissions are unavailable, request the owner to apply them; do not claim YAML establishes protection.
2. **Hold automatic deploy OFF.** Confirm actual service settings, Blueprint Auto Sync and the old live SHA. Blueprint Auto Sync should be **No** so unreviewed config syncing cannot race green CI. Pausing Blueprint Auto Sync does **not** pause service-level code auto-deploy.
3. **Approve a controlled manual baseline release** of the exact reviewed SHA. Check main and head CI, build/start/Live, full deployed SHA, public exact-SHA smoke and a separately approved owner-authenticated safe read for both existing MCP tools. This is the first time the new health metadata can actually be verified on Render. Do not blindly assume an old deployment matches current source.
4. **Approve the separate activation change** from `autoDeployTrigger: "off"` to `autoDeployTrigger: checksPass` in `render.yaml`, only for the same existing Free service. After green main CI, manually sync the reviewed Blueprint change, read back service setting **After CI Checks Pass**, verify Blueprint Auto Sync still **No**, and check failure notifications. Never use `commit` as fallback and never expose a deploy-hook secret. If config changes must coincide with an app release, pause service auto-deploy *before* merging, then perform coordinated manual sync and re-verify.
5. **Harmless accepted merge proof:** compare full merged commit SHA, latest main `test` result and completion time with Render's *auto-deploy* event/start time, checked-out SHA and final Live state; repeat exact-SHA and authorized existing-tool smoke. If CI fails, skipped checks or other ambiguities require investigation; Render can treat neutral/skipped checks as passing, so required checks must not be conditional. A CI check must never depend on the Render deploy it gates.
6. **Failed-CI nondeployment:** obtain a separately permitted platform/non-production observation; do not intentionally break production main. Leave the checkbox open until proven. Document failure alerts/recovery without assuming a notification was delivered merely because configured.

## Pause and recovery

If unexpected code deploys or auth failures occur, set the existing service's **Auto Deploy = Off** in Render; reconcile `render.yaml` and any later Blueprint sync before resuming. Verify effective settings by read-back. If a release breaks compatibility, choose a known-tested exact SHA for a separately approved manual rollback or a forward fix; re-check Render startup, `/ready`, unauth MCP 401, both existing tools and the connected ChatGPT path. Re-deploying an older build does not undo any separately changed Auth0/provider configuration.

This service is stateless with disposable capped calculation workers; unlike trip planning it has no persistent booking database or supplier-journal workflow. Still, deploy/restart can interrupt an ongoing solver calculation, and Free-tier idle wakeups can disrupt the MCP connection. Do not claim uninterrupted work or silent OAuth reconnect.

**No automatic production settings change, merge, plan upgrade, Auth0 change, new hosted tool, paid infrastructure or plugin republishing is authorized by this runbook or its PR.**
