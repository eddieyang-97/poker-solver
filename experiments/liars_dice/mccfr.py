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


def corrected_values(child, probability, chosen, baseline):
    """Control variate: b[a] + 1[a=sample] * (X-b[a])/q[a]."""
    values = list(baseline)
    values[chosen] += (child - values[chosen]) / probability
    return values


@dataclass
class Info:
    regret: array
    average: array
    visits: int = 0


class Solver:
    def __init__(self, game, seed=761245, exploration=0.6, max_infos=100000,
                 opponent_exploration=0.05, initial_policy=None,
                 initial_regret=0.0, baseline=None):
        if not 0 < exploration <= 1 or not 0 < opponent_exploration <= 1 or max_infos < 1:
            raise ValueError("Exploration must be in (0,1]; positive information-set budget")
        if not math.isfinite(initial_regret) or initial_regret < 0 or (initial_regret and initial_policy is None):
            raise ValueError("Nonnegative finite initial regret requires an initial policy")
        self.game, self.rng = game, random.Random(seed)
        self.exploration, self.max_infos = exploration, max_infos
        self.opponent_exploration = opponent_exploration
        self.initial_policy, self.initial_regret, self.baseline = initial_policy, initial_regret, baseline
        self.infos = {}
        self.iterations = 0
        self.max_importance = 0.0
        self.max_value_estimate = 0.0

    def fallback(self, player, hand, history):
        actions = self.game.actions(history)
        if self.initial_policy is None:
            return [1 / len(actions)] * len(actions)
        row = self.initial_policy(player, hand, history)
        if (len(row) != len(actions) or not all(math.isfinite(p) and p >= 0 for p in row)
                or not math.isclose(sum(row), 1, rel_tol=0, abs_tol=1e-10)):
            raise ValueError("Invalid initial policy row")
        return row

    def policy(self, player, hand, history, average=True):
        node = self.infos.get(self.game.key(player, hand, history))
        if node is None:
            return self.fallback(player, hand, history)
        values = node.average if average else [max(0, x) for x in node.regret]
        return normalize(values) if sum(values) else self.fallback(player, hand, history)

    def episode(self, update, hands, history=(), own=1.0, other=1.0, sample=1.0):
        player = len(history) % 2
        actions = self.game.actions(history)
        key = self.game.key(player, hands[player], history)
        if key not in self.infos:
            if len(self.infos) >= self.max_infos:
                raise MemoryError("Information-set budget reached; run is incomplete")
            regret = (array("d", (self.initial_regret * p for p in self.fallback(player, hands[player], history)))
                      if self.initial_regret else array("d", [0]) * len(actions))
            self.infos[key] = Info(regret, array("d", [0]) * len(actions))
        node = self.infos[key]
        positive = [max(0, x) for x in node.regret]
        strategy = normalize(positive) if sum(positive) else self.fallback(player, hands[player], history)
        # Evaluate the fixed baseline before observing the sampled action/child.
        baseline = None
        if self.baseline is not None:
            baseline = self.baseline(player, hands[player], history)
            if len(baseline) != len(actions) or not all(math.isfinite(v) for v in baseline):
                raise ValueError("Invalid baseline row")
            if player != update:
                baseline = [-v for v in baseline]
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
        if baseline is None:
            action_estimate = child / sampling[chosen]
            action_values = None
            value = strategy[chosen] * action_estimate
        else:
            action_values = corrected_values(child, sampling[chosen], chosen, baseline)
            value = sum(p * v for p, v in zip(strategy, action_values))
        self.max_value_estimate = max(self.max_value_estimate, abs(value))
        if player == update:
            # Chance samples from the true prior: its factor cancels in other/sample.
            # Its factor is constant within an infoset and cancels in average normalization.
            weight = other / sample
            self.max_importance = max(self.max_importance, weight, own / sample)
            for i, p in enumerate(strategy):
                estimate = action_values[i] if action_values is not None else (action_estimate if i == chosen else 0)
                node.regret[i] += weight * (estimate - value)
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
