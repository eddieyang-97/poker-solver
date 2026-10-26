# Development scope and remaining acceptance

**GitHub Issues are the actionable queue**, including [parent workflow/research #11](https://github.com/eddieyang-97/poker-solver/issues/11), [turn reuse research #25](https://github.com/eddieyang-97/poker-solver/issues/25) and [bounded hosted turn #26](https://github.com/eddieyang-97/poker-solver/issues/26). This page gives a durable capability map, not a parallel backlog or PR diary. [README](../README.md) is the entry point; [validation](validation.md) links measured evidence and true failure gates.

## Delivered capabilities versus remaining proof

| Workstream | Current implementation | Evidence and outstanding boundary |
| --- | --- | --- |
| No-raise river | Private hosted `solve_river`, `evaluate_river_call`; independently checked constrained benchmark corpus | Owner ChatGPT calls to both tools reproduced actual values; cold starts and OAuth lifecycle require separate checks. Caller-supplied ranges are not calibrated. [Evidence](benchmarking.md), [hosted acceptance](validation.md) |
| River hand analysis | Local reconstruction, supplied range hypotheses, optional one-raise and exact integer-cent review | Opt-in local only; separate tree-matching reference and accounting gates. Forced observed-line node locking is **not** implied. [Hand guide](hand-review.md), [raise guide](river-raises.md) |
| Action-frequency explorer | Local likelihood conditioning with joint blockers, folded-player latent cards and explicit unknowns | No population calibration, automatic solver input or hosted deployment. [Contract](range-explorer.md) |
| Turn research | Local two-street engine, independently trained in-repository reference, decomposition and resource studies | Small validated cases only; no external certification or general hosted turn solver. [Turn guide](turn.md), [reference](turn-independent.md), [resources](turn-resource-study.md) |
| Turn reuse / approximation #25 | Owner-merged PR #35 delivered strict-equivalence, transfer and short-fresh-solve comparisons | Reused transferred policies often produce abstaining wide bounds; exact-match hit rate from synthetic repeats is not real demand. Local research only; owner issue disposition remains. [Study](turn-reuse.md) |
| Hosted turn #26 | Narrow opt-in `solve_turn_v1` factory enabled separately; existing default river tools unchanged | Real pinned-game computation eventually succeeded, but **Free Render parent/headroom and warm-client latency gates failed**. Stage B not accepted. No cache, heuristic substitute, cost increase or relaxed convergence. [Timeout evidence](turn-hosted-timeout.md), [release contract](turn-pilot-release.md) |

## Future questions, not automatic instructions

- **Useful hosted turn delivery:** first demonstrate exact measured performance and quality under existing budgets, or explicitly decide no-go. Compare an exact precomputed catalog with bounded fresh solving only when supported by genuinely representative demand and preserved game keys. Do not represent heuristic EVs as certified equilibrium.
- **Observed-hand analysis:** correlated joint arrival distributions and true node locking change the game; define their conditioning and deviation semantics before deriving EVs. Later calibrated player models need population data, not just successful solver training.
- **Hosted raises and broader streets:** local raise correctness, one-off Linux worker measurements and theoretical feasibility do not authorize new MCP tools. Preserve strict Auth0 resource/subject checks, 20s/384 MiB limits and authenticated real-client evidence. Flop/multiway or six-max deep stacks require new independent numerical, resource and product milestones.

## Reproduction and histories

Stable, versioned benchmark inputs, source provenance, negative results and independent numerical checks live in [benchmark documents](benchmarking.md) and their adjacent `*-results.json` data. [Validation index](validation.md) distinguishes local, CI, Render and actual ChatGPT/client measurements.

Requirements, completion checklists, discarded designs, PR-by-PR CI receipts and remaining owner decisions live in [Issues](https://github.com/eddieyang-97/poker-solver/issues) and [PRs](https://github.com/eddieyang-97/poker-solver/pulls), **not** in a second independently maintained status history.
