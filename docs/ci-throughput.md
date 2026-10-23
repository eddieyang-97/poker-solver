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
All eleven artifact names, iterations, limits and numerical gates are retained;
`tests/fixtures/ci-gates.json` records the original command/upload contract.
The sole command change is the explicit `--reference-workers 2` scheduling
option, admitted separately by the contract test. Serial remains the CLI default.

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
The first DAG-only run took 764 seconds (12m44s) and retained all eleven groups;
that missed the target. CI now bounds independent reference training to two
concurrent disposable subprocesses on the same standard runner. Every runout is
still trained independently; parent evaluation, aggregation and serialization
stay in original card order. No cached reference substitution, trimmed fixture,
reduced iterations, tolerance or trainer/solver change is used. The unchanged
12-minute step timeout and 120-second reference subprocess timeout remain gating.

## Failure injection and release boundary

`scripts/compare_ci_evidence.py` consumes baseline/candidate ZIP directories and
public artifact manifests. It checks all eleven ZIP digests, file sets, source
and raw-output hashes, worker receipts and every JSON leaf. Only explicitly
listed timing, memory, PID, profiler and verified raw-file digest metadata is
separated; numerical outputs, strategies, status/failure classifications and
limits use exact comparisons, with no newly introduced numeric tolerance.
The two reviewed scheduling-source hashes and reported worker count are explicit
execution metadata; source bytes are verified against each Git revision.
Readable Markdown is retained alongside its authoritative JSON. The complete
diff remains local; concise verified counts and any discrepancies are versioned.

The first optimized CI run passed in 425 seconds (7m05s), versus the sequential
median of 890 seconds: 52.2% less wall time. Its summed job time was 903 seconds;
rounding each job gives 17 runner-minute estimates versus the baseline median
15. This is a latency/cost tradeoff, not a proven per-run compute saving. Removing
the duplicate feature push reduces redundant full-suite work per PR update.
A second run passed in 423 seconds (7m03s), with 16 rounded runner minutes.
The two-sample median is 424 seconds, 52.4% below baseline; rounded runner-minute
median is 16.5 versus 15. This does not establish per-run compute savings or a
stable p90. Both runs retain eleven complete artifact groups. Final doc-head CI
and its additional timing receipt are linked on PR #29 to avoid recursive
evidence-only CI commits.

The strict optimized comparison exits 1: 19,451 non-metadata differences remain,
including strategy probabilities. The second run has 18,319 strict differences
and the same maximum probability/root-value/replay deltas. None is hidden by
loosening a threshold.
All reference-profile digests are unchanged; the largest product probability
shift is 0.34670755, not a chip EV discrepancy. Replaying both saved turn policies
in the same independent/product models passes all original same-policy,
convergence and cross-play bounds: maximum numeric mismatch 5.2246e-14 chips,
maximum root-value difference 0.000136553 chips. Largest probability shifts in
`trips_3x4` and `draw_4x4_two_sizes` occur at own reaches around 8e-8–3e-7.
Conditional action EVs there also differ materially. A small root NashConv does
not certify low-reach continuations, and no cross-run frequency precision is
claimed. The exact cross-run arithmetic/CPU cause has not been established.

Reproduce the diagnostic after downloading the two public artifact sets:

```powershell
.venv/Scripts/python scripts/compare_ci_evidence.py --baseline .artifacts/issue28/baseline-artifacts --candidate .artifacts/issue28/optimized1-artifacts --baseline-manifest .artifacts/issue28/baseline-artifacts-manifest.json --candidate-manifest .artifacts/issue28/optimized1-artifacts-manifest.json --baseline-revision 502ed40 --candidate-revision 45be65a --audit-turn-policies --output .artifacts/issue28/optimized1-comparison.json
```

This reports strict differences rather than zero-difference acceptance. Its
optional audit replays existing policies, without training, changing solver
behavior or replacing the independent reference. Two maximum resource probes
also timed out under unchanged budgets; the other four completed. Expected
study failures remain explicit and establish no hosted acceptance.

A paired same-host Windows/Python 3.14.8 singleton measurement (2,000/4,000
iterations) took 36.781s with one worker and 21.783s with two: 40.8% less wall
time. Maximum active child calls were 1/2 and all 44 reference-profile digests,
root diagnostics and aggregate values matched exactly. These are measured
samples, not universal bounds or Linux release acceptance.

In the fast sequential baseline, 188 distinct reference workers spent a summed
338.715 seconds training against the 351-second decomposition step. Training is
about 96.5% of that sample; worker startup is not the dominant measured cost.

`python -m unittest discover -s tests -p test_ci_gate.py -v` runs the actual
aggregate CLI with isolated results for each failed/skipped/cancelled/timed-out
or missing dependency. It also checks YAML dependencies, triggers, cancellation
and the complete unchanged check/artifact manifest. These are isolated tests,
not deliberately failed production builds or proof of Render provider behavior.

No branch-rule, Render, OAuth, hosted-tool or application change is included.
The existing protected `test` context remains, so no protection rename is
requested. It cannot succeed before every numerical/artifact job succeeds.
Issue #23 was closed after the successful green-main → automatic Render
`checksPass` deployment, exact-SHA public smoke and authenticated tool checks.
The failed-required-CI → **no deployment** negative case remains **unverified**
and is now tracked in open Issue #28. The isolated aggregate gate tests here
do not prove Render's negative-case behavior. This PR does not authorize
merge/deploy.

Rollback: owner-reviewed revert restoring the sequential `test` and full
coverage. Never bypass protection or enable commit-triggered deployment.
Post-merge main CI receipts require a separately accepted merge; PR checks
cannot substitute for them. Latest-head CI, matched artifact comparisons and
post-change repeated timings are recorded as observed, with unresolved gates
kept explicit in the results and PR.
