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

The baseline archive is merged through PR #41 (`27dfec1da6ea5b96921e4352537cd0097f215c0d`); follow-on PR #42 targets `main` and remains unmerged. Rule confirmation, a useful full-game approximation, an exploitability upper bound and owner acceptance remain outstanding. No deployment has been performed.

The standalone suite now runs unconditionally in the existing required `river` CI job, with a two-minute timeout and one OpenBLAS thread. It therefore participates in the fail-closed required `test` aggregate. The four numerical jobs, their original checks and eleven artifact groups are preserved. `tests/test_ci_gate.py` checks this workflow contract. Required CI results still need verification against the exact PR head; the historical local results above do not establish a new head's CI success.
