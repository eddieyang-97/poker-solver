"""Tighten only a selected optimistic frontier before considering expansion."""
import numpy as np

from gap_response import priority_gap
from response_kernels import PreparedFrontier


class SelectiveFrontier(PreparedFrontier):
    def __init__(self, game, guide, model, seat, max_nodes, claims, oracle,
                 *, max_queries=4096, max_histories=20000):
        if type(max_queries) is not int or max_queries < 0:
            raise ValueError('Nonnegative integer query cap required')
        if (oracle.game is not game or oracle.model is not model
                or oracle.guide is not guide or oracle.seat != seat):
            raise ValueError('Compatible frozen oracle required')
        super().__init__(game, guide, model, seat, max_nodes, claims,
                         max_histories=max_histories, reuse_reach=True)
        self.oracle = oracle
        self.max_queries = max_queries
        self.queried = set()
        self.disabled = False
        self.stats.update(oracle_queries=0, oracle_failures=0)

    def _refine(self, node, weights):
        if (not node.actions and node.history not in self.queried and not self.disabled
                and self.stats['oracle_queries'] < self.max_queries):
            self.queried.add(node.history)
            self.stats['oracle_queries'] += 1
            try:
                upper = self.oracle.upper(node.history, node.mass)
            except MemoryError:
                # Retain the existing valid +1 bound and continue ordinary
                # expansion. Never publish a partially computed oracle value.
                self.disabled = True
                self.stats['oracle_failures'] += 1
            else:
                if not np.isfinite(upper).all() or (upper < node.lower-1e-12).any():
                    raise ArithmeticError('Invalid optimistic frontier value')
                node.upper = np.maximum(node.lower, np.minimum(node.upper, upper))
                node.gap = priority_gap(node.lower, node.upper, node.mass.sum())
                return
        super()._refine(node, weights)
