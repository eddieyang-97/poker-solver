# Exact-size local river review — 22 October 2026

Issue #17 adds exact integer-cent sizing and opt-in hand-review dispatch to the
existing local one-raise worker. This is not node locking, range calibration or
hosted acceptance. The original 200bb example remains intact; the existing compact
150bb accounting input is reused, with range hypotheses in a separate file.
The measured implementation is `4e6d4a2ef6724d6384f2fc1d2b8367e4075ee4f1`;
the following documentation commit does not alter product/test/benchmark sources.

The actual disposable worker and independently trained matching reference ran
2,000/4,000 CFR+ iterations on the £63 pot / £275 remaining stack tree. Both use
the observed £40 opening, raise-to-£120 and an explicitly requested jam-to-£275.
The HJ decision maps to `c/b4000`; the next BTN decisions are
`c/b4000/r8000` and `c/b4000/r23500`. No implicit all-in is added.

| Measurement (chips) | Product | Independent reference |
| --- | ---: | ---: |
| Root EV relative to half starting pot | -9.26970804 | -9.26968372 |
| NashConv | 0.00723474 | 0.00387502 |

Largest fixed-policy EV/BR/reach/action-EV discrepancy: **1.7053e-13 chips**,
under the unchanged 1e-8 gate. Trained-value difference: **0.00002432 chips**,
within the combined gaps. Both gaps are below the unchanged **£0.315** gate.
The reference received exact reduced rational sizes 40/63, 80/143 and 235/143,
with no implicit all-in and the same one-additional-raise tree. Its isolated
trainer imported no product module. This pinned implementation is an independent
reference, not an externally audited gold standard.

These values concern the explicitly supplied illustrative independent arrival
ranges. They are not a solution of the real-world limp-call hand or a betting
range inferred from earlier actions. Checks/bets are endogenous; joint and own
strategic reach do not establish observed-line probabilities. The JSON retains
the exact request, queried-node output, accepted action mapping, runtime,
reference configuration/checkpoints, raw/profile/source hashes and limitations.
Full request/results and both profiles remain local/CI artifacts.

Local Windows/Python 3.14.8 checks passed: Ruff, compileall, **132 tests run,
131 passed and one Linux-only allocation check skipped**, the existing **8/8
independent raise fixtures / 48 mixed-policy comparisons**, both maximum local
workers, and **10/10 no-raise cases plus sensitivity**. All eight legacy outputs
at 2,000 iterations match canonical JSON bytes captured before these changes on
the same machine. This compatibility sample is separate from cross-platform
round-off or universal correctness claims. The known approximately
**8.7562e-9-chip** reference action-EV discrepancy remains, with little margin
below its unchanged 1e-8 gate; it was not tuned away.

Exact reference comparison currently rejects more than one opening amount;
per-bet raise totals cannot be silently converted to a single different fraction.
New exact-mode requests are rejected if mixed, over-stack, duplicated, noninteger,
under-minimum or inconsistent with the observed prefix. Existing fractional
rounding rejection and all-in/minimum/refund behavior remain intact.

Reproduction commands and exact measured hashes are in
[raise-review-results.json](raise-review-results.json). CI adds a separate
`exact-size-raise-review` artifact with full sanitized inputs/results and raw
profiles. Final-head CI was pending when this local snapshot was recorded.
No deployment, MCP registration, OAuth, plugin, paid-resource or turn changes.
