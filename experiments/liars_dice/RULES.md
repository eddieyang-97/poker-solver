# Owner-confirmed two-player 吹牛 / Liar's Dice rules

**Confirmed by the owner on 31 October 2026.** These are the actual house rules for this research, as clarified in chat and confirmed together. The `Rules()` defaults in `game.py` implement them. Research sensitivity profiles intentionally vary individual rules and **do not** represent alternative confirmed house rules. Exact probabilities under these rules are distinct from equilibrium claims: **a validated full-game GTO strategy does not yet exist**.

## Confirmed rules

- **Players and round:** Two players, five independent fair six-sided dice each, with private hands. The first round is opened by player A (player 0 in the single-round model); the other player responds. Subsequent rounds re-roll all dice; no die elimination.
- **Opening:** At least 3 of any face, in either 飞 or 斋 mode. Faces 1 through 6 are biddable; face 1 is the lowest rank.
- **飞 (wild):** Ones act as the named face for faces 2–6. A bid on face 1 counts actual ones only (never double-counts them); five ones count as seven on a bid of ones.
- **斋 (non-wild):** Ones are not wild for other faces. Thus `44411` counts only three 4s in 斋; `44444` counts seven 4s.
- **Special five-die scoring:** If all five dice are made from a mixture of a named non-one face and ones, that hand contributes **six** of the named face in 飞 (e.g. `44411` gives six 4s). Five identical dice of a face contribute **seven** to that face in either mode; five ones also contribute seven to **each named non-one face in 飞**, but zero to those faces in 斋. The bonus is per-player, then contributions add (two `44411` hands yield twelve 4s 飞; two `44444` hands yield fourteen 4s).
- **Same-mode raise:** Higher quantity allows any named face; at the same quantity, only a strictly higher face is legal. Face rank is numerical, 1 through 6.
- **飞 → 斋:** The new quantity may be one less, equal, or greater (i.e. new quantity ≥ old quantity − 1). Changing face is allowed. In particular an opening `3飞` may be followed by `2斋`; the minimum of three applies to **opening**, not every subsequent bid.
- **斋 → 飞:** New quantity must be at least old quantity + 2; any face may be chosen.
- **Bid cap:** 14 is the maximum legal quantity, even though some lower impossible bids may be made. The permitted finite action space excludes 15+.
- **Challenge / 开:** At any non-opening decision, challenge the preceding bid. A bid is true if the sum of the two hands' effective contributions is **at least** the claimed quantity. If true, challenger loses; if false, bidder loses. Loser immediately drinks once. No exact-hit bonus, doubling, pass, reroll or additional challenge action.
- **Objective model:** One independent round, winner +1 / loser −1, equal fixed stake. This represents who drinks; it does not optimize cumulative alcohol consumption or multiple-round strategy.

### Counterfactual research profiles (not house rules)

For methodological sensitivity only, the experimental scripts can disable face-1 bids, change the all-ones contribution from seven to six, give mixed 斋 hands a six-count bonus, or restrict opening/after-switch quantities. Those profiles are **not** endorsed play rules. Historical output keys such as `baseline_assumptions` are names used when the experiments were run before confirmation; the default parameter values have since been confirmed and the recorded numerical results have not changed.

For non-one target face f: in 飞, count occurrences of f or 1; if all five qualify, count six for a mixture, seven for five f or five ones. In 斋, count occurrences of f, upgrading five f to seven. For face 1, count ones once, upgrading five to seven. Bonuses are target-specific: five twos do not count as seven fours. `game.py` tests all 7,776 ordered rolls against the archive on face four, with additional edge cases and an independent binomial check.

## Extensive-form definition

Chance draws two independent private multisets with exact multiplicity `5! / product(count(face)!)`, divided by 7,776. There are 252 multisets per player; this compression discards only unobservable die ordering, not information relevant to this round.

Public history is the entire ordered sequence of bids. Player to act is its length modulo two. Opening actions are legal bids with quantity at least three; later actions are challenge or a bid satisfying the table above. A challenge is a terminal action, not a history token retained for another decision.

An information set is `(seat, own exact multiset, complete public history)`. The opponent's dice are never included. Two histories ending at the same bid remain distinct. No recall abstraction, private-hand clustering, face relabelling or strategy cache is used.

Terminal utility is +1 to the winner and −1 to the loser. Expected utility `u` corresponds to drinking probability `(1-u)/2`. This is a zero-sum, fixed-stake single-round model, not a model of alcohol consumption preferences or a multi-round drinking contest.

Legality is acyclic: lexicographic rank `(2*quantity + (3 if 斋 else 0), face)` strictly increases at every bid. Under the confirmed rules the longest legal path has 150 bids; exact dynamic counting gives approximately `1.4053e45` public decision histories and `3.5413e47` information sets. See `outputs/summary.json` for exact integers. These include all legal, often irrational histories; there is no claim that all must be visited to learn useful play.

## Acceptance boundary

House-rule confirmation is complete. The remaining blocker is **solver quality**: a model covering all legal actions still needs independently credible convergence/exploitability evidence before being described as a complete-game equilibrium. The full-game runs here fail that standard by a large margin. No strategy frequencies from those runs should be represented as GTO.
