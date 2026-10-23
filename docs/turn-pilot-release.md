# Turn MCP pilot — release decision, not authorization

**Stage A only. Production no-go pending the gates below.** Tracks #26, following
owner-merged #21/PR #30. Chosen design is bounded live-only; #25 catalog packaging,
cold/warm cache hits and cache miss fallback do not apply. No cache ships.

The local prototype supports at most two concrete combos/player, one size/street,
2000 iterations, exact cent money and four output views. Caller ranges remain
assumptions. This is not a realistic full-width turn solver or GTO service.
Repeated original 24-combo timeouts remain disqualifying for broader release;
faster subsequent samples do not erase them. [Contract](turn-pilot.md).

## Evidence required before owner release decision

- Reviewed PR head, exact accepted merge SHA and latest **main** `test` CI with
  all required jobs/eleven artifacts. PR CI does not establish deployed state.
- Retain isolated actual Linux 20s CPU/wall, 384 MiB AS, admission/rate/body/output
  negatives, worker cleanup/recovery and convergence failure behavior. Candidate
  repeated samples additionally need observed <=10s wall/CPU and <=192 MiB AS
  headroom. This remains sample evidence, not a universal capacity guarantee.
- Independently verify applied existing Free Render service/capacity, one worker,
  current SHA, `checksPass` release infrastructure and cold-start behavior.
  #23's harmless successful CI→deploy proof is recorded in its issue; failed-CI
  nondeployment/platform semantics remain a separate known verification gap.
- **Explicit owner authorization for this new tool.** The current Render guard
  intentionally forbids activation. Prepare a separate reviewed activation
  change/startup choice only after that approval. Do not turn a routine approved
  merge into automatic production registration through an environment toggle.
- Use only existing private owner auth/connection and Free resources. No OAuth
  issuer/audience/scope/allowlist change, new account, extra grant, plugin publish,
  plan upgrade, keepalive or credential sharing is implied. If any is actually
  necessary, prepare exact changes and obtain separate owner approval.

## Separately approved hosted acceptance

| Boundary | Required actual evidence |
| --- | --- |
| Release | Exact deployed SHA, readiness and existing two-tool output regressions |
| Security | Missing/wrong signature/issuer/audience/scope/subject/expired token denied; no computations/admission on denial; unchanged provider permissions |
| Capacity | Real Render startup/import/parse/solve/BR/serialization/exit, repeated cold/warm runs, one shared slot, busy/rate/timeout/recovery and body/output bounds |
| Client | Actual owner ChatGPT invocation, exact request and raw result/source/diagnostics, future-view semantics, unsupported and insufficient-convergence results |
| Availability | Free idle wakeups versus connector deadlines; reconnect behavior, residual refresh/revocation acceptance gaps explicitly recorded |
| Provenance | Version, full game/source/request/result hashes, convergence and reached/zero-reach rows retained without tokens/subjects/secrets |

An artificial pre-solved demo, localhost SDK roundtrip, passing resource study,
`/health` or backend deployment is insufficient for ChatGPT acceptance. There is
no actual hosted turn evidence yet. Four synthetic questions establish examples,
not organic demand or broad usefulness. Stop if this tiny product isn't useful.

## Abort / rollback

Before any approved activation, pin a reviewed prior river-only release SHA and
record current service start command/tool list. Abort if tool list/auth changes
unexpectedly, source receipts mismatch, root gate fails while strategy is shown,
outputs exceed bounds, or worker/time/cold-start behavior violates acceptance.
Disable the pilot and restore the existing river-only `poker_spot.http_server:app`
entry point, or deploy the separately approved known-good prior SHA. If release
ordering is suspect, pause automatic deploys under owner control and investigate.
Re-verify exact SHA, `/ready`, unauthenticated denial and both existing tools;
do not alter Auth0 or widen budgets as a latency fix. No database migration or
persistent user data is introduced, so rollback has no data-migration step.

Do not merge, deploy, register/publish tools, change production configuration or
claim Stage B acceptance from this document. Owner release approval is pending.
