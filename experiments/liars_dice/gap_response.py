"""Incremental full-history response bounds with best-first allocation."""
from dataclasses import dataclass, field

import numpy as np

from bounded_response import ResponseSearch


@dataclass
class Frontier:
    history: tuple
    mass: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    gap: np.ndarray
    actions: tuple = ()
    children: list = field(default_factory=list)
    action_lower: np.ndarray | None = None
    action_upper: np.ndarray | None = None
    optimistic: np.ndarray | None = None


class HistoryLimit(RuntimeError):
    """A complete expansion would exceed the allocated history cap."""


def priority_gap(lower, upper, reach):
    # Suppress cancellation noise in priority only. Report the backed-up
    # endpoints as calculated, including gaps below the search tolerance.
    gap = upper - lower
    return np.where(gap > 1e-13 * reach, gap, 0.)


class FrontierResponse(ResponseSearch):
    """Reuse expanded work across checkpoints. Bounds and choices ignore priority.

    Gap allocation follows each own hand's current optimistic action, then
    prioritizes the unresolved interval width of its opponent observations.
    Reach allocation instead follows opponent mass, including observations under
    actions that currently cannot attain the optimistic value.
    """

    def __init__(self, game, guide, model, seat, max_nodes, allocation='gap', max_histories=20000):
        super().__init__(game, guide, model, seat, depth=1, max_nodes=max_nodes)
        if allocation not in ('gap', 'reach') or type(max_histories) is not int or max_histories < 1:
            raise ValueError('Known allocation and positive integer history limit required')
        self.prior = np.asarray(game.prior)
        self.allocation, self.max_histories = allocation, max_histories
        self.roots = None
        self.stats.update(generated_histories=0, priority_visits=0, claim_values=0)
        self.stop_reason = None

    def _claim_value(self, action, mass, challenging):
        self.stats['claim_values'] += 1
        return super()._claim_value(action, mass, challenging)

    def _leaf(self, history, mass):
        self.stats['maximum_history'] = max(self.stats['maximum_history'], len(history))
        lower = self._claim_value(history[-1], mass, True) if history else None
        if self.game.actions(history) == (-1,):
            self.stats['forced_challenges'] += 1
            return lower, lower, None
        if self.stats['generated_histories'] >= self.max_histories:
            raise HistoryLimit('Complete expansion exceeds generated history cap')
        self.stats['generated_histories'] += 1
        reach = mass.sum()
        upper = np.full(len(mass), reach)
        gap = priority_gap(lower, upper, reach) if history else upper * 2
        node = Frontier(history, mass, lower, upper, gap)
        return lower, upper, node

    def _refresh(self, node):
        best = node.action_lower.argmax(axis=0)
        node.lower = node.action_lower[best, np.arange(len(best))]
        node.optimistic = node.action_upper.argmax(axis=0)
        node.upper = node.action_upper[node.optimistic, np.arange(len(best))]
        node.gap = priority_gap(node.lower, node.upper, node.mass.sum())
        self.decisions[node.history] = np.asarray(node.actions)[best]

    def _expand(self, node):
        actions = self.game.actions(node.history)
        lower = np.zeros((len(actions), len(self.prior)))
        upper = np.zeros_like(lower)
        children = []
        for i, action in enumerate(actions):
            group = []
            if action == -1:
                lower[i] = upper[i] = node.lower
            else:
                prefix = node.history + (action,)
                for reply, mass in self._branches(1-self.seat, prefix, node.mass):
                    if reply == -1:
                        lo = hi = self._claim_value(action, mass, False)
                    else:
                        lo, hi, child = self._leaf(prefix + (reply,), mass)
                        if child is not None:
                            group.append(child)
                    lower[i] += lo
                    upper[i] += hi
            children.append(group)
        # Publish a complete expansion only. A limit inside the loop leaves
        # the old challenge policy and optimistic value in place.
        node.actions, node.children = actions, children
        node.action_lower, node.action_upper = lower, upper
        self.stats['expanded_own_nodes'] += 1
        self._refresh(node)

    def _pick(self, groups, weights):
        best = None
        priority = 0.
        for i, group in enumerate(groups):
            active = weights if self.allocation == 'reach' else weights[i]
            if not active.any():
                continue
            for child in group:
                self.stats['priority_visits'] += 1
                gap = float(active @ child.gap)
                if gap <= 0:
                    continue
                score = gap if self.allocation == 'gap' else float(child.mass.sum())
                if score > priority:
                    priority, best = score, (i, child, active)
        if best is None:
            raise ArithmeticError('Positive response gap has no expandable continuation')
        return best

    def _refine(self, node, weights):
        if not node.actions:
            self._expand(node)
            return
        if self.allocation == 'gap':
            eligible = weights * (node.gap > 0)
            masks = eligible * (np.arange(len(node.actions))[:, None] == node.optimistic)
        else:
            masks = weights
        i, child, active = self._pick(node.children, masks)
        old_lower, old_upper = child.lower, child.upper
        self._refine(child, active)
        node.action_lower[i] += child.lower - old_lower
        node.action_upper[i] += child.upper - old_upper
        self._refresh(node)

    def advance(self, max_nodes):
        """Take a cumulative checkpoint, keeping the latest feasible plan."""
        if type(max_nodes) is not int or not self.stats['expanded_own_nodes'] <= max_nodes <= self.max_nodes or max_nodes < 1:
            raise ValueError('Checkpoint must be positive and within the cumulative budget')
        if self.roots is None:
            roots, fixed = [], np.zeros(len(self.prior))
            if self.seat == 0:
                _, _, root = self._leaf((), self.prior)
                self._expand(root)
                roots.append(root)
            else:
                for action, mass in self._branches(0, (), self.prior):
                    if action == -1:
                        raise ValueError('Opponent challenged at opening')
                    lo, _, root = self._leaf((action,), mass)
                    if root is None:
                        fixed += lo
                    else:
                        roots.append(root)
            self.roots, self.fixed = roots, fixed
        while self.stop_reason is None and self.stats['expanded_own_nodes'] < max_nodes:
            if sum(float(self.prior @ node.gap) for node in self.roots) <= 1e-13:
                self.stop_reason = 'gap_tolerance'
                break
            masks = [self.prior] if self.allocation == 'gap' else self.prior
            _, node, active = self._pick([self.roots], masks)
            try:
                self._refine(node, active)
            except HistoryLimit:
                self.stop_reason = 'history_cap'
        lower = float(self.prior @ (self.fixed + sum(n.lower for n in self.roots)))
        upper = float(self.prior @ (self.fixed + sum(n.upper for n in self.roots)))
        if not np.isfinite([lower, upper]).all() or lower > upper + 1e-12:
            raise ArithmeticError('Invalid response bounds')
        if self.result is not None and (lower < self.result['lower']-1e-12 or upper > self.result['upper']+1e-12):
            raise ArithmeticError('Refinement invalidated prior bounds')
        self.result = {'seat': self.seat, 'lower': lower, 'upper': upper, 'width': max(0., upper-lower),
                       'max_nodes': max_nodes, 'stop': self.stop_reason or 'node_cap',
                       'stats': self.stats.copy(), 'formally_interval_certified': False}
        return self.result

    def solve(self):
        return self.advance(self.max_nodes)
