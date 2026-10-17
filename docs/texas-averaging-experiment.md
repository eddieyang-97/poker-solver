# Controlled TexasSolver averaging experiment

This follows the unresolved discrepancy in [the weighted-blocker audit](texas-blocker-audit.md).
It is a separately identified modified-source experiment, not a replacement for
the unmodified Windows release, a reference correctness pass, or a hosted change.
The original recorded FAIL results and £0.50 NashConv gate remain intact.

The source is pinned to TexasSolver `95f039c116fa7bcae7fb6c01aca56adb0f24c680`.
Preparation checks the clean tracked checkout, commit and evaluation-table hash;
all compiled source, header and generated input hashes are recorded. Upstream
source remains untouched. Generated copies in ignored artifacts add observation
at completed iterations 4,000, 8,000, …, 40,000. At each checkpoint, both average
and current strategies are exported immediately after the source exploitability
calculation. Suit isomorphism is disabled and one training thread is used.

The first Ubuntu workflow stopped at the strict table guard before compilation:
Git's LF table has SHA256 `13e0f4bd3cb99388caec49b36f98b98b70ae30407cbd740d880db65ed4db5e7b`,
while the Windows checkout/release uses CRLF and hash
`4b68eee7bd91224157b125aad7429bf25cedd96370bcd228f316058d197afba2`.
Reading the pinned Git blob independently confirmed that CRLF-to-LF conversion
alone accounts for every byte difference. Preparation now requires the exact
LF-normalized content hash and one of these two raw hashes; manifests retain both.
The unmodified Windows release adapter still requires its original raw hash.

The next build exposed missing direct `<memory>` includes in the old upstream
headers on GCC 13. Both executables therefore force-include that standard header
via the same recorded compiler option. No upstream header or algorithm is edited
for this compatibility correction. Compiler warnings remain visible in CI logs.

Two executables share the same instrumented solver:

- `baseline_observer`: original regret and averaging updates, including theta=0.9.
- `theta_one`: only the accumulated-strategy multiplier is changed to 1.0.
  This preserves history; it is not described as standard linear DCFR averaging.

Both use the exact weighted-blocker fixture and a fixed 40,000-iteration budget.
Accuracy is set to −1 to disable early stopping, and print interval is 4,000.
The fixed budget and input commands are retained. Each process has a 120-second
deadline, and the ephemeral Ubuntu build job has a 20-minute deadline.

The adapter validates every exported action tree and hand row. The existing
independent evaluator calculates centered OOP EV and NashConv for each policy.
Source exploitability is converted by `2 * initial_pot * percent / 100`, then
compared with the average policy from that exact checkpoint. Current policies
are compared between variants to detect any change in the training trajectory.
A lower average-policy gap with matching sampled current policies is evidence
of an averaging effect on this fixture, not proof of a general solver fix.

The dedicated PR workflow installs Qt5 Core, CMake and GCC on an ephemeral
Ubuntu GitHub runner. It checks out the external source separately and uploads
only generated reports, not external source, lookup tables or executables.
The normal Python CI uses offline recorded evidence only.

Reproduce on Linux with the pinned clean external checkout and Qt5 development
headers, CMake, OpenMP and GCC available:

```sh
python scripts/texas_averaging_experiment.py prepare --source /path/to/TexasSolver --prepared .artifacts/texas-prepared
cmake -S .artifacts/texas-prepared -B .artifacts/texas-build -DCMAKE_BUILD_TYPE=Release
cmake --build .artifacts/texas-build --parallel 2
OPENBLAS_NUM_THREADS=1 python scripts/texas_averaging_experiment.py run --source /path/to/TexasSolver --prepared .artifacts/texas-prepared --build .artifacts/texas-build --output .artifacts/averaging-results
```

## Actual execution — 17 October 2026

[The dedicated source-build workflow](https://github.com/eddieyang-97/poker-solver/actions/runs/39023271206)
passed at repository commit `23b054f318a143ea60d579aeeb9596d320751852`, using
Ubuntu 24.04, GCC 13.3, Qt5 Core 5.15.13, Python 3.12.15 and OpenMP. Both actual
40,000-iteration processes completed successfully. The artifact ZIP's SHA256 is
`48e0afa746c02a805d45238cf36377f7bff532945f4793c36b15e6ee84b1e24c`;
the downloaded ZIP was verified against GitHub's recorded artifact digest before
its reports were retained. No binaries, lookup data or source are in that ZIP.

[texas-averaging-results.json](texas-averaging-results.json) preserves all ten
raw checkpoints per variant, both policies, source metrics, input commands,
compiler/platform, logs, final post-statistics exports, binary hashes and build
input hashes. [texas-averaging-results.md](texas-averaging-results.md) is the full
generated comparison table. These are real builds and calculations, not synthetic
or offline-only observations.

| Variant | Iterations | Independently evaluated OOP EV | Average-policy NashConv | £0.50 gate |
| --- | --- | --- | --- | --- |
| Observer baseline, theta=0.9 | 4,000 | −£24.97470416 | £1.59073955 | FAIL |
| History-preserving variant, theta=1 | 4,000 | −£24.99999894 | £0.00335872 | PASS |
| Observer baseline, theta=0.9 | 40,000 | −£25.00777017 | £1.13173461 | FAIL |
| History-preserving variant, theta=1 | 40,000 | −£24.99999705 | £0.00005794 | PASS |

All ten baseline average policies fail; all ten variant average policies pass.
The current policies are **exactly identical between the two builds at every
sampled checkpoint**, while both builds' current-policy NashConv remains above
£0.50. At 40,000 it is £1.77262557. The variant's average gap is not monotonic
across every sample, and there is no claim of a monotonic convergence guarantee.

At 40,000, the variant checks OOP KK 100%, calls with KK 50%, and bets QJ
47.91679084% after a check, close to the weighted game's analytical 23/48
(47.91666667%). IP AA and KK bet 100%. These are computed conditional
frequencies for this constrained tree and arrival ranges, not live-play advice.

The observer's 4,000/40,000 average-policy JSON is **exactly identical** to the
earlier unmodified Windows release exports. This strengthens confidence that
observation/build compatibility changes did not create the original failure.
The final post-statistics exports also equal the final checkpoint averages for
both builds. At identical checkpoints, source-normalized and independently
evaluated average NashConv differ by at most £0.00002164, below the existing
£0.000051 output-precision allowance used by the admitted pilot. No tolerance
was fitted to this experiment or widened.

The controlled single-multiplier change isolates a material averaging effect
on this fixture while the sampled current trajectory matches. It supports
averaging as the cause of this fixture's exported-policy failure. It does not
prove the absence of other issues, exact behavior at unsampled iterations,
general convergence on other games, or correctness of a patched release. The
original release audit remains FAIL and excluded from accepted benchmarks.
Concrete-combo support, independently verified alternative sizes and broader
Texas fixtures remain outstanding. Product/hosted behavior and OAuth are unchanged.

Re-evaluate every saved policy without compiling/running TexasSolver:

```sh
OPENBLAS_NUM_THREADS=1 python scripts/texas_averaging_experiment.py replay --evidence docs/texas-averaging-results.json --output .artifacts/texas-averaging-replay
```

Replay exits 0 when evaluation succeeds, regardless of the preserved FAIL
classifications; it is a diagnostic rather than an accepted-corpus convergence
command. Tests separately enforce the expected classifications and unchanged
gates. The older `audit_texas_blockers.py` still deliberately exits 1 for its
unmodified release failures. Normal CI performs replay, not a fresh source build.
