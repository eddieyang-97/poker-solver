# Two-player 吹牛 / Liar's Dice — standalone research

**Research only.** No dependency on the NLHE engine, hosted service, MCP/plugin, or production interfaces. See [Issue #40](https://github.com/eddieyang-97/poker-solver/issues/40) for follow-on research.

## Rules supplied in chat
Two players, five fair six-sided dice each, minimum opening quantity 3. 飞 (fly): ones are wild; 斋 (zhai): ones are not wild. A five-die hand containing only one named face and ones is counted as **6** of that face, while five equal dice count as **7**. Fly-to-zhai quantity may drop by one; zhai-to-fly increases by at least two. A lost challenge means drinking; no die elimination.

**Still to settle before a full-game solver:** whether bonus applies in zhai when the 5 dice include ones; treatment of all-ones and claiming face 1; whether per-player bonuses are added; precise face ordering, start mode, and raise legality. The current scripts assume per-player additive bonuses. Do not quietly resolve these through convention.

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

Use an appropriate executable path on Windows. The C++ script is a research prototype, not yet independently validated. Re-check the exact legal-action tree and regret/reach accounting before interpreting its NashConv as a convergence guarantee.
