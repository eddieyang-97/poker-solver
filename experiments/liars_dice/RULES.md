# Provisional round model — owner confirmation outstanding

Issue [#40](https://github.com/eddieyang-97/poker-solver/issues/40) and the supplied chat rules are the authority. The following **research profile is not a confirmation of house rules**. No complete-game GTO claim is valid until the open items below are settled. These experiments concern a single independently rerolled round.

## Agreed inputs

- Two players each privately observe five fair, independent six-sided dice.
- Minimum opening quantity is three. A bid names quantity, face and 飞/斋 mode.
- Ones are wild in 飞; ones are not wild in 斋.
- A qualifying target-face/ones hand counts as six; five identical dice count as seven. The qualification boundaries remain open.
- 飞→斋 allows quantity minus one; 斋→飞 requires quantity plus at least two.
- Challenge ends the round. The loser drinks; no dice are removed.

## Explicit default assumptions

| Question requiring confirmation | Implemented default / available sensitivity |
| --- | --- |
| Which player opens? | Fixed player 0 for a single-round game. Player 1 responds. Next-round opening assignment and repeated-game objective are not modelled. |
| May either mode open? | Yes; alternate profile opens 飞 only. |
| Is face 1 biddable? Does it force 斋 or alter ordering? | Face 1 allowed in either mode, numerically lowest; it counts actual ones only, with seven for five ones. Alternate profile excludes face 1. No implicit mode switch. |
| What does all-ones count as in 飞 for another face? | Seven; sensitivity uses six. Other possible house rules remain unimplemented. |
| Does 44411 receive a bonus in 斋? | Counts three fours; alternate profile counts six. 44444 counts seven in either mode. |
| Are the two hands' bonuses independent and additive? | Yes: 44444 versus 44444 totals fourteen fours. Nonadditive rules require a different terminal model. |
| Same-mode face changes? | Higher quantity permits any face; equal quantity requires a strictly higher face. No wraparound or arbitrary same-quantity face switch. |
| Face change on mode switch? | Any face, regardless of its previous rank. Only quantity threshold applies. |
| May 飞→斋 go below three? | Yes, opening 3飞 may become 2斋. Alternate profile keeps all quantities at least three. |
| Must 飞→斋 reduce exactly one? | No: quantity may stay equal or increase. Reverse transition increases by at least two. |
| Maximum quantity? | Cap at fourteen, including potentially false bids. Quantities above fourteen are omitted as knowingly impossible under additive scoring; their formal legality still requires confirmation. This is an explicit finite action restriction. |
| Challenge meaning and stake? | A bid is true iff the summed contribution is **at least** its quantity. False: bidder loses; true: challenger loses. Equal, constant stakes; no exact-hit bonus, doubling, reroll, pass or other challenge action. |

For non-one target face f: in 飞, count occurrences of f or 1; if all five qualify, count six for a mixture, seven for five f or (by default) five ones. In 斋, count occurrences of f, upgrading five f to seven. For face 1, count ones once, upgrading five to seven. Bonuses are target-specific: five twos do not count as seven fours. `game.py` tests all 7,776 ordered rolls against the archive on face four, with additional edge cases and an independent binomial check.

## Extensive-form definition

Chance draws two independent private multisets with exact multiplicity `5! / product(count(face)!)`, divided by 7,776. There are 252 multisets per player; this compression discards only unobservable die ordering, not information relevant to this round.

Public history is the entire ordered sequence of bids. Player to act is its length modulo two. Opening actions are legal bids with quantity at least three; later actions are challenge or a bid satisfying the table above. A challenge is a terminal action, not a history token retained for another decision.

An information set is `(seat, own exact multiset, complete public history)`. The opponent's dice are never included. Two histories ending at the same bid remain distinct. No recall abstraction, private-hand clustering, face relabelling or strategy cache is used.

Terminal utility is +1 to the winner and −1 to the loser. Expected utility `u` corresponds to drinking probability `(1-u)/2`. This is a zero-sum, fixed-stake single-round model, not a model of alcohol consumption preferences or a multi-round drinking contest.

Legality is acyclic: lexicographic rank `(2*quantity + (3 if 斋 else 0), face)` strictly increases at every bid. Under the default assumptions the longest legal path has 150 bids; exact dynamic counting gives approximately `1.4053e45` public decision histories and `3.5413e47` information sets. See `outputs/summary.json` for exact integers. These include all legal, often irrational histories; there is no claim that all must be visited to learn useful play.

## Acceptance boundary

Owner confirmation of the table is still required. Testing implementations of assumptions does not verify those assumptions. Even after confirmation, a model covering all actions needs an independently credible exploitability upper bound before being described as a complete-game equilibrium. The runs here fail that standard by a large margin.
