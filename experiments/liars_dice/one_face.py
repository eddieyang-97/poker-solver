"""Independent tuple-history evaluator and small exact CFR+ reference.

No C++ traversal helpers or trainer state used in evaluation. Numpy is local
research only (already a repository dependency).
"""
from functools import lru_cache
import numpy as np


VALUES = (0, 1, 2, 3, 4, 6, 7)
PRIOR = (1024/7776, 2560/7776, 2560/7776, 1280/7776, 320/7776, 30/7776, 2/7776)


class OneFace:
    def __init__(self, maximum=14):
        if not 3 <= maximum <= 14:
            raise ValueError("maximum must be 3..14")
        self.maximum = maximum
        self.prior = PRIOR
        self.hands = VALUES

    def actions(self, history):
        return tuple(([-1] if history else []) + list(range(history[-1] + 1 if history else 3, self.maximum + 1)))

    def payoff(self, history, hands, challenger):
        valid = VALUES[hands[0]] + VALUES[hands[1]] >= history[-1]
        return 1.0 if (challenger == 0) != valid else -1.0

    def sample(self, rng):
        return tuple(rng.choices(range(7), weights=PRIOR, k=2))

    def key(self, player, hand, history):
        return player, hand, history


def evaluate(game, policy):
    """Exact NashConv: maximize after pooling hidden opponent types, not before.

    policy(player, hand-index, complete-public-history) -> action probabilities.
    Returns each BR in that player's own utility, and NashConv (sum of BRs).
    """
    n = len(game.prior)
    prior = np.array(game.prior)

    @lru_cache(None)
    def strategies(history):
        p = len(history) % 2
        table = np.array([policy(p, t, history) for t in range(n)])
        if (not np.isfinite(table).all() or (table < 0).any()
                or not np.allclose(table.sum(axis=1), 1, atol=1e-10, rtol=0)):
            raise ValueError("Invalid policy")
        return table

    def terminal(history, challenger):
        return np.array([[game.payoff(history, (a, b), challenger)
                          for b in range(n)] for a in range(n)])

    def selfplay(history):
        p = len(history) % 2
        result = np.zeros((n, n))
        s = strategies(history)
        for i, action in enumerate(game.actions(history)):
            child = terminal(history, p) if action == -1 else selfplay(history + (action,))
            result += child * (s[:, i, None] if p == 0 else s[None, :, i])
        return result

    def response(history, self, belief):
        p = len(history) % 2
        candidates = []
        s = strategies(history)
        for i, action in enumerate(game.actions(history)):
            mass = belief if p == self else belief * s[:, i]
            if action == -1:
                utility = terminal(history, p) * (1 if self == 0 else -1)
                child = utility @ mass if self == 0 else mass @ utility
            else:
                child = response(history + (action,), self, mass)
            candidates.append(child)
        # One action per own hand/public history; never observe opponent hand.
        return np.max(candidates, axis=0) if p == self else np.sum(candidates, axis=0)

    ev = float(prior @ selfplay(()) @ prior)
    br0 = float(prior @ response((), 0, prior))
    br1 = float(prior @ response((), 1, prior))
    return {"ev_p0": ev, "br0": br0, "br1": br1,
            "gain0": br0 - ev, "gain1": br1 + ev,
            "nashconv": br0 + br1, "exploitability": (br0 + br1) / 2}


def exported_policy(path):
    table = np.fromfile(path, dtype="<f8").reshape((4096, 7, 13))

    def policy(player, hand, history):
        mask = sum(1 << (q - 3) for q in history)
        return table[mask, hand, :len(OneFace().actions(history))]
    return policy


class ExactCFR:
    """Enumerate all deals, accumulate before clipping, alternate player updates.

    Reach-weighted linear average. Small-game oracle; not a full-game algorithm.
    """
    def __init__(self, game):
        self.game = game
        self.regrets, self.averages = {}, {}
        self.iterations = 0

    def current(self, history):
        if history not in self.regrets:
            shape = (len(self.game.prior), len(self.game.actions(history)))
            self.regrets[history] = np.zeros(shape)
            self.averages[history] = np.zeros(shape)
        positive = self.regrets[history].clip(0)
        sums = positive.sum(axis=1, keepdims=True)
        return np.divide(positive, sums, out=np.full_like(positive, 1 / positive.shape[1]), where=sums > 0)

    def policy(self, player, hand, history):
        if history not in self.averages or self.averages[history][hand].sum() == 0:
            return [1 / len(self.game.actions(history))] * len(self.game.actions(history))
        row = self.averages[history][hand]
        return row / row.sum()

    def train(self, iterations):
        prior = np.array(self.game.prior)
        n = len(prior)
        for _ in range(iterations):
            for update in (0, 1):
                def walk(history, r0, r1):
                    p = len(history) % 2
                    s = self.current(history)
                    children = []
                    for i, action in enumerate(self.game.actions(history)):
                        if action == -1:
                            child = np.array([[self.game.payoff(history, (a, b), p)
                                               for b in range(n)] for a in range(n)])
                        else:
                            child = walk(history + (action,), r0 * s[:, i] if p == 0 else r0,
                                         r1 * s[:, i] if p == 1 else r1)
                        children.append(child)
                    v = sum(child * (s[:, i, None] if p == 0 else s[None, :, i])
                            for i, child in enumerate(children))
                    if p == update:
                        for i, child in enumerate(children):
                            advantage = (child - v) @ (prior * r1) if p == 0 else (prior * r0) @ (v - child)
                            self.regrets[history][:, i] = np.maximum(0, self.regrets[history][:, i] + advantage)
                        self.averages[history] += (self.iterations + 1) * (r0 if p == 0 else r1)[:, None] * s
                    return v
                walk((), np.ones(n), np.ones(n))
            self.iterations += 1
