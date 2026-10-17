# Weighted-blocker reference discrepancy

This is a **failing external-reference diagnostic**, separate from the passing
ten-fixture suite and the admitted TexasSolver rank-class pilot. No gate was
relaxed and no solver or reference algorithm was modified.

PR #3 was reviewed and merged as `946adaa5314af00ee0d15b4b58ea3329290a302d`.
The next investigation checked newer source pinned at
[`bb53f8cbfff4841da2d75bd060d0ab269c3d5881`](https://github.com/bupticybee/TexasSolver/blob/bb53f8cbfff4841da2d75bd060d0ab269c3d5881/src/tools/PrivateRangeConverter.cpp).
It still admits only two-/three-character rank classes, not concrete combos.
No installed C++ compiler or WSL build environment was found locally; no system
toolchain was installed. The original exact-combo comparison remains blocked.

## Matched diagnostic game

Use the same five-card board `2c,3d,4h,8s,9c`, £100 pot/stack and sole £100 shove,
but add IP `KK:0.5`: OOP `KK`, IP `AA,KK:0.5,QJo:0.5`. This is a separately named
game with [explicit combos/weights](../benchmarks/texassolver/blocker-fixture.json).
As in the prior pilot, the release's implicit all-in creates no extra size.

Six OOP KK combos meet 24 IP combos before hole-card removal. Each OOP KK is
compatible with only one of IP's six KK combos. Enumerating all valid pairs gives
**114 pairs**, unnormalized joint weight **75**, and IP category probabilities
**AA 48%, KK 4%, QJ 48%** after conditioning. Using the unconditioned IP marginal
would incorrectly give KK 20%. The audit checks this distribution explicitly.

The analytical equilibrium changes because IP's tying KK hands can bet to fold
out opposing KK. IP KK bets, OOP calls half, and QJ bets **23/48 ≈ 47.9167%**.
OOP call-minus-fold indifference, with per-OOP compatible weights, is
`6*(-100) + 0.5*50 + 6*x*200 = 0`. OOP root EV remains **−£25**. The complete
constructed analytical policy is evaluated by the independent best-response
routine: NashConv is about `3.6e-14` chips, within floating-point error.
These are derived analytical values, not fabricated external outputs.

## Actual observations

The same hashed Windows v0.2.0 executable and lookup table used in
[the initial pilot](texassolver.md) were run unmodified with one thread, suit
isomorphism off and accuracy target 0.001%. The two budgets used print intervals
100 and 1000 respectively. All decision nodes, action amounts, players, children
and hand rows passed the strict import checks before evaluation.

| Maximum iterations | OOP EV of exported policy | Independent NashConv | Existing gate | Result |
| --- | --- | --- | --- | --- |
| 4,000 | −£24.97470416 | £1.59073955 | £0.50 | **FAIL** |
| 40,000 | −£25.00777017 | £1.13173461 | £0.50 | **FAIL** |

Root EV near the equilibrium value does not establish a small best-response gap.
Increasing the budget tenfold did not bring this exported policy below the gate.
This is not proof that no later budget/version can converge.

Separately trained product/noambrown results on the **same** game, at 1500/4000
iterations: root EV −£25.0001 / −£25.00000674; independently measured NashConv
£0.03584237 / £0.01608152. Their existing comparison gates passed. No thresholds
were chosen from the failing Texas outputs.

[texas-blocker-results.json](texas-blocker-results.json) retains both actual input
command files, raw exports, logs/checkpoints, binary/lookup provenance, and full
independent comparison. [texas-blocker-results.md](texas-blocker-results.md) is the
generated discrepancy table. Last printed checkpoints have zero-based indices
3900 and 39000; final exports follow completion of budgets 4000/40000. The report
retains both log normalization and independent final-policy evaluation and does
not require those **different checkpoints** to match exactly.

## Investigation and unresolved cause

The release's
[`PrivateCardsManager::setRelativeProbs`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/ranges/PrivateCardsManager.cpp)
explicitly conditions on compatible opponent weight. Thus the observation is
not established evidence of a simple missing-blocker normalization bug.

One candidate is exported strategy averaging: the inspected
[`DiscountedCfrTrainable.h`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/include/trainable/DiscountedCfrTrainable.h)
sets `theta=0.9`; its
[`updateRegrets`](https://github.com/bupticybee/TexasSolver/blob/95f039c116fa7bcae7fb6c01aca56adb0f24c680/src/trainable/DiscountedCfrTrainable.cpp)
multiplies accumulated strategy by theta at each update, emphasizing recent
strategies. The logs continue to oscillate rather than meet the requested target.
This is a **candidate explanation**, not an isolated root cause: no altered build,
ablation, algorithm patch or output averaging was performed.

## Reproduce and interpret the status

Actual local execution (two fixed budgets, each with a 60-second deadline):

```powershell
.venv/Scripts/python scripts/audit_texas_blockers.py --binary .artifacts/texassolver-release/TexasSolver-v0.2.0-Windows/console_solver.exe --output .artifacts/texas-blockers
```

Offline replay, requiring no Texas binary:

```powershell
.venv/Scripts/python scripts/audit_texas_blockers.py --evidence docs/texas-blocker-results.json --output .artifacts/texas-blocker-replay
```

**Both commands exit 1 for these observed convergence failures** and write JSON
and Markdown FAIL reports. This is not a transport failure. Regression tests
verify the chance calculation, analytical policy, independent engines and
preservation of the two failures. Passing tests mean the diagnostic is reproduced;
they do not turn the reference solve into a passing comparison. The diagnostic
is not silently folded into the green benchmark corpus.

Follow-up requires isolating convergence/averaging behavior in a separately
identified build/version or another independently verified reference. Do not
adjust our production solver, widen the gate or relabel the outputs to agree.
