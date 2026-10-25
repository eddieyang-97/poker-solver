# Turn MCP pilot — Stage B activation and acceptance

**Activated, but Stage B acceptance failed.** PR #33 is owner-merged and Live at
`39e979c6bc0fd0b9cdcb10d5a5f3f9cdb7226e4f`. Two authenticated pinned-game calls
now compute with verified receipts, but take 17.6–18.1s client / about 17.0s
parent wall: both fail the unchanged 15s client and 10s headroom gates.
Both legacy river tools pass their exact baseline checks. Earlier PR #32 worker
and startup-related connector timeouts remain recorded.
See [the investigation, candidate changes and no-go decision](turn-hosted-timeout.md).
Production settings are unchanged by that investigation; disabling the pilot or
deploying its candidate requires separate owner approval. Keep #26 open.

The following preparation history tracks #26, following merged PR #31 / main
`d0eb8699a7c7924cbbc3b2a562bb1a8554a231a9`. Chosen design is bounded live-only; #25 catalog packaging,
cold/warm cache hits and cache miss fallback do not apply. No cache ships.

The local prototype supports at most two concrete combos/player, one size/street,
2000 iterations, exact cent money and four output views. Caller ranges remain
assumptions. This is not a realistic full-width turn solver or GTO service.
Repeated original 24-combo timeouts remain disqualifying for broader release;
faster subsequent samples do not erase them. [Contract](turn-pilot.md).

## Evidence required before owner release decision

The owner explicitly authorized Stage B on 23 October 2026, after reporting PR
#31 merged/deployed. Independent readback confirms that river-only baseline:

- Main [CI 39984504602](https://github.com/eddieyang-97/poker-solver/actions/runs/39984504602)
  passed all five jobs and retained eleven artifact groups at exact `d0eb869`.
  Measured critical path: 324s; estimated runner time: 15 minutes, not billing.
- Existing Free Frankfurt service `srv-db934j67bikc73bppelg`, one instance and
  one Uvicorn worker, branch `main`, `autoDeployTrigger=checksPass`.
  Deploy `dep-dbdogaflot8c738sol00` became live at 16:16:39 UTC on that SHA.
- Public exact-SHA smoke: `/health` 200, `/ready` 200, unauthenticated `/mcp` 401,
  engine `river-only`. An earlier health request was unavailable; a subsequent
  probe passed. This is not a measured idle cold-start result or latency guarantee.
- Render metrics report a 0.15 CPU limit and approximately 512 MiB service
  memory. Worker AS cap remains 384 MiB; total parent/service memory and actual
  shared CPU wall time need hosted measurements, not inference from CI.
- Both existing ChatGPT connector tools computed fresh baseline requests.
  `evaluate_river_call`: KdQd versus AsJh on Ks9s5hTdTs, pot £505, bet £450,
  call-minus-fold £955. `solve_river`: £100 pot/stack, KhKd versus AsAd,QhJd
  on 2c3d4h8s9c, pot bet, 1500 iterations: root OOP EV -£25.0001, NashConv
  0.037% pot. The call tool first requested reauthentication, accepted it, and
  computed on retry. This is not refresh/revocation lifecycle proof.

These observations do not activate a turn tool. No live settings, Auth0 or
published plugin metadata have changed in this activation PR.

Stage A source `a9ade24` passed Linux [CI 39936495563](https://github.com/eddieyang-97/poker-solver/actions/runs/39936495563):
164/164 tests, all five jobs, eleven artifacts; eight measured worker samples
meet conservative headroom and bounded-output gates. Sources, result hashes
and all 10 strategic + 188 river reference digests verify. These are **local
release-preparation results only**; [receipts](turn-pilot-results.json) preserve
the original two maximum-workload timeouts and known policy variance.

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
- **Explicit owner authorization for this new tool is recorded above.** Review
  and owner merge of the activation code remain required. The default app and
  local Render guard remain unchanged; no environment toggle activates a new
  hosted tool. Select only the explicit hosted factory described below.
- Use only existing private owner auth/connection and Free resources. No OAuth
  issuer/audience/scope/allowlist change, new account, extra grant, plugin publish,
  plan upgrade, keepalive or credential sharing is implied. If any is actually
  necessary, prepare exact changes and obtain separate owner approval.

## Activation sequence

1. Review the activation PR, observe latest-head required `test` success and all
   eleven artifacts, then let the owner merge. Verify exact new main CI/live SHA.
   A normal merge still deploys the river-only default entry point.
2. Change only the existing service's start command to:

   ```sh
   uvicorn poker_spot.http_server:create_hosted_turn_pilot_app --factory --host 0.0.0.0 --port $PORT --workers 1
   ```

   Preserve all environment/auth values, Free plan, one instance, body/rate/worker
   limits and `checksPass`. The factory fails outside Render Linux,
   `POKER_MODE=hosted` or configured owner OAuth. Default HTTP/stdio remain two
   river tools. `render.yaml` remains an unapplied river-only baseline; no
   Blueprint manages this service. Available Render MCP has no start-command
   update operation; use the authenticated Dashboard or supported API and read
   back the resulting command/deploy. Never paste a Render API key into chat.
3. Observe `live`; run the public smoke against the exact new main SHA:

   ```sh
   python scripts/smoke_release.py https://poker-solver-vie0.onrender.com FULL_MAIN_SHA --engine turn-pilot-v1
   ```

4. Run the SDK harness from the pinned release checkout. Supply an OAuth access
   token only through the existing secure environment mechanism:

   ```sh
   python scripts/acceptance_turn_pilot.py --url https://poker-solver-vie0.onrender.com/mcp --expected-sha FULL_MAIN_SHA --output .artifacts/turn-pilot-hosted-sdk.json
   ```

   It retains exact requests/raw SDK results, source/runtime/game/result receipts,
   stage timings, two example runs, unsupported iteration rejection and both
   river smokes. Failed provenance, root convergence, 20s/384 MiB budget, 64 KiB
   SDK engineering bound or observed 10s/192 MiB headroom abort acceptance.
   Every admitted example must also deliver its decoded SDK response within
   **15 seconds client wall time**, including network, scheduling and MCP/SDK
   handling. This warm engineering target allocates 10s for the existing worker
   headroom plus 5s for transport/delivery; it is not a verified ChatGPT deadline.
   It does not replace the separate worker 20s hard budget or 10s headroom gate.
   Slow computed responses are retained with a latency failure, not passed or
   relabeled as failed computation.
   SDK evidence is separate; no timeout or insufficient-convergence observation
   is manufactured if these admitted examples converge.
5. Refresh the existing private ChatGPT connection's tools and invoke
   `solve_turn_v1` with [the exact example](../examples/turn-pilot.json). Retain
   actual raw requests/results including provenance and execution. Reconnect if
   needed, repeat the request and both river tools. No new Auth0 permission or
   plugin publish is required by this server change; if client behavior requires
   either, prepare that separately for approval.
6. Measure a real idle wakeup separately from consecutive warm calls; inspect
   service memory/CPU/errors and complete the matrix below. Label local/CI
   timeout/claim-tampering evidence honestly where no safe real hosted case exists;
   leave corresponding hosted gates open. Never add production fault hooks,
   flood the shared rate limit or weaken authentication to manufacture evidence.

The harness's admitted example calls are **warm**: public health/readiness,
initialization and discovery precede them, including the first example. Its first
public-probe duration is recorded as unclassified priming time, not evidence of
an idle wakeup. A true cold test needs an independently established idle interval
and Render event/log evidence, then timing of the first unprimed request. Report
that separately; do not apply the warm target or label a primed tool call cold.

Legacy smoke requests are now the **exact two recorded requests** in
[the baseline](turn-pilot-stage-b-baseline.json), whose LF SHA is retained in
each SDK report. The earlier £100 mixed-range indifference call is a different
request and is not compared with the recorded £505 single-combo call. The
complete schemas, board/hands, money/tree, iterations and node/action maps must
match; own reach must follow the returned policy. Deterministic call quantities, including rounded odds, equity
and EV, require exact equality. The polarized river fixture retains its existing
0.04 absolute frequency gate and <0.5%-pot convergence gate; root EV is checked
against the baseline's combined-gap bound and the analytical -£25 equilibrium.
Conditional action EVs are checked through terminal chip ledgers, rounded-policy
identities and an interval for the unqueried AA policy. No exact cross-runtime
frequencies or blanket conditional-EV precision is inferred from root NashConv.
These specialized checks apply to this pinned pedagogical fixture only.

`validate_turn_result()` also checks captured structured ChatGPT results against
the pinned release sources. Receipts prove consistency, not signed execution
attestation or independent correctness of range assumptions/low-reach EVs.

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
now actual computed pinned-game results as well as earlier failures, but the
latency/headroom gates still fail. Four synthetic questions establish examples,
not organic demand or broad usefulness. Stop if this tiny product isn't useful.

## Abort / rollback

With owner approval, restore the default entry point using the current reviewed
code (`39e979c6bc0fd0b9cdcb10d5a5f3f9cdb7226e4f` at this retest). This removes
the opt-in turn registration without depending on an old retained build:
`uvicorn poker_spot.http_server:app --host 0.0.0.0 --port $PORT --workers 1`.
Two tools: `solve_river`, `evaluate_river_call`. Abort if tool list/auth changes
unexpectedly, source receipts mismatch, root gate fails while strategy is shown,
outputs exceed bounds, or worker/time/cold-start behavior violates acceptance.
Disable the pilot and restore the existing river-only `poker_spot.http_server:app`
entry point, or deploy a separately approved known-good SHA. The original
river-only baseline was `d0eb8699a7c7924cbbc3b2a562bb1a8554a231a9` /
`dep-dbdogaflot8c738sol00`; availability of that historical build is not assumed.
If release
ordering is suspect, pause automatic deploys under owner control and investigate.
Re-verify exact SHA, `/ready`, unauthenticated denial and both existing tools;
do not alter Auth0 or widen budgets as a latency fix. No database migration or
persistent user data is introduced, so rollback has no data-migration step.

Do not merge automatically or claim Stage B acceptance from this document.
The scoped new-tool activation and PR #33 optimization are owner-merged and Live;
actual Render/ChatGPT acceptance remains failed/open. Further production changes,
including disabling the pilot, require explicit owner approval. Plugin publishing, OAuth changes,
broader tools/ranges/users, larger budgets and paid plans remain unauthorized.
