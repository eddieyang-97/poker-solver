"""Finite-horizon response bounds against a frozen complete opponent policy.

Hidden opponent hands are pooled before maximizing each own-hand action.
Frontier play challenges immediately; optimistic frontier utility is +1.
Bounds use floating-point arithmetic, not outward-rounded interval arithmetic.
"""
from functools import lru_cache

import numpy as np


class PopulationModel:
    """Sparse behavioral probabilities of a frozen root policy mixture."""
    def __init__(self, target, cache_size=256):
        self.target, self.game = target, target.game
        self.actions = lru_cache(maxsize=cache_size)(self._actions)

    def _actions(self, player, history):
        legal = self.game.actions(history)
        weights = self.target.weights[player, :, None]*self.target._support(player, history)
        denominator = weights.sum(axis=0)
        rows = np.divide(weights, denominator[None, :], out=np.zeros_like(weights),
                         where=denominator[None, :] > 0)
        result = {}
        for component, probabilities in zip(self.target.components, rows):
            if not probabilities.any():
                continue
            chosen = np.asarray(component.choices(player, history))
            if chosen.shape != denominator.shape or not np.isin(chosen, legal).all():
                raise ValueError('Invalid frozen component action')
            for action in np.unique(chosen[probabilities > 0]):
                action = int(action)
                result.setdefault(action, np.zeros(len(denominator)))
                result[action] += probabilities*(chosen == action)
        unreachable = denominator == 0
        if unreachable.any():
            for action in legal:
                result.setdefault(action, np.zeros(len(denominator)))
                result[action][unreachable] = 1/len(legal)
        total = sum(result.values())
        if not np.allclose(total, 1, atol=1e-12, rtol=0):
            raise ValueError('Unnormalized frozen policy')
        for probabilities in result.values():
            probabilities.flags.writeable = False
        return result


class ResponseSearch:
    """One seat's best-response interval and deployable lower-value policy.

    depth counts own decisions. max_nodes limits expanded own public nodes;
    all legal actions and every nonzero opponent response are still integrated
    at each expanded node. Budget exhaustion uses legal frontier play.
    """
    def __init__(self, game, guide, model, seat, depth=1, max_nodes=256):
        if seat not in (0, 1) or type(depth) is not int or depth < 1 or type(max_nodes) is not int or max_nodes < 1:
            raise ValueError('Seat 0/1 and positive integer search budgets required')
        self.game, self.guide, self.model, self.seat = game, guide, model, seat
        self.depth, self.max_nodes = depth, max_nodes
        self.decisions = {}
        self.stats = {'expanded_own_nodes':0, 'depth_frontiers':0, 'budget_frontiers':0,
                      'forced_challenges':0, 'opponent_nodes':0, 'maximum_history':0}
        self.result = None

    def _claim_value(self, action, mass, challenging):
        column = self.guide.columns[action]
        counts = self.guide.counts[:, column].astype(int)
        histogram = np.bincount(counts, weights=mass, minlength=8)
        tails = np.r_[np.cumsum(histogram[::-1])[::-1], 0.]
        needed = np.clip(self.guide.quantities[column]-counts, 0, 8)
        truth = tails[needed]
        value = 2*truth-mass.sum()
        return -value if challenging else value

    def _branches(self, player, history, mass):
        self.stats['opponent_nodes'] += 1
        branches = [(action, mass*probability) for action, probability in self.model.actions(player, history).items()]
        # Visit common observations first; do not discard small nonzero masses.
        return sorted(((a, m) for a, m in branches if m.sum() > 0), key=lambda item:(-float(item[1].sum()), item[0]))

    def _search(self, history, mass, remaining):
        self.stats['maximum_history'] = max(self.stats['maximum_history'], len(history))
        legal = self.game.actions(history)
        challenge = self._claim_value(history[-1], mass, True) if history else None
        if legal == (-1,):
            self.stats['forced_challenges'] += 1
            return challenge, challenge.copy()
        if remaining == 0 or self.stats['expanded_own_nodes'] >= self.max_nodes:
            if challenge is None:
                raise AssertionError('Opening must be expanded to produce legal frontier play')
            self.stats['depth_frontiers' if remaining == 0 else 'budget_frontiers'] += 1
            return challenge, np.full(len(mass), mass.sum())
        self.stats['expanded_own_nodes'] += 1
        best_lower, best_upper = np.full(len(mass), -np.inf), np.full(len(mass), -np.inf)
        chosen = np.full(len(mass), legal[0], dtype=int)
        for action in legal:
            if action == -1:
                lower, upper = challenge, challenge
            else:
                lower, upper = np.zeros(len(mass)), np.zeros(len(mass))
                prefix = history+(action,)
                for response, child_mass in self._branches(1-self.seat, prefix, mass):
                    if response == -1:
                        value = self._claim_value(action, child_mass, False)
                        lower += value
                        upper += value
                    else:
                        child_lower, child_upper = self._search(prefix+(response,), child_mass, remaining-1)
                        lower += child_lower
                        upper += child_upper
            better = lower > best_lower
            chosen[better] = action
            best_lower = np.maximum(best_lower, lower)
            best_upper = np.maximum(best_upper, upper)
        chosen.flags.writeable = False
        self.decisions[history] = chosen
        return best_lower, best_upper

    def solve(self):
        if self.result is not None:
            return self.result
        prior = np.asarray(self.game.prior)
        if self.seat == 0:
            lower, upper = self._search((), prior, self.depth)
        else:
            lower, upper = np.zeros(len(prior)), np.zeros(len(prior))
            for action, mass in self._branches(0, (), prior):
                if action == -1:
                    raise ValueError('Opponent challenged at opening')
                child_lower, child_upper = self._search((action,), mass, self.depth)
                lower += child_lower
                upper += child_upper
        lo, hi = float(prior @ lower), float(prior @ upper)
        if not np.isfinite([lo, hi]).all() or lo > hi+1e-12:
            raise ArithmeticError('Invalid response bounds')
        self.result = {'seat':self.seat, 'depth':self.depth, 'max_nodes':self.max_nodes,
                       'lower':lo, 'upper':hi, 'width':hi-lo, 'stats':self.stats.copy(),
                       'formally_interval_certified':False}
        return self.result

    def choices(self, player, history):
        if player != self.seat or len(history)%2 != player:
            raise ValueError('Wrong responder seat')
        if self.result is None:
            raise ValueError('Solve before deploying a frozen response')
        if history in self.decisions:
            return self.decisions[history]
        # Complete play at unsearched or off-target histories. All non-opening
        # states admit a challenge, including histories with zero target reach.
        return np.full(len(self.game.prior), -1 if history else self.game.actions(())[0], dtype=int)

    def policy(self, player, hand, history):
        chosen = self.choices(player, history)[hand]
        return [float(a == chosen) for a in self.game.actions(history)]
