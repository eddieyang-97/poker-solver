# Turn solution reuse and estimation — Issue #25

**Recommendation: pursue short fresh solves with a measured best-response stop
gate before building a larger approximate catalog.** Exact suit/money reuse is
valid within the checked complete game. Transferring a nearby strategy is fast,
but usually needs to abstain. Plain cached EV and an equity adjustment are too
inaccurate in these examples to recommend as user-facing estimates.

This is local research, not a product cache or a change to the turn engine.
The hosted pilot still requires exactly 2,000 iterations. Nothing here changes
its contract, existing resource/convergence limits, production integrations or
Issue #26's failed hosted acceptance. Educational, post-session use only.

## Experiment

[Fixtures](../benchmarks/turn-reuse-fixtures.json) declare three sources from
the existing independent corpus: weighted dry, weighted collision, and a
four-flush with four combos per side and two river sizes. The 20 synthetic
queries contain one exact repeat, three equivalent transformations, 13 changed
games, and three deliberately unsupported transfers. Changed games vary range
weights, stack/pot ratio, bet sizes and board cards, including a four-flush
becoming a three-flush. No parameters were fitted or changed after observing
the results. All 13 changed-input games are outside **every** source's suit/money
key class; a regression checks this separation. Examining the successful transfers
then revealed three further strategic duplicates under the supplied mapping:
two blank-rank swaps and one unused-stack change. We retain them, compare every
private-deal/runout payoff and chance tensor plus the active tree, and exclude
them from approximation-error statistics. The remaining ten targets change the
strategic game; a regression protects this leakage audit.

Source family and a complete card bijection are **supplied**, not inferred by
a nearest-neighbour search. This is a favourable test of transfer given a known
candidate, not an automatic arbitrary-board lookup or measured user demand.
The extra-size, new-hand and short-stack/all-in topology cases reject transfer;
they are not claims that fresh local solving cannot handle those games.

The existing #21 `full_record`/gzip/hash/validation contract stores full average
policies under ignored artifacts. It preserves solver/runtime/iteration identity,
all weighted hands, 48 public contexts, null support, actions and diagnostics.
No product module imports the new benchmark code. No database, model training,
production cache, nearest-hit fallback or automatic range inference is added.

## Methods and guarantees

**Exact/equivalent:** enumerate the 24 global suit permutations. Canonicalize
the complete board and weighted ranges, preserving players and absolute weights.
Normalize every actual bet, terminal contribution and remaining stack by the
starting pot using exact binary64 ratios. Preserve tree topology, actors, chance,
solver/runtime and iterations. This permits proportional chip-unit changes only
when the complete realized ledger scales exactly; no rounding makes a hit.
Card/hand order is mapped explicitly. Identical capped trees may be equivalent
even when unused input fractions differ; altered topology is rejected.

Global suit relabelling preserves hand ranks, blockers and the uniform 44 legal
rivers per compatible deal. Scaling the full monetary ledger multiplies every
payoff by the same positive constant. Thus the mapped *existing policy* and its
best-response bounds scale; this does not assert bit-identical fresh CFR training
or a unique equilibrium. Tests cover all 24 permutations, hand order, every river
EV/null, monetary scaling and invalid mappings. Source artifacts retain #21's
strict identity; this separate equivalence experiment does not relax that reader.

**Approximate:** map the full source average behavioral policy into the target
game. Changed weights, arbitrary provided card permutations and different bet
amounts are allowed only with completely mapped hand support and the same ordered
action/continuation structure. There are no defaults for missing hands or merged
actions. Evaluate both players' strategies and legal best responses on the
**target** board, weights and payoff ledger. This is target fixed-policy
evaluation, not a fresh target solve or target equilibrium EV.

For any transferred policy pair, let `L` be OOP's value against IP's best response
and `U` OOP's best response against IP. In this finite zero-sum game its equilibrium
value lies in `[L, U]`, and NashConv is `U - L`. A midpoint has maximum value error
half that width, plus the existing `1e-8` numerical allowance. We accept a
**bounded root value** only at the unchanged 0.5%-pot width gate; otherwise report
`abstain_wide_bound`, retaining the interval and policy value. This bounds aggregate
root value, not every hand's frequency, conditional EV or low-reach continuation.

Compare five root estimates: source EV scaled by pot; that EV plus the change in
forced-checkdown EV; target fixed-policy EV; the BR interval midpoint; and a fresh
200-iteration solve with no transferred state. The equity adjustment assumes the
strategic premium transfers across games; the counterexamples test that assumption.
Payoff-sign changes and compatible-deal total variation are explanatory similarity
diagnostics, not fitted scores or an acceptance threshold.

## Independent validation and results

Every supported target gets a separately constructed, isolated 4,000-iteration
reference solve and a fresh 2,000-iteration product solve. Reference training
receives only configuration, never product policies/trees. Transferred, short,
fresh and reference policies are cross-evaluated in both models, including each
BR bound and explicit hand/action mapping. Same-policy differences must remain
under **1e-8 chips**; fresh/reference gaps must remain under **0.5% of pot**.
Their equilibrium-value intervals must overlap. Full profiles/source hashes
are retained; the reference shares the pinned evaluator and CFR+ family and is
not an externally audited gold standard.

[Recorded report](turn-reuse-results.json) and [case table](turn-reuse-results.md)
retain actual inputs, timings, bounds, failures and provenance. All 17 supported
targets passed the independent checks; all three unsupported transfers rejected.
Maximum same-policy discrepancy was **1.42e-13 chips**.

| Estimate, 10 strategically changed targets | Median absolute root error (% pot) | Maximum (% pot) |
| --- | ---: | ---: |
| Scaled cached EV | 5.8746 | 21.4960 |
| Checkdown-equity adjustment | 4.8496 | 29.2603 |
| Transferred policy, evaluated on target | 5.7546 | 52.4100 |
| BR midpoint, including abstained cases | 2.7939 | 26.0550 |
| Fresh 200 iterations | **0.0118** | **0.0251** |

Errors are against the independently trained reference's root value, whose own
nonzero convergence interval is recorded. They are not measured errors against
an exact general equilibrium. The bounds, rather than sample error statistics,
provide the target-game value guarantee.

Strict lookup matches **1/20**, equivalence expands that to **4/20**, and approximate
transfer gives narrow root bounds for **3/13** additional changed-input targets:
precisely those three strategic duplicates. All **10/10 genuinely changed games
abstain**. All 13 fresh 200-iteration solves have narrow bounds. These constructed
ratios neither establish real demand nor imply unseen-game coverage.

Two useful failures:

- Reducing the dry source's QJ weight from 0.7 to 0.1 leaves its raw cached EV
  comparatively close (1.37% pot error), but its transferred strategy loses
  **52.41% pot** relative to the reference, with a **52.71%-pot BR interval**.
  A plausible root-number estimate does not validate its strategy.
- Removing a spade from the four-flush changes two root fixed-continuation action
  choices, costing **13.21% and 6.84% pot** under the reference continuation.
  Transfer's BR width is **54.68% pot**. Its midpoint even has the wrong centered
  root-value sign, but is correctly classified as an abstention. A positive or
  negative centered value is not itself an action recommendation.

## Performance and scope

Local Windows measurements use Python 3.14.8, NumPy 2.5.4 and one BLAS thread.
Full catalog gzip storage is **47,235 bytes** for three tiny games. Online timing
includes source reconstruction, file read/checksum/decode/validation, target
construction, equivalence checks, full policy transfer and target value/both BRs.
It excludes imports and reference training; separate fresh-process probes include
startup, imports, three reads/evaluations, JSON and reap. Parent CPU measurements
can quantize to zero for very small stages on Windows; do not infer zero work.
The JSON retains all samples and source-generation costs. Timings vary between
passes and are observations, not universal bounds or a Render CPU extrapolation.

For the ten strategically changed targets, online lookup/transfer/BR cost was
**0.016–0.043s**, versus **1.306–3.114s** for 2,000 fresh iterations and
**0.138–0.321s** for 200. Median per-target speedups including measured target
construction were **105x** and **9.5x**, respectively. Three fresh-process
probes took **0.256–0.283s total parent wall** (startup plus three evaluations)
and **35.1–37.6 MiB peak RSS**. These Windows measurements are explicitly unlimited.

The recorded report contains matched per-target speed ratios and all fresh-process
samples, including startup plus three read/evaluation samples. Fast transfer
mostly buys wide intervals and abstentions. OS filesystem caches may already be
warm; these are fresh processes, not measured cold storage or Free Render wake-ups.

Linux CI runs three fresh-process probes with the existing **20s CPU / 384 MiB AS**
limits installed before NumPy/product imports, and a 20s parent timeout including
serialization/reap. Windows probes explicitly report unlimited memory/CPU mode.
These are local/CI experiments, not hosted startup, OAuth or ChatGPT acceptance.
The required CI `test` dependency set and eleven artifact groups remain intact;
the new study's profiles/catalog are retained in `turn-policy-validation`.

## Reproduce and next work

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.venv/Scripts/python scripts/benchmark_turn_reuse.py --output .artifacts/turn-reuse
.venv/Scripts/python -m unittest discover -s tests -p test_turn_reuse.py -v
```

1. Explore a local fresh-solve stopping rule that checks BR width at measured
   checkpoints and abstains/escalates when convergence is insufficient. Validate
   larger, diverse and adversarial held-out ranges before changing any product
   iteration contract. Passing at 200 here is not permission to reduce #26's 2,000.
2. Keep exact suit/money equivalence as a small optional research primitive.
   A real catalog needs demand evidence and immutable packaging/admission; this
   trusted local artifact reader is not an untrusted upload/security boundary.
3. Defer nearest-neighbour search, learned estimates and a larger library. First
   demonstrate benefit over short fresh solving. Full hand-support/tree mismatch
   currently abstains; automatic matching and richer games are unvalidated.

No hosted readiness claim follows. Keep Issue #26's actual failed latency gates,
historical resource failures, and the independent numerical corpora unchanged.
