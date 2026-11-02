# Validation receipt — 31 October 2026

Historical experiment provenance: standalone Issue #40 research was measured on a working tree based on archive head `f245b59ad9d34b4bb41075c0e2116e5b5a076f33`; main inspected for those runs was `f59e8d7c5009845acc4f9a2c82364e104b80395d`. Working source hashes for the measured runs are in `outputs/research.json` and `outputs/abstraction.json`; the summary binds its raw input by SHA256. New files added after a run's startup are not retroactively included in its source manifest. Windows, Python 3.14.8, existing project virtual environment, portable GCC 14.2.0. The measurements below are local observations, not GitHub CI or hosted acceptance.

Output text was normalized to LF after execution, then the summary regenerated so its input digest also matches the committed file. Source digests identify the actual tested working-file bytes (existing archive files had CRLF, newly created Python files had LF). A checkout's automatic line-ending conversion can change those digests without changing code; account for that when comparing across platforms.

## Executed numerical commands

All ran from the repository root; `.venv/Scripts/python.exe` is abbreviated as `python` below. Compiler directory was added to PATH in PowerShell. No compiler/source download or executable is versioned.

```text
python experiments/liars_dice/liars_dice_analysis.py
g++ -O3 -std=c++17 -Wall -Wextra -pedantic experiments/liars_dice/audit_baseline.cpp -o .artifacts/liars_dice/audit_baseline.exe
.artifacts/liars_dice/audit_baseline.exe 200000 .artifacts/liars_dice/baseline-policy.bin
python experiments/liars_dice/run_research.py --iterations 10000 --games 2000 --policy-bin .artifacts/liars_dice/baseline-policy.bin
python experiments/liars_dice/summarize.py
python experiments/liars_dice/run_abstraction.py --iterations 50000 --games 2000
```

Both experiment drivers default to seeds `761245 42`; the full driver uses the second seed on the default rules only. Commands/results, resource measurements, rule profiles, iteration counts and independent toy evaluation are retained in the JSON outputs and discussed in [research.md](research.md). The archived C++ compile completed without warnings after adding its explicit return. The full-rule sampler completed its requested finite budget; the adjacent-action runs stopped at the explicit information-set cap. Neither passed useful equilibrium quality. Exit zero from the driver means a receipt was written, not that equilibrium acceptance passed.

## Executed checks

| Command | Observed result |
| --- | --- |
| `python -m unittest discover -s experiments/liars_dice/tests -v` | 15 tests passed, including exhaustive scoring/legality, analytical and enumerated BR checks, exact-vs-sampled convergence, regret/average importance expectation including zero target-policy support, posterior conditioning, budget stops and action-subset expansion. |
| `python -m ruff check experiments/liars_dice --exclude liars_dice_analysis.py` | Passed; unchanged archive retains an unused `comb` import. |
| `python -m ruff check poker_spot tests scripts` | Passed. |
| `python -m compileall -q poker_spot scripts` | Passed. |
| `OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v` | 200 tests, OK, three skipped; 95.716 seconds in the unsandboxed retry. |
| `OPENBLAS_NUM_THREADS=1 python scripts/benchmark.py --sensitivity` | Exit zero, unchanged river correctness and sensitivity corpus passed. |

The first sandboxed repository test attempt stalled after the history tests at the HTTP boundary and was stopped. Only its identified runner processes were terminated. The complete unsandboxed retry passed. This is an environment-specific observation; no HTTP or NLHE changes were made to obtain the pass. Detailed local test and river logs remain under ignored `.artifacts/liars_dice/`.

The baseline archive is merged through PR #41 (`27dfec1da6ea5b96921e4352537cd0097f215c0d`); follow-on PR #42 was owner-merged as `a6a9e7edf2bbc65491c10644ef9bf29c00a481f4` on 1 November 2026, with required PR-head [CI #41208869357](https://github.com/eddieyang-97/poker-solver/actions/runs/41208869357) successful. The owner confirmed the previously open house rules on 31 October 2026. Issue #40 is closed as an accepted experimental milestone. A useful full-game equilibrium approximation and an unrestricted exploitability upper bound remain outstanding under follow-on #43. No deployment has been performed.

The standalone suite now runs unconditionally in the existing required `river` CI job, with a two-minute timeout and one OpenBLAS thread. It therefore participates in the fail-closed required `test` aggregate. The four numerical jobs, their original checks and eleven artifact groups are preserved. `tests/test_ci_gate.py` checks this workflow contract. Required CI results still need verification against the exact PR head; the historical local results above do not establish a new head's CI success.

## Confirmed-rule continuation

The next experiment uses the owner-confirmed source context `3218e1d6a998509e8b42f548d0dabe1344b074d3` plus the LF-normalized working-source manifests in the new receipts. It preserves the original numerical corpora above. Executed with `OPENBLAS_NUM_THREADS=1` and the same project virtual environment:

```text
python experiments/liars_dice/run_guided.py --seeds 761245 42 --checkpoints 1000 10000 --games 2000 --adaptive-games 1000 --max-infos 200000
python experiments/liars_dice/prior_control.py
python experiments/liars_dice/run_family.py --games 5000 --adaptive-games 2000
python -m unittest discover -s experiments/liars_dice/tests -v
python -m unittest discover -s tests -p test_ci_gate.py -v
python -m ruff check experiments/liars_dice --exclude liars_dice_analysis.py
python -m ruff check poker_spot tests scripts
python -m compileall -q poker_spot scripts experiments/liars_dice
```

- **25 research tests passed**, including all original fifteen and independent control-variate expectations, exact frozen estimator moments, posterior likelihood checks, matrix games, exact chance enumeration and realization-equivalent root mixtures.
- **Four isolated CI gate/contract tests passed**, plus both lint commands, compileall and whitespace checks. An additional exhaustive check verified the prior guide against its declared baseline on all 42,588 hand/last-bid states.
- **All eight sampler ablations completed 10,000 iterations.** Best tested guided/baseline variants still have 95% full-game NashConv lower bounds 1.1538 / 1.2178. Detailed compute, memory, convergence and failure interpretation: [guided research](guided-research.md), `outputs/guided.json`.
- **Exact untrained control:** all 63,504 private deals enumerated, scalar EV −0.1744933564. Its numerical source receipt is `outputs/prior-control.json`.
- **Exact finite-family payoffs:** 225 policy pairings × 63,504 private deals. Restricted gap 2.3923e−9; outside response tests still give a 95% full-game lower bound 1.2079. See [family research](family-research.md), `outputs/family.json`. This is a rejected full-game approximation despite the tiny restricted gap.
- All listed new source hashes were independently checked after execution; the new JSON uses LF. The sampler's snapshot predates the separate finite-family/control test files, so those later files are covered by their own numerical receipts and latest-head test run instead of retroactively altering that snapshot.

No NLHE implementation or contract changed, and numerical results have not been promoted as hosted or full-game equilibrium acceptance. The existing complete required CI DAG will run on the pushed head; a previously green head is not a claim of success for these additions. Full-suite and NLHE numerical checks are supplied by that unchanged CI workflow rather than duplicating the already-passing earlier local suite.

## History-conditioned policy populations (#43)

Follow-on source context: merged `a6a9e7e`, initial unpruned implementation `47895c5`, then working source manifests retained in the numerical receipts. The experiment remains entirely under this standalone directory.

Executed with the project virtual environment and one OpenBLAS thread:

```text
python experiments/liars_dice/run_policy_space.py --rounds 2 --iterations 100000 --tremble 0.02 --mixture-cutoff 0.000001 --max-seconds 600
python experiments/liars_dice/run_policy_space.py --rounds 2 --iterations 100000 --tremble 0.10 --mixture-cutoff 0.000001 --max-seconds 600 --output experiments/liars_dice/outputs/policy-space-tremble10.json
python -m unittest discover -s experiments/liars_dice/tests -v
python -m unittest discover -s tests -p test_ci_gate.py -v
python -m ruff check poker_spot tests scripts experiments/liars_dice --exclude liars_dice_analysis.py
python -m compileall -q poker_spot scripts experiments/liars_dice
```

- **29 standalone tests passed** (four new), plus all four isolated CI-contract tests, Ruff, compileall and whitespace checks. Tests independently verify posterior histograms, off-model completion, exact policy-pair enumeration, history-dependent root-mixture realization, explicit support projection and inactive-component behavior.
- The primary run completed: populations 15/19/23 have exact candidate-response NashConv lower bounds **1.364617 / 1.092897 / 0.825342**. The final deployed restricted gap is **2.3921e−6**. These lower bounds have no chance-sampling uncertainty and no unrestricted upper-bound interpretation.
- Primary cost: **595.33 wall / 589.39 CPU seconds**, 713 policy pairs, 63,504 private deals per pair. Maximum observed pair: 16,656 public nodes and 21 bids. Maximum discarded root probability mass: 3.495e−7. No peak-memory measurement or controlled wall-time speedup is claimed.
- The tremble-0.10 sensitivity run also completed both expansions: response lower bounds **1.363773 / 1.093170 / 0.826045**, final deployed restricted gap **2.6484e−6**, **603.13 wall / 597.08 CPU seconds**. The between-pair guard permits the last pair to complete after 600 seconds; no hard-deadline pass is claimed.
- Every current source digest in both completed receipts, each serialized mixture value/restricted gap and all response lower bounds were independently recomputed and matched.
- The interrupted unpruned pilot is retained separately, including its completed first round and observed 216.28 process CPU seconds. Its executable-source manifests match `47895c5`; its test-file digest predates the additional full-rule test, as explicitly recorded.
- An isolated CLI node-budget probe (`--rounds 1 --iterations 10 --max-nodes 1`, ignored artifact output) exited nonzero and durably recorded `incomplete`, zero completed rounds and zero completed policy pairs. No false convergence was reported.

See [policy-space research](policy-space-research.md) and the versioned JSON receipts for response definitions, exact numerators, projection mass, ancestry and limitations. Required latest-head CI remains a separate verification step. No NLHE implementation, hosted interface or deployment changed.

## Full-rule nested-policy regression

PR #44's review identified that independent history-conditioned payoff traversal was previously tested only on the one-face game. The added `test_recorded_nested_full_rule_pair_against_scalar_roll_oracle` rebuilds the first two recorded Bayesian generations, independently enumerates chance multiplicities from 7,776 ordered rolls, and traverses all 63,504 private deals for component pair **(19, 15)**. Scalar scoring reads the raw dice; no grouped traversal, production contribution table or terminal utility helper supplies the expected result. Both challengers and both mode-switch directions are required. Its numerator **−147,016** over **60,466,176** agrees exactly with the existing receipt and a fresh grouped evaluation.

The focused policy-space suite passed all **five tests** locally; the full standalone suite passed **30 tests**, with repository/research Ruff, compileall and whitespace checks also passing. The original numerical receipts remain unchanged and retain their source/test context at `d4027db`; this additional regression postdates those runs. Numerical executable sources are unchanged. This verifies one complete full-rule nested-policy payoff rather than claiming an independent audit of all 488 added pairings.

## Bounded continuation-response milestone (#45)

See [methods and reproduction](bounded-response-research.md). Five new focused tests passed. Both completed bounded-search receipts verify extracted policies by exact full-rule component-pair replay, plus 54 independent small-game BR/realization cases per receipt. Original numerical corpora are preserved. The unanchored allocation failure is pinned by source hashes to `0423c99`; final receipts record the incumbent-refinement implementation separately. Full-game bounds use float64, not formal outward-rounded intervals, and do not establish GTO or hosted suitability.

## State/precomputation and query study (#46)

See [analysis research](analysis-research.md) for commands, environment, process-memory method and measured limitations. Four new focused tests cover raw-roll scoring/priors, snapshot identity, strict query validation, cache isolation, both-seat stream/reference equivalence and history dependence. The numerical study compares exact stream plus two lossy controls across 15/19/23 policies, records independent toy BR values, 18 held-out payoff checks and five fresh-process query benchmarks. The separate replay comparison verifies posterior equality and records cache misses. Windows working-set receipts are not Linux address-space or hosted acceptance.
