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

The baseline archive is merged through PR #41 (`27dfec1da6ea5b96921e4352537cd0097f215c0d`); follow-on PR #42 targets `main` and remains unmerged. The owner confirmed the previously open house rules on 31 October 2026. A useful full-game approximation, an exploitability upper bound and owner acceptance of the research deliverable remain outstanding. No deployment has been performed.

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
