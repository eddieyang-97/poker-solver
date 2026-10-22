# Repository instructions

## Issue-driven development workflow

- Treat GitHub issues as the source of truth for milestone scope,
  dependencies, deliverables, acceptance criteria, and exclusions.
  Issue #11 is the parent roadmap; child issues define individual work.

- Before starting, read AGENTS.md, the assigned issue, linked
  documentation, relevant prior PRs, and current main.
  Check dependencies and avoid duplicating completed work.

- Work on one scoped issue per PR unless combining issues is explicitly
  justified. Reference the issue in the PR and explain any deviations
  from its requirements.

- Do not expand scope, weaken numerical gates, change solver semantics,
  or modify production integrations merely to complete a milestone.
  Record material blockers and propose separate follow-up issues.

- Preserve existing behavior and regression evidence. Add focused tests
  for new functionality rather than unnecessarily duplicating fixtures.

- Before requesting review, run relevant tests, static checks,
  independent benchmarks, and reproducible examples.
  Record exact commands, results, failures, source SHA, and CI evidence.
  Never describe unrun tests or pending CI as passing.

- PRs must summarize implementation, acceptance-criteria coverage,
  validation evidence, remaining limitations, and any security,
  resource, or deployment implications.

- Address review findings with focused fixes and fresh validation.
  Do not merge automatically. Wait for explicit owner authorization.

- After an accepted merge, update the corresponding issue checklist
  and milestone documentation. Close an issue only when its stated
  acceptance criteria are satisfied; otherwise retain outstanding
  work explicitly.

- Keep local implementation, solver correctness, range-model quality,
  and hosted acceptance as separate milestones. Deployment, OAuth,
  plugin permissions, or paid-resource changes require separate
  explicit authorization.

- Hosted scope: HEADS-UP NLHE river-only constrained decision analysis. A separately authorized experimental local turn/river engine is allowed in `poker_spot/turn.py`; keep it out of MCP registrations and production deployment until separately validated. Neither engine is a full GTO solver.
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
- `benchmarks/` is development-only. Never import its vendored reference into `poker_spot` or add it to the hosted requirements. Preserve its MIT license, pinned commit and source hashes; review provenance before changing the reference.
- Run `python scripts/benchmark.py --sensitivity` after solver or benchmark changes. Reject differing action trees/rounding rather than silently adapting them. Keep raise-enabled reference experiments separate from same-tree correctness gates and never expose them through the hosted tools.
- TexasSolver is an opt-in standalone development reference, never a hosted dependency. Do not commit its binaries, resource tables or source. Its current adapter accepts only the documented rank-class pilot; reject unsupported concrete combos and mismatched trees.
- After Texas adapter changes run `python scripts/benchmark_texas.py --evidence docs/texassolver-results.json --output .artifacts/texas-replay`. Label offline replay separately from actual external execution.
- The separate `audit_texas_blockers.py` diagnostic intentionally exits 1 for the recorded reference convergence failures. Keep its FAIL classifications and unchanged gate visible; passing replay regression tests do not establish a passing external solve. Do not add it to the passing fixture corpus or silently replace the admitted pilot.
- `texas_averaging_experiment.py` is a separately labelled, user-authorized source-build ablation. Preserve the pinned observer baseline, single-multiplier variant, matched checkpoints and original release failures. Never present its modified output as unmodified reference acceptance or deploy it; retain reports only, not upstream source/resources/binaries.
- After local turn changes run `python scripts/benchmark_turn.py`. Keep exact 44-per-deal chance, street-specific information sets, chip carry/refunds, scalar policy/BR and singleton minimax tests. Its oracle reads the product tree/policy; never describe it as an independently trained external turn solver. Do not register or deploy a turn MCP tool in this milestone.
- After turn decomposition/benchmark changes run `python scripts/benchmark_turn_decomposition.py`: preserve all 48 candidate rivers, compatible-pair mass divided by 44, independent river training, tree/rounding rejection and unchanged convergence gates. This special case has no turn betting and does not establish external two-street training correctness. After performance harness changes run `python scripts/benchmark_turn_performance.py`; retain actual time/RSS, platform and failure evidence. Maximum-dimension samples are not a universal worst-case bound or hosted memory/timeout acceptance.
- After independent turn reference or adapter changes run `python scripts/benchmark_turn_independent.py`. The reference model/trainer and isolated worker must never import product modules or consume its tree/policy during training. Preserve explicit private deals, 44 legal rivers, information-set pooling before regret clipping/BR choices, cent-exact tree rejection, bidirectional policy evaluation, analytical checks and unchanged numerical/convergence gates. This is a separately implemented in-repository development reference, not an externally audited solver or proven gold standard; it does not establish hosted acceptance. Keep full profiles in local/CI artifacts and version concise measured outputs/hashes.
- Issue #13 separately authorizes the experimental local river raise engine in `poker_spot/raises.py`, never a hosted tool or turn extension. Preserve one additional raise after the opening bet, cent-exact pot-after-call raise sizing, legal minimums/short all-ins, contribution/refund ledgers and positive-reach EV handling. After its product/adapter/worker changes run `python scripts/benchmark_river_raises.py --performance` plus the unchanged river benchmark/sensitivity. Keep pinned isolated reference training independent of product code/policies, reject differing trees/rounding/implicit all-ins, retain profiles/source hashes and unchanged gates. Local 60-second worker limits/measurements do not change hosted budgets or establish hosted acceptance.
- Issue #11's local action-model explorer performs joint conditioning only, never solver/MCP dispatch. Preserve chronological public-card filtering, exact observed-action/amount binding, complete supplied probability rows, unknown-likelihood gaps, latent cards of modeled folded players, private decimal contexts and no automatic marginal-to-solver substitution. Exclude future actions/cards and all hole-card claims from inference. After explorer changes run `python scripts/benchmark_range_explorer.py` and the existing river benchmark/sensitivity; keep rational-oracle, scale/context, zero-support, bounds and actual timeout tests. Performance samples are not universal resource bounds or hosted acceptance. Node locking and hosted/turn orchestration remain separate milestones.
- Issue #17's opt-in local raise review accepts explicit integer-cent opening/raise-to sizes alongside unchanged fractional trees. Preserve exact totals (no rounding/capping/implicit jam), the compact accounting regression, observed-but-unlocked semantics, explicit arrival hypotheses and request/result/tree/source receipts. After exact-size product/adapter/worker/review changes run `python scripts/benchmark_raise_review.py`, the existing `benchmark_river_raises.py --performance` and no-raise benchmark/sensitivity. The independent exact reference currently admits one opening amount using rational fractions; reject incompatible trees rather than adapting them. No joint-range substitution, node locking or hosted registration in this milestone.
