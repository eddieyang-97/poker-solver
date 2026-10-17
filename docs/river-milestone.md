# River milestone closeout — 17 October 2026

This records the completed private river pilot and initial independent benchmark
milestone before any turn implementation. PRs #2–#5 are merged; the latest merge
is `af3d3984f569e70a2900a2b91fcd11e3619e332f`. It does not declare the optional
distribution, hosting-hardening or broader-reference work complete.

## Original hosted river deliverables

| Deliverable | Measured evidence | Status |
| --- | --- | --- |
| Dedicated hosted service, health/readiness and bounded calculations | Separate Free Render service; official SDK stateless HTTP; fixed process/CPU/memory/admission limits; [hosting](hosting.md) | Complete for the private pilot |
| Authenticated ChatGPT connection and both tools | Real Auth0 authorization-code/S256 consent; actual connector payloads for both tools after owner reconnect; [raw hosted acceptance](hosted-acceptance-results.json) | Complete for the owner connection |
| Conversational river analysis with computed outputs | Four weighted-range £505 solves and three call-EV calculations matched local reproduction exactly; [validation](validation.md#direct-authenticated-connector-acceptance-after-reconnect) | Complete |
| Automated checks and CI | Final benchmark PR head `3e4d9d07b1972ba93952656cfe94ae4db8ff1685`: 45 tests, Ruff, compileall, accepted benchmarks and replay checks; [CI](https://github.com/eddieyang-97/poker-solver/actions/runs/39023651886) | Complete |
| Deployed architecture, limits and verification documentation | [Validation](validation.md), [hosting](hosting.md), [README](../README.md); limitations retained | Complete |

Private-pilot acceptance does not mean always-on hosting, automatic refresh,
production social login or friends/public distribution has passed. The deployed
service remains river-only at the version/commit recorded in the hosted evidence.
Benchmark and documentation commits do not require production redeployment.

## Issue #1 initial benchmark deliverables

| Deliverable | Evidence | Status |
| --- | --- | --- |
| Independently authored reference, version/configuration and licensing | Pinned MIT noambrown implementation in an isolated process; exact upstream CLI failure retained; upstream naive evaluator used without algorithm edits | Complete |
| Initial representative corpus | Ten versioned fixtures spanning textures, weighted blockers, sizes, SPR, ties and rare nodes; [fixtures](../benchmarks/fixtures.json) | Complete; 20–30 expansion deferred |
| Canonical semantics and strict adapter | Full tree, hand identity/order, weights, blockers, bet rounding and EV normalization checked; mismatches rejected | Complete |
| Metrics and discrepancy reporting | Root/action EV, regret, recommendations, strategies, reach, best-response gap and runtime/allocation diagnostics; [reports](benchmark-results.md) | Complete |
| Reproducible CI harness | Deterministic independent execution, versioned snapshots, source hashes and licenses; no paid/secret reference dependencies | Complete |
| Separate richer-tree sensitivity | Same-input one-extra-raise experiment, excluded from correctness gates; measured OOP EV change about £0.6124 per £100 pot | Complete |
| Investigation of material discrepancy | Unmodified Texas weighted policies retained as FAIL; [controlled source-build ablation](texas-averaging-experiment.md) isolates an averaging effect | Complete for the observed fixture |

All ten accepted same-tree fixtures pass. Texas compatibility is one admitted
rank-class pilot, not ten-fixture external acceptance. The averaging variant is
explicitly modified source and cannot replace the unmodified failing baseline.
The current corpus does not establish unrestricted NLHE GTO correctness or
validate the caller's assumed arrival ranges.

## Follow-ups that remain open

| Follow-up | Current limitation / completion requirement |
| --- | --- |
| Broader reference coverage | Original Texas concrete-combo input is unsupported; alternative sizes require matching implicit-all-in controls. Broader games require another reviewed configuration/reference, not relaxed gates. |
| Corpus expansion | Grow from ten toward 20–30 only with useful independent evidence and reviewed fixtures. |
| OAuth operations | Automatic refresh is unconfigured/unverified. Observe real expiry/refresh, provider grant revocation, server-side access removal and reconnect recovery without weakening verification. |
| Production Google login | Auth0 uses development Google keys. Owner-managed client credentials require account configuration; never commit them. |
| Second-account and other-client acceptance | A separate person/account must independently connect and invoke both tools. Claude onboarding remains a proposed runbook. No friends/public availability claim. |
| Availability | Free Render cold starts can exceed the connector timeout. No paid plan or periodic keepalive is authorized/configured. |

These are visible follow-ups, not hidden passes. They are distinct from Issue
#1's initial acceptance criteria and the original owner-only hosted pilot.

## Turn implementation boundary

Turn work must wait for the user's agreed prerequisite scope to be completed.
The required private river pilot and initial benchmark acceptance criteria are
complete; PR #6 merged their closeout as `e2417485d6e6ca246d14d974e4af657a3d432ba8`.
The subsequent [local turn implementation](turn.md) proceeds on that basis,
with the optional follow-ups above still open and explicitly outside its scope.
When authorized to begin, implement and validate it separately from the accepted
river core and hosted river tools. Deterministic river-card chance, card-removal
conditioning, two-street pot/stack accounting and future betting decisions need
explicit tests and independent evidence. Multiplying turn showdown equity by a
river call-EV formula is valid only for a terminal/all-in model; it is not a
general turn continuation solver.

Do not expose an experimental turn calculation through the hosted MCP service,
raise resource limits or claim independent turn validation before the matching
tests, benchmarks and transport acceptance are complete. Preserve the existing
river behavior, evidence and owner-only authorization boundaries.
