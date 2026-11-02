"""Exact payoffs for expanding populations of complete, deterministic policies.

Response construction is heuristic, not a full-game best-response oracle.
Every component sees only its own hand and the complete public history.
"""
from functools import lru_cache

import numpy as np


def prune_weights(weights, cutoff):
    """Explicit root support projection; return normalized weights and lost mass."""
    weights = np.asarray(weights, dtype=float)
    if (not 0 <= cutoff < 1 or weights.ndim != 1 or not weights.size
            or not np.isfinite(weights).all() or (weights < 0).any()
            or not np.isclose(weights.sum(), 1, rtol=0, atol=1e-10)):
        raise ValueError("Normalized weights and cutoff in [0,1) required")
    keep = weights >= cutoff
    keep[np.argmax(weights)] = True
    removed = float(weights[~keep].sum())
    result = np.where(keep, weights, 0.)
    return result/result.sum(), removed


class PriorComponent:
    def __init__(self, family, index):
        self.family, self.index = family, index

    def choices(self, player, history):
        return self.family.choices[self.index, :, self.family.state(history)]


class PopulationMixture:
    """Immutable root mixture, converted using the player's own action reach."""
    def __init__(self, game, components, weights0, weights1, cache_size=256):
        self.game, self.components = game, tuple(components)
        self.weights = np.array([weights0, weights1], dtype=float)
        if (self.weights.shape != (2, len(self.components)) or not self.components
                or not np.isfinite(self.weights).all() or (self.weights < 0).any()
                or not np.allclose(self.weights.sum(axis=1), 1, rtol=0, atol=1e-10)):
            raise ValueError("Two normalized component mixtures required")
        self.weights.flags.writeable = False
        self._support = lru_cache(maxsize=cache_size)(self._own_support)

    def _own_support(self, player, history):
        if not history:
            return np.ones((len(self.components), len(self.game.prior)), dtype=bool)
        previous = history[:-1]
        supported = self._support(player, previous)
        if len(previous) % 2 == player:
            result = supported.copy()
            for index in np.flatnonzero(self.weights[player] > 0):
                result[index] &= self.components[index].choices(player, previous) == history[-1]
            return result
        return supported

    def likelihood(self, player, history, action):
        legal = self.game.actions(history)
        if action not in legal:
            raise ValueError("Illegal requested action")
        weights = self.weights[player, :, None] * self._support(player, history)
        denominator = weights.sum(axis=0)
        numerator = np.zeros(len(self.game.prior))
        for component, weight in zip(self.components, weights):
            if weight.any():
                numerator += weight * (component.choices(player, history) == action)
        return np.divide(numerator, denominator, out=np.full_like(numerator, 1/len(legal)),
                         where=denominator > 0)

    def policy(self, player, hand, history):
        return [float(self.likelihood(player, history, a)[hand]) for a in self.game.actions(history)]


class BayesianComponent:
    """Posterior truth/aspiration heuristic against a frozen trembled model.

    The tremble belongs to the *belief model*, not to deployed deterministic
    play. It makes the response a complete policy even against a different
    population member. No actual opponent component identity is supplied.
    """
    def __init__(self, game, guide, target, threshold=.5, aspiration=None,
                 tremble=.02, cache_size=256):
        if (not 0 <= threshold <= 1 or not 0 < tremble <= 1
                or (aspiration is not None and not 0 <= aspiration <= 1)):
            raise ValueError("Invalid response parameters")
        self.game, self.guide, self.target = game, guide, target
        self.threshold, self.aspiration, self.tremble = threshold, aspiration, tremble
        self.belief = lru_cache(maxsize=cache_size)(self._belief)
        self.choices = lru_cache(maxsize=cache_size)(self._choices)
        # Only twelve distinct contribution views in the full game, one in the
        # toy. Aggregate posterior count histograms rather than all hand pairs.
        views, self.view_index = np.unique(guide.counts.T, axis=0, return_inverse=True)
        self.views = views.astype(int)

    def _belief(self, player, history):
        if not history:
            return self.guide.prior.copy()
        previous = history[:-1]
        weights = self.belief(player, previous)
        actor = len(previous) % 2
        if actor == player:
            return weights
        legal = self.game.actions(previous)
        if history[-1] not in legal:
            raise ValueError("Illegal observed history")
        likelihood = ((1-self.tremble)*self.target.likelihood(actor, previous, history[-1])
                      + self.tremble/len(legal))
        weights = weights * likelihood
        return weights/weights.sum()

    def truth(self, weights):
        histograms = np.array([np.bincount(view, weights=weights, minlength=8) for view in self.views])
        tails = np.cumsum(histograms[:, ::-1], axis=1)[:, ::-1]
        # Need <=0 is certain, need >=8 is impossible.
        tails = np.column_stack((tails, np.zeros(len(tails))))
        need = np.clip(self.guide.quantities[None, :] - self.guide.counts, 0, 8)
        return tails[self.view_index[None, :], need]

    def _choices(self, player, history):
        legal = self.game.actions(history)
        bids = sorted((a for a in legal if a != -1), key=lambda a:self.guide.ties[self.guide.columns[a]])
        if not bids:
            return np.full(len(self.game.prior), -1, dtype=np.int16)
        truth = self.truth(self.belief(player, history))
        columns = [self.guide.columns[a] for a in bids]
        values = truth[:, columns]
        best = values.max(axis=1)
        safest = np.array(bids)[np.argmax(values >= best[:, None]-1e-12, axis=1)]
        chosen = safest.copy()
        if self.aspiration is not None:
            supported = values >= self.aspiration-1e-12
            quantity = self.guide.quantities[columns]
            best_q = np.max(np.where(supported, quantity[None, :], -1), axis=1)
            eligible = supported & (quantity[None, :] == best_q[:, None])
            scores = np.where(eligible, values, -1)
            best = scores.max(axis=1)
            indices = np.argmax(eligible & (scores >= best[:, None]-1e-12), axis=1)
            chosen[best_q >= 0] = np.array(bids)[indices[best_q >= 0]]
        if history:
            chosen[truth[:, self.guide.columns[history[-1]]] < self.threshold] = -1
        chosen.flags.writeable = False
        return chosen

    def policy(self, player, hand, history):
        chosen = self.choices(player, history)[hand]
        return [float(a == chosen) for a in self.game.actions(history)]


def exact_pair(game, guide, first, second, max_nodes=100000):
    """Group all private pairs by full public history; retain integer weights.

    Unlike the old Markov table evaluator, this supports history-dependent
    components. At no point may action selection observe the other hand.
    """
    n = len(game.prior)
    h0, h1 = np.repeat(np.arange(n), n), np.tile(np.arange(n), n)
    weights = np.rint(np.asarray(game.prior)*7776).astype(np.int64)
    if weights.sum() != 7776 or not np.allclose(weights/7776, game.prior, atol=1e-15, rtol=0):
        raise ValueError("Expected five-dice chance weights")
    chance = weights[h0]*weights[h1]
    stack = [((), np.arange(n*n))]
    numerator, completed, nodes, maximum_depth = 0, 0, 0, 0
    while stack:
        history, deals = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise RuntimeError("Exact policy-pair node budget exceeded")
        if len(history) > 150:
            raise AssertionError("Nonterminating policy")
        maximum_depth = max(maximum_depth, len(history))
        player = len(history)%2
        component, hand = (first, h0) if player == 0 else (second, h1)
        all_choices = np.asarray(component.choices(player, history))
        if all_choices.shape != (n,) or not np.isin(all_choices, game.actions(history)).all():
            raise ValueError("Component chose an illegal action")
        choices = all_choices[hand[deals]]
        for action in np.unique(choices):
            subset = deals[choices == action]
            if action != -1:
                stack.append((history+(int(action),), subset))
                continue
            col = guide.columns[history[-1]]
            true = guide.counts[h0[subset], col]+guide.counts[h1[subset], col] >= guide.quantities[col]
            utility = (2*true.astype(np.int64)-1)*(1 if player == 1 else -1)
            numerator += int(utility @ chance[subset])
            completed += len(subset)
    if completed != n*n:
        raise AssertionError("Missing private deals")
    return numerator, {'public_nodes':nodes, 'maximum_bids':maximum_depth}
