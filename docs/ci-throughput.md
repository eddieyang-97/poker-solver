# CI throughput and required release gate — Issue #28

Four independent jobs use ordinary `ubuntu-latest` runners:

| Job | Required work |
| --- | --- |
| `river` | Static/unit checks, river sensitivity, range explorer, hand review, raises/exact review, both Texas replays |
| `turn` | Turn policy oracle and independently trained strategic turn reference |
| `decomposition` | River-subgame decomposition and maximum-size turn performance |
| `resources` | Linux resource study, including explicitly failed budget probes |

The required GitHub Actions check remains exactly **`test`**. It lists all four
dependencies with `if: always()`. `scripts/ci_gate.py` accepts only the exact job
set with every result `success`. Failure, cancellation, skip, timeout, missing or
unknown results and malformed input fail closed. Upload failures fail their job.
There is no path filtering, conditional benchmark admission or continue-on-error.
All eleven artifact names, commands, iterations, limits and numerical gates are
retained; `tests/fixtures/ci-gates.json` records the sequential baseline contract.

Feature branches run on `pull_request` only; main runs on `push`, with identical
numerical coverage. Concurrency keys separate PR numbers from unique main run
IDs. Only superseded runs of the same PR can be cancelled; main runs cannot
cancel each other. Synchronization/rebases trigger fresh PR checks; a merged SHA
receives separate main validation. No workflow-dispatch or paid runner is added.
Four numerical runners plus the short aggregate is the maximum per run.

## Measurements

Read-only public timeline collection (no credentials/settings writes):

```powershell
.venv/Scripts/python scripts/profile_ci.py --run 39854268963 --run 39865456688 --run 39842226267 --output .artifacts/issue28/baseline
```

Raw run/jobs/artifacts JSON is retained locally; versioned
[measurements](ci-throughput-results.json) distinguish critical path, initial
queue, created-to-green, setup/install overhead, artifact sizes and summed job
time. Rounded runner minutes are an estimate, not account billing. The third
baseline is final preparation head `9e63c6ab`, merged in `502ed404`; numerical
sources and workflow match main.

| Sequential successful run | Job wall | Decomposition | Initial queue | Runner-minute estimate |
| --- | ---: | ---: | ---: | ---: |
| 39854268963 | 1,199s | 691s | 3s | 20 |
| 39865456688 | 637s | 351s | 2s | 11 |
| 39842226267 | 890s | 522s | 3s | 15 |

Median: 890 seconds (14m50s). Three samples do not support a useful p90 estimate.
Runner logs identify Actions 2.338.0, Ubuntu 24.04.5, image `20261012.334.1`;
regions differ. Artifact totals: 862,586–862,735 bytes across eleven groups.
Runner variance is substantial; measurements are not deterministic bounds.

Decomposition trains 188 independent river games over all 48 candidate runouts
per fixture, preserving zero-mass cards and 44 legal rivers per compatible deal.
Start with DAG parallelism; no cached reference substitution, worker fan-out,
fixture trimming, reduced iterations or algorithm changes. Its unchanged
12-minute timeout remains gating. Further optimization needs profiling evidence.

## Failure injection and release boundary

`python -m unittest discover -s tests -p test_ci_gate.py -v` runs the actual
aggregate CLI with isolated results for each failed/skipped/cancelled/timed-out
or missing dependency. It also checks YAML dependencies, triggers, cancellation
and the complete unchanged check/artifact manifest. These are isolated tests,
not deliberately failed production builds or proof of Render provider behavior.

No branch-rule, Render, OAuth, hosted-tool or application change is included.
The existing protected `test` context remains, so no protection rename is
requested. It cannot succeed before every numerical/artifact job succeeds.
Issue #23 separately tracks actual `checksPass` deployment ordering and failed-CI
nondeployment. This PR does not authorize merge/deploy.

Rollback: owner-reviewed revert restoring the sequential `test` and full
coverage. Never bypass protection or enable commit-triggered deployment.
Post-merge main CI receipts require a separately accepted merge; PR checks
cannot substitute for them. Latest-head CI, matched artifact comparisons and
post-change repeated timings are recorded as observed, with unresolved gates
kept explicit in the results and PR.
