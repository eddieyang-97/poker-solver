"""Exact belief update under an EXPLICIT assumed opponent behavioural policy."""
import math


def posterior(game, own_seat, history, opponent_policy):
    """Own actions carry no extra opponent-hand likelihood given own information.

    Returns opponent hand weights. Raises on impossible policy evidence rather
    than resetting to a prior. No claim that a supplied policy models a human.
    """
    if own_seat not in (0, 1):
        raise ValueError("own seat must be 0/1")
    mass = list(game.prior)
    prefix = ()
    for action in history:
        actions = game.actions(prefix)
        if action == -1 or action not in actions:
            raise ValueError("History must contain legal bids only")
        player = len(prefix) % 2
        if player != own_seat:
            index = actions.index(action)
            for hand in range(len(mass)):
                row = opponent_policy(player,hand,prefix)
                if (len(row) != len(actions) or not all(math.isfinite(p) and p >= 0 for p in row)
                        or not math.isclose(sum(row),1,rel_tol=0,abs_tol=1e-10)):
                    raise ValueError("Invalid opponent policy row")
                mass[hand] *= row[index]
            total = sum(mass)
            if total == 0:
                raise ValueError("History has zero support under the assumed policy")
            mass = [p/total for p in mass]
        prefix += (action,)
    return mass


def challenge_ev(game, own_seat, own_hand, history, opponent_policy):
    if not history:
        raise ValueError("Cannot challenge before a bid")
    if len(history) % 2 != own_seat:
        raise ValueError("It is not this player's turn")
    weights = posterior(game,own_seat,history,opponent_policy)
    ev = 0.0
    for opp, p in enumerate(weights):
        hands = (own_hand,opp) if own_seat == 0 else (opp,own_hand)
        ev += p*game.payoff(history,hands,own_seat)*(1 if own_seat == 0 else -1)
    return ev
