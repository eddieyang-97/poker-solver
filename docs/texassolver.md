# TexasSolver compatibility pilot

PR #2's independent river harness was reviewed and merged as
`99a49cee5ddd169a0fd68e3a0f55ac02b40ed5a7`. The next pilot ran the upstream
standalone **Windows v0.2.0** console release locally. It adds a second
independently trained reference, without embedding TexasSolver, adding it to
the hosted service, or downloading binaries in CI.

## Provenance and source inspection

The release tag points to
[`95f039c116fa7bcae7fb6c01aca56adb0f24c680`](https://github.com/bupticybee/TexasSolver/tree/95f039c116fa7bcae7fb6c01aca56adb0f24c680).
The separate `console` branch was initially inspected at
`6dfb65b4d7ed081da509e8d8c3d82138c4708267`; it differs from the release source.
The release-tag source was then checked out for the actual comparison. In
particular, its default all-in settings differ from the console branch.

Local-only download:
[TexasSolver-v0.2.0-Windows.zip](https://github.com/bupticybee/TexasSolver/releases/download/v0.2.0/TexasSolver-v0.2.0-Windows.zip).
The recorded SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| Download ZIP | `0a9122fa0cd9384e6c1cbe0492e8a3b8ac7809890c649e1a53f77a59d6d50a7c` |
| `console_solver.exe` | `8b74cd6f687387a9ea6c567591642cfe0bfca88360a1748ff7c7db769d0c5c1a` |
| `resources/compairer/card5_dic_sorted.txt` | `4b68eee7bd91224157b125aad7429bf25cedd96370bcd228f316058d197afba2` |

The adapter verifies the executable and lookup hashes before running. These
identify the downloaded artifact; they do not prove a reproducible source build.
No upstream source, resource tables or binaries are redistributed here. The
upstream repository labels its source AGPL-3.0; this pilot invokes its separate
executable and retains our inputs, observed output and comparison data only.

Source details checked at the release tag:

- [`CommandLineTool.cpp`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/tools/CommandLineTool.cpp):
  `set_pot` assigns half the pot as each player's prior commitment;
  `set_effective_stack` adds that commitment. Five board cards select river.
  River raise lists start empty; the release's all-in flags start **true**.
  The CLI trains discounted CFR, not CFR+.
- [`PrivateRangeConverter.cpp`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/tools/PrivateRangeConverter.cpp):
  accepts rank classes of length 2/3 and rejects length-4 concrete combos. It
  silently drops weights at or below 0.005. Do not pass our arbitrary weighted
  concrete ranges through this parser as though they were supported.
- [`GameTree.cpp`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/GameTree.cpp):
  player 1 is OOP, player 0 is IP. Bets are percentages, rounded to big-blind
  units and ultimately integer amounts. Automatic all-in conversion is another
  source of differing trees. Payoffs include the equal prior commitments and
  are already centered around half the river pot.
- [`PCfrSolver.cpp`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/solver/PCfrSolver.cpp):
  JSON includes action labels, players and card-keyed average strategies, but
  omits terminal nodes/payoffs and action EVs. `set_dump_rounds 1` retains all
  river decisions because depth increments on chance/street transitions.
- [`BestResponse.cpp`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/solver/BestResponse.cpp):
  logged total exploitability is `(BR0+BR1)/2/pot*100`. Convert to NashConv chips
  with `2*pot*reported_percent/100`. This differs from noambrown's raw chip metric.

## Failed exact input and separately supported fixture

The original Issue #1 single-combo input (`KhKd` versus `AsAd,QhJd`) was actually
executed. It exited **3** with `range str AsAd len not valid` and produced no
strategy JSON. [The observed failure](../benchmarks/texassolver/unsupported-single-combo.json)
is retained. **That exact concrete game is still unsupported by this release.**

The successful pilot is separately named `texas_polarized_rank_classes`:
board `2c,3d,4h,8s,9c`, pot/stack £100, OOP `KK`, IP `AA,QJo:0.5`, only a
£100 bet. The six AA combos have total weight 6; twelve QJo combos at 0.5 also
have total weight 6. OOP has six KK combos. Every cross-player pair is compatible
and every AA beats KK, which beats every QJ. Thus the analytical rank-level
equilibrium is the same toy equilibrium, but this is **not the original concrete
fixture**. The [explicit canonical combo list](../benchmarks/texassolver/fixture.json)
is independently enumerated and checked against the class input before running.

The release's implicit all-in coincides with the sole allowed £100 bet; no extra
size is introduced in this pilot. Empty raise lists and a high all-in-conversion
threshold alone would **not** prove compatibility for other bet sizes. The
adapter supports only this reviewed fixture and refuses silent substitution.

Every exported action node is validated against the independent reference tree:
player mapping, check/call context, bet amount, complete decision children,
card-keyed rows and probabilities. Extra raises/sizes/streets, truncated exports,
missing hands and invalid probabilities are rejected. Texas omits terminals;
payoffs are reconstructed from the declared fixture, so strategy-tree checks
plus source inspection are evidence here, not a raw exported payoff audit.

## Observed results

The external run used one thread, no suit isomorphism, maximum 4000 iterations,
accuracy 0.001%, and print interval 100. It stopped at printed **Iter: 101**
(JSON checkpoint `iteration: 100`). It returned QhJd betting **50%**, KhKd calling
**50%**, and KhKd checking **100%**. The actual complete dump, commands, log,
lookup/executable provenance and three-engine comparison are in
[texassolver-results.json](texassolver-results.json).

| Same rank-class fixture | OOP root EV | NashConv | QhJd bet | KhKd call |
| --- | --- | --- | --- | --- |
| Product, 1500 iterations | −£25.0001 (rounded) | £0.03714713 | about 50.0056% | about 49.9316% |
| noambrown, 4000 iterations | −£25.00000914 | £0.01504138 | about 49.9712% | about 49.9987% |
| Actual Texas exported policy, independently evaluated | −£25.00000000 | about £3.6e−14 | 50% | 50% |
| Analytical | −£25 | 0 | 50% | 50% |

**The Texas EV/NashConv row is independent evaluation of its returned policy**
using the existing reference evaluator. Texas did not export these EVs. Its
actual logged total exploitability was `2.86102294921875e-06` percent, normalizing
to **£0.00000572205 NashConv**. The small nonzero log-versus-dump difference is
retained; float accumulation, export rounding and the final statistics traversal
can matter. Its exact cause has not been isolated. The difference is below the
existing £0.000051 rounded-output gate; no tolerance was relaxed.

All comparison gates passed. Off-path action EVs remain `null`, not invented
values. This one symmetric fixture does not validate general weighted/blocker
normalization, all ten existing fixtures, action-EV exports or full NLHE GTO.

## Reproduce

Actual execution is opt-in, local only, and requires the upstream Windows release
and its resource directory extracted together. The adapter has a 60-second
process deadline and uses an isolated temporary working directory:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark_texas.py --binary .artifacts/texassolver-release/TexasSolver-v0.2.0-Windows/console_solver.exe --output .artifacts/texas-pilot
```

Offline replay requires no TexasSolver download or executable:

```powershell
.venv/Scripts/python scripts/benchmark_texas.py --evidence docs/texassolver-results.json --output .artifacts/texas-replay
```

Replay checks the saved actual policy and freshly trains the product/noambrown
engines. It is **not a fresh TexasSolver solve**. CI labels this distinction and
retains its report. Inputs and outputs are saved separately before analysis so
an adapter discrepancy can be inspected rather than losing the external evidence.

Next steps: assess a separately pinned version/build supporting concrete combos
and controllable all-in settings, verify general blocker/weighted-range
normalization, then consider broader fixtures. Do not patch production behavior,
broaden this pilot implicitly, or call TexasSolver a proven gold standard.
