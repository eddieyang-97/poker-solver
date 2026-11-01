# Two-player 吹牛 / Liar's Dice — standalone research

**Research only.** No dependency on the NLHE engine, hosted service, MCP/plugin, or production interfaces. See [Issue #40](https://github.com/eddieyang-97/poker-solver/issues/40) for follow-on research.

## Owner-confirmed house rules
Two players, five fair six-sided dice each, minimum opening quantity 3. 飞 (fly): ones are wild; 斋 (zhai): ones are not wild. A five-die hand containing only one named face and ones is counted as **6** of that face, while five equal dice count as **7**. Fly-to-zhai quantity may drop by one; zhai-to-fly increases by at least two. A lost challenge means drinking; no die elimination.

**All previously listed house-rule questions were confirmed by the owner on 31 October 2026.** The default game model follows those decisions: all-ones count as seven for another face in 飞; mixed 斋 hands get no bonus; face 1 is biddable and counts actual ones only; per-player bonuses add; same-mode raises use quantity then ascending face; mode switches can change faces; an opening 3飞 can be followed by 2斋; either mode may open; 飞→斋 may reduce by one, stay level, or increase; and bids cap at 14. Round winner/loser receive fixed ±1 utility, and each loss means one drink. See [confirmed rules](RULES.md) for the complete specification. Confirmation of the game does **not** imply solver convergence.

## Snapshots included
- `liars_dice_analysis.py`: exact exhaustive enumeration of all 7,776 **opponent** 5-die sequences for bids on face 4. Probabilities are unconditional on opponents' actions. Fly treats a hand of 4s/1s as 6 except five equal as 7; zhai gives 7 only for five 4s.
- `one_face_cfr.cpp`: an **extremely restricted** toy two-player zero-sum game. Only bid “N fours, fly” for N=3..14, or challenge. No face changes and no zhai. It collapses each player's hidden hand to a face-4 contribution type. Uses a seeded sampling-based positive-regret CFR-style update and computes best responses to its average strategies in this toy tree.
- `results.md`: observed outputs and provenance; numbers are not GTO for the real game.

## Reproduce
```sh
python experiments/liars_dice/liars_dice_analysis.py
g++ -O3 -std=c++17 experiments/liars_dice/one_face_cfr.cpp -o /tmp/one_face_cfr
/tmp/one_face_cfr 200000
```

Use an appropriate executable path on Windows. These original archive commands run a restricted research prototype; the follow-on audit below independently checks its measured average-policy gap without certifying full-game convergence.

## Follow-on independent validation

The archive's 200,000-iteration results now reproduce, including an independent evaluation of its entire exported average policy: toy NashConv **0.026688617**. Exact CFR+ on a smaller 3..5 bid game reaches **0.000003731**. Full-rule outcome sampling and a smaller action-set experiment both **fail** useful convergence; their frequencies are not recommendations. Issue #40 remains open.

- [Owner-confirmed complete house rules](RULES.md).
- [Methods, independent checks, measured failures and next research step](research.md).
- [中文 / English strategy guide](strategy-guide.md).
- `game.py`: exact private multisets, contribution scoring, complete confirmed legal actions and single-round utilities.
- `one_face.py`, `audit_baseline.cpp`: independent toy evaluation and exact small-game CFR+.
- `mccfr.py`: full-history outcome sampling; `run_abstraction.py`: smallest-quantity-per-face/mode restriction evaluated in the full confirmed game.
- `beliefs.py`: exact Bayesian update under an explicitly supplied opponent policy, not an inferred human model.
- `outputs/`: raw seeded results, timing, exact probability numerators and response lower bounds. Full exported toy policy and compiler stay in ignored artifacts.

## Reproduce the follow-on study

Use the project virtual environment (Python 3.10+ and NumPy); no new runtime dependencies or hosted imports. From the repository root, POSIX commands are:

```sh
mkdir -p .artifacts/liars_dice
g++ -O3 -std=c++17 -Wall -Wextra -pedantic experiments/liars_dice/audit_baseline.cpp -o .artifacts/liars_dice/audit_baseline
.artifacts/liars_dice/audit_baseline 200000 .artifacts/liars_dice/baseline-policy.bin
python experiments/liars_dice/run_research.py --iterations 10000 --games 2000 --seeds 761245 42 --policy-bin .artifacts/liars_dice/baseline-policy.bin
python experiments/liars_dice/summarize.py
python experiments/liars_dice/run_abstraction.py --iterations 50000 --games 2000 --seeds 761245 42
python -m unittest discover -s experiments/liars_dice/tests -v
python -m ruff check experiments/liars_dice --exclude liars_dice_analysis.py
```

On Windows use `.venv/Scripts/python.exe`, an `.exe` output name, and put the compiler's runtime DLL directory on PATH. The recorded build used portable WinLibs GCC 14.2.0 (release `14.2.0posix-12.0.0-ucrt-r3`), compiler archive SHA256 `88868d745b807f083a117ff69348d8bc021ad7389aa503379dbed1866efcaeb9`. No binaries are committed. Standard-library random distributions can differ across C++ implementations; compare policies by exact evaluation rather than demanding cross-toolchain byte identity.

The archived Python script retains an unused import, so only that unchanged archival file is excluded from the added research lint command. Existing repository checks remain unchanged. Timing and Python traced allocation figures are measurements on this Windows machine, not Linux resource-limit evidence. The adjacent experiment intentionally reports a budget stop; it must not be relabelled as 50,000 completed iterations.

Current validation commands and outcomes are recorded in [validation.md](validation.md). Neither these experiments nor that document alter the NLHE solver, hosted tools, OAuth, deployment or plugin interfaces.

## Confirmed-rule follow-on experiments

The [guidance/control-variate study](guided-research.md) adds a probability-informed fallback and fixed value baselines, independently checked estimators, two training seeds and posterior-aware response tests. Guidance improves coverage, but the best tested variant still has full-game NashConv lower bounds above **1.15**. An exact [untrained prior-policy control](outputs/prior-control.json) prevents crediting the heuristic's strength to learning.

The [finite-family study](family-research.md) enumerates all private deals for 225 complete-policy pairings and solves that restricted zero-sum game. Its family gap reaches **2.4e−9**, yet outside responses establish a full-game lower bound above **1.20**. These are full-rule policy approximations, not validated GTO strategies.

```sh
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_guided.py --seeds 761245 42 --checkpoints 1000 10000 --games 2000 --adaptive-games 1000 --max-infos 200000
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/prior_control.py
OPENBLAS_NUM_THREADS=1 python experiments/liars_dice/run_family.py --games 5000 --adaptive-games 2000
```

New receipts use LF-normalized source hashes and LF JSON output. Earlier receipts retain their original provenance. The required CI research step discovers both old and new standalone tests without changing the NLHE gates.
