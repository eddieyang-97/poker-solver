"""Outcome-sampling MCCFR, signed cumulative regrets, unbiased reach corrections.

Derived from the counterfactual estimator; see research.md for equations/sources.
No sampled-regret clipping (sampling noise + CFR+ needs separate justification).
"""
from array import array
from dataclasses import dataclass
import math
import random


def normalize(values):
    total = sum(values)
    return [x / total for x in values] if total else [1 / len(values)] * len(values)


@dataclass
class Info:
    regret: array
    average: array
    visits: int = 0


class Solver:
    def __init__(self, game, seed=761245, exploration=0.6, max_infos=100000,
                 opponent_exploration=0.05):
        if not 0 < exploration <= 1 or not 0 < opponent_exploration <= 1 or max_infos < 1:
            raise ValueError("Exploration must be in (0,1]; positive information-set budget")
        self.game, self.rng = game, random.Random(seed)
        self.exploration, self.max_infos = exploration, max_infos
        self.opponent_exploration = opponent_exploration
        self.infos = {}
        self.iterations = 0
        self.max_importance = 0.0

    def policy(self, player, hand, history, average=True):
        actions = self.game.actions(history)
        node = self.infos.get(self.game.key(player, hand, history))
        if node is None:
            return [1 / len(actions)] * len(actions)
        return normalize(node.average if average else [max(0, x) for x in node.regret])

    def episode(self, update, hands, history=(), own=1.0, other=1.0, sample=1.0):
        player = len(history) % 2
        actions = self.game.actions(history)
        key = self.game.key(player, hands[player], history)
        if key not in self.infos:
            if len(self.infos) >= self.max_infos:
                raise MemoryError("Information-set budget reached; run is incomplete")
            self.infos[key] = Info(array("d", [0]) * len(actions), array("d", [0]) * len(actions))
        node = self.infos[key]
        strategy = normalize([max(0, x) for x in node.regret])
        # Full support for BOTH players is necessary for the simple average
        # estimator, including hands where the opponent's target policy assigns
        # zero probability to this history. Tail correction handles either seat.
        epsilon = self.exploration if player == update else self.opponent_exploration
        sampling = [(1 - epsilon) * p + epsilon / len(actions) for p in strategy]
        chosen = self.rng.choices(range(len(actions)), weights=sampling)[0]
        action = actions[chosen]
        if action == -1:
            child = self.game.payoff(history, hands, player) * (1 if update == 0 else -1)
        else:
            child = self.episode(update, hands, history + (action,),
                                 own * strategy[chosen] if player == update else own,
                                 other if player == update else other * strategy[chosen],
                                 sample * sampling[chosen])
        action_estimate = child / sampling[chosen]
        value = strategy[chosen] * action_estimate
        if player == update:
            # Chance samples from the true prior: its factor cancels in other/sample.
            # Its factor is constant within an infoset and cancels in average normalization.
            weight = other / sample
            self.max_importance = max(self.max_importance, weight, own / sample)
            for i, p in enumerate(strategy):
                node.regret[i] += weight * ((action_estimate if i == chosen else 0) - value)
                node.average[i] += own / sample * p
                if not math.isfinite(node.regret[i]) or not math.isfinite(node.average[i]):
                    raise ArithmeticError("Non-finite importance estimate")
            node.visits += 1
        return value

    def train(self, iterations):
        for _ in range(iterations):
            for update in (0, 1):
                self.episode(update, self.game.sample(self.rng))
            self.iterations += 1
