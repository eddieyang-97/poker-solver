# Local action-frequency range explorer

This is the first Phase 2 follow-up for Issue #11: editable, explicitly supplied
action models and sensitivity reports. It is post-session range conditioning,
not earlier-street solving, population calibration, node locking or a new MCP tool.
The existing solver engines, review adapter, hosting and authorization stay intact.

Inputs are a reconstructed hand and a separate model document. `through` selects
an actual observed action by street and zero-based index. Only that action and
its prefix are used; later public cards/actions and all hole-card claims are
excluded. Public cards enter chronologically. Reports after an early action must
not accidentally condition on a later board or showdown reveal.

The document contains two or three `priors` keyed by seated position, a
`target_pair` of modeled players, and one to three named `profiles`. Priors have
`range` and `provenance`; they describe relative private-hand weights **before
the first preflop action**, not river arrivals to be conditioned twice. Each
expanded prior has at most 24 positive concrete combos. Participants outside
the model are explicitly omitted, including their latent-card/selection effects.
Priors use the existing range parser's binary64 weights, rank-class expansion
and last-token override convention. Positive tokens that underflow during that
parsing are rejected; they are never silently treated as zero. Decimal product
arithmetic begins from the parsed weights, not arbitrary-precision original text.

Each profile contains models keyed by an actual `(street, index)`, with
`provenance`, a finite list of alternative legal action objects (each with an
`id`), and `frequencies`: a complete concrete-combo-to-action-ID probability
table for that actor's original prior. The actor is bound to that history event;
alternative objects omit `player`. Alternatives are checked by replaying the
history prefix; exactly one must match the observed action by actor, kind and
exact amount. Every row has probabilities in [0,1] with decimal sum exactly 1;
there is no silent renormalization or invented default. Frequencies accept
numbers or bounded decimal strings (350 characters), zero or values from 1e-300
through 1; the row-sum check uses a private 1,200-digit context. Decimal strings
can express a very small action probability and its accurate complement.
Omitted legal actions/sizes have **zero modeled probability** in this caller's
finite action abstraction; this is a declared assumption, not a complete poker
policy learned from data. At most six alternatives
and 24 supplied action models per profile are allowed. Missing models record
unknown likelihoods and perform no update. Supplied rows condition on the public
prefix and actor's hand, never another player's private hand.

The calculation enumerates compatible private deals, initially weighted by the
product of the supplied priors. On each public reveal, impossible deals are
removed. On a modeled observed action, multiply each surviving deal's weight by
the supplied probability for the actor's hand. A modeled folded player remains
in the deal as latent dead cards; folding does not put their cards back. A
zero-probability observed line is reported as impossible, not ignored.

Arithmetic uses a private 600-digit Decimal context. Relative per-deal products
are retained between updates, subject to that precision; sums/divisions use it
as well. Authoritative
probabilities and masses are decimal strings; float display values can underflow
for extremely small support. No claim of symbolic/rational exactness is made.
At most 24^3 candidate deals and 24 models per profile bound local work; input
files are capped at 256 KiB. Reports contain normalized marginal and target-pair
joint distributions, model/gap traces, event probabilities and sensitivity to the
first profile (total variation and per-combo deltas).

The report also compares the true target-pair joint posterior to the distribution
obtained by treating its marginals as independent arrival weights and applying
pairwise blockers again. These generally differ, even with only two players.
Marginals must **not** be silently fed into the current solver. There is no
automatic solver dispatch/export: correlated deals and marginalized folded
players require a separately validated adapter or an explicit approximation.
The result is computed conditioning under supplied assumptions, never a
solver-verified strategy or a calibrated population range.

## Run and edit a study

Use the project virtual environment and `OPENBLAS_NUM_THREADS=1`:

```powershell
.venv/Scripts/python.exe scripts/explore_ranges.py examples/hand-review.json --models examples/range-models.json --output .artifacts/range-study
.venv/Scripts/python.exe scripts/benchmark_range_explorer.py --output .artifacts/range-explorer
.venv/Scripts/python.exe -m unittest discover -s tests -p test_range_explorer.py -v
```

The CLI takes a structured hand accepted by the existing history accountant.
Use the existing history parser to normalize bounded prose first. Edit
`examples/range-models.json`, or pass repeated `--set POINTER=JSON` edits to
existing model-document fields. All edits are applied before validation; when
changing a two-action probability row, change its complement too. A model past
the new `through` cut is an error and must be removed explicitly, not silently
ignored. Unknown/malformed/illegal models are rejected before any result report
is returned. An unknown likelihood has no Bayesian update and remains a gap;
`computed` means conditioning under the supplied **subset** of action models,
not a complete calibrated posterior for the observed line.

The disposable worker has a 60-second parent wall deadline, tested with actual
termination. Direct `explore(hand, models)` library calls have dimension bounds
but no process deadline. The CLI measures CPU and worker/parent wall time;
worker timing excludes module imports, while parent wall includes startup.
No CPU, memory or hosted capacity bound is established by these measurements.
Input JSON duplicate object keys are rejected. There is no web UI, provider
dependency, network access or credential entry in this workflow.

Outputs retain the sanitized history prefix, exact input model, conditional
likelihoods, unmodeled actions, marginals, target-pair joint posterior, sensitivity
and LF-normalized source hashes. `request_sha256` covers the actual sanitized
inference inputs; it is an integrity check, not signed proof that an arbitrary
uploaded result executed. All hole-card claims are excluded, including hero
cards; a user seeking a conditional perspective must explicitly supply that
prior rather than relying on an implicit reveal. Board-card survival ratios in
the trace are not probabilities of dealing the exact board. Readable displays
use six significant digits; very small values can underflow in float display,
while the JSON decimal strings retain positive support.

The example has three hypothetical priors before preflop and three editable
profiles. It conditions on a supplied UTG opening model and different UTG+1 flop
fold models, through the fold at flop index 4. The remaining eleven action
likelihoods are unknown, including the preflop calls/3-bet and flop bet/call.
This intentionally sparse example is a sensitivity illustration, not an estimate
of actual live opponents. It does not use the revealed 88 as the opponent range.

## Validation boundary

Tests include hand-derived two/three-player probabilities, twenty randomized
models cross-checked by a separate exact `Fraction` deal enumerator, card removal,
folded-player correlation, uniform tiny scales, ambient Decimal-context changes,
future/reveal exclusion, impossible observations, legal action replay, amount
binding, malformed rows, bounds, actual worker execution and deadline recovery.
The development benchmark runs the example and two maximum-dimension workers,
with independent analytical checks for the example's three posterior values.
CI retains full requests/results and source hashes in `range-explorer-validation`.
The [21 October measured snapshot](range-explorer-results.md) and
[inputs/source/raw/profile digests and decimal results](range-explorer-results.json)
record actual local execution. All **115 tests**, Ruff and compileall passed;
the existing **10 river cases plus sensitivity** also pass. The example and
both maximum-dimension workers completed. The latter took about 1.249/0.917
seconds parent wall on Windows 11/Python 3.14.8; these are measured samples, not
universal bounds. The disjoint-card probe enumerates all 13,824 compatible deals,
with 24 action models for each of three profiles. Full raw outputs remain in
local/CI artifacts, with source and profile digests verified against this code.

The illustrative example's UTG AA posterior is **0.25**, **4/7** and **40/61**
under baseline/neutral/reversed third-player fold selection. These are computed
conditional probabilities under the declared models, not poker action
frequencies. The example's eleven unknown action likelihoods remain gaps.
Treating the baseline target-pair marginals as independent arrival weights gives
total variation distance about **0.220519** from the actual joint posterior even
after applying pairwise blockers. This demonstrates why no solver export is
performed. Local checks do not establish a final-head CI pass; consult the PR's
current run and retained artifact separately.

The existing hand-review CLI and all solver/transport registrations are unchanged.
True node locking, calibrated frequency models, automatic solver integration and
future turn/flop/multiway strategy solving remain open in Issue #11. This local
range explorer completes only its editable-model/conditioning follow-up.
