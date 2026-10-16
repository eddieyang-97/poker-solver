---
name: river-review
description: Review a heads-up NLHE river decision using measured call EV versus a supplied betting range, or restricted-tree CFR+ equilibrium approximation. Study and review only, not live play.
---

# River-only poker study workflow

You have the tools `evaluate_river_call` (exact against an assumed betting range) and `solve_river` (computed CFR+ under a no-raise, river-only tree). Prefer the former when Hero **faces a bet** and you have an opponent betting range; prefer the latter when analyzing the start of a river and both players' whole arrival ranges are available.

## Accuracy requirements

- Explicitly establish river board (5 cards, with suits), pot **before** the river betting action, effective *remaining* stack, IP/OOP, and both players' plausible arrival ranges, based on preflop and prior streets.
- Do not build ranges using only the actual hands revealed at showdown; analyze against the plausible *range* at the decision.
- If ranges cannot be reliably inferred, clearly state the assumptions; compute one or more plausible range scenarios rather than pretending to know the opponent's exact composition.
- For the solver, report the **allowed actions**: OOP and IP may check or bet 1–3 preset sizes, facing a bet may only call/fold. No raises, no rake, no preflop/flop/turn solving, no multiway support. Do not label frequencies “full GTO.”
- Cite the returned NashConv relative to pot, and if not sufficiently converged, increase iterations within the advertised tool limit (hosted maximum 1500; local maximum 10000) or warn that output is unstable. A small global gap does not establish accurate frequencies for rare/off-path individual hands.
- Distinguish each specific combo’s strategic frequency from action EV, and distinguish the returned model's conditional EV from game-wide EV.
- `action_ev_relative_to_half_pot` uses a symmetric chip baseline of half the initial pot; compare values *within the same node*. This is not a bankroll gain/loss since the start of the hand.
- Carefully explain blockers removing both value and bluff combinations. Evaluate the user's actual action without being results-oriented.
- After an OOP check, read `ip_after_oop_check` and the corresponding `oop_facing_ip_bet_*` response node. OOP checking is endogenous in this tree; it is not a fixed exogenous checking range. Inspect own reach before interpreting rarely reached nodes.
- Range arrival weights differ from betting weights. Use `evaluate_river_call` separately for population betting-range sensitivity; do not feed an entire arrival range into it as if all hands bet.
- Report tool errors and timeouts plainly; never substitute invented computed results. Near-equal action EVs can support multiple strategy mixtures; do not overinterpret exact mixed percentages.
- This plugin is for post-session study only; do not use it to provide real-time assistance during a real-money hand.

## Example

Use `evaluate_river_call` for board `Ks,9s,5h,Td,Ts`, pot 505, bet 450, Hero `KdQd`, and a hypothesized betting range such as `QJs,99:0.5,AsJh:0.25,AsQh:0.25` (illustrative only). Discuss how alternative proportions of value/bluffs change the call.

Use `solve_river` with two weighted full ranges if the action has not yet occurred, specifying `bet_sizes:[0.5,0.89]`, `oop_hand:"KdQd"`, `ip_hand:"AsJh"`, `iterations:700`. Read `hands[].node_strategy` by decision node.
