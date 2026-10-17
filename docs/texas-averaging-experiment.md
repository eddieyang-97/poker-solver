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

Initial status: guarded preparation verified locally; source compilation and
execution pending the dedicated PR workflow. No experiment results are claimed yet.
