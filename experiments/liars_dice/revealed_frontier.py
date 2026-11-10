"""Upper bounds from revealing the opposing hand at a response frontier."""
import numpy as np

from fixed_strategy import PublicGraph
from gap_response import priority_gap
from response_kernels import PreparedFrontier
from response_refinement import CachedRecallModel


def oracle_resources(graph, hand_count):
    states = len(graph.keys)
    edges = sum(map(len, graph.actions))
    pairs = hand_count**2
    # Dense value table and conservative allowance for temporary pair matrices.
    return {'states': states, 'action_edges': edges, 'pair_edges': edges*pairs,
            'estimated_matrix_bytes': (states+4)*pairs*8, 'recall': graph.recall}


class RevealedUpper:
    """Fixed-opponent best response after giving the responder both hands.

    Rows are own hand, columns are opposing hand. For a cached one-bid
    target the value for a *known deal* depends only on turn and last bid.
    For other models the graph retains complete public history.
    """

    def __init__(self, game, model, guide, seat, *, max_bytes=192*1024**2,
                 max_states=4096, max_pair_edges=2_000_000_000):
        if type(seat) is not int or seat not in (0, 1):
            raise ValueError('Seat must be 0 or 1')
        if any(type(cap) is not int or cap < 1 for cap in (max_bytes, max_states, max_pair_edges)):
            raise ValueError('Positive integer oracle limits required')
        cached = type(model) is CachedRecallModel
        if model.target.game is not game:
            raise ValueError('Oracle and target require the same game')
        graph = model.target.layout.graph if cached else PublicGraph(game, recall=None, max_states=max_states)
        n = len(game.hands)
        resources = oracle_resources(graph, n)
        states = resources['states']
        if (states > max_states or resources['estimated_matrix_bytes'] > max_bytes
                or resources['pair_edges'] > max_pair_edges):
            raise MemoryError('Revealed-hand oracle exceeds state, memory or work cap')

        self.game, self.model, self.guide, self.seat = game, model, guide, seat
        self.graph = graph
        self.resources = resources
        values = np.empty((states, n, n))
        scratch = np.empty((n, n))
        for i in reversed(range(states)):
            actor, history = graph.keys[i]
            legal = graph.actions[i]
            current = values[i]
            if actor != seat:
                rows = model.entries[i] if cached else model.actions(actor, history)
                if not cached:
                    table = np.asarray(list(rows.values()))
                    if (not rows or not set(rows) <= set(legal) or table.shape != (len(rows), n)
                            or not np.isfinite(table).all() or (table < 0).any()
                            or not np.allclose(table.sum(axis=0), 1, atol=1e-12, rtol=0)):
                        raise ValueError('Invalid frozen full-history probabilities')
                current.fill(0.)
            else:
                current.fill(-np.inf)
            for action, child in zip(legal, graph.children[i], strict=True):
                if actor != seat and action not in rows:
                    continue
                if action == -1:
                    column = guide.columns[history[-1]]
                    count = guide.counts[:, column]
                    true = np.add.outer(count, count) >= guide.quantities[column]
                    value = 1 - 2*true if actor == seat else 2*true - 1
                else:
                    value = values[child]
                if actor == seat:
                    np.maximum(current, value, out=current)
                else:
                    np.multiply(value, rows[action], out=scratch)
                    current += scratch
        values.flags.writeable = False
        self._values = values

    def matrix(self, history):
        key = self.graph.key(len(history) % 2, history)
        return self._values[self.graph.index[key]]

    def upper(self, history, mass):
        """Integrate the relaxed continuation against the actual opponent reach."""
        return self.matrix(history) @ mass


class RevealedFrontier(PreparedFrontier):
    """Use the oracle only for optimistic endpoints and expansion priority."""

    def __init__(self, game, guide, model, seat, max_nodes, claims, oracle, *, max_histories=20000):
        if (oracle.game is not game or oracle.model is not model
                or oracle.guide is not guide or oracle.seat != seat):
            raise ValueError('Oracle is bound to one game, opponent, guide and seat')
        super().__init__(game, guide, model, seat, max_nodes, claims, max_histories=max_histories,
                         reuse_reach=True)
        self.oracle = oracle
        self.stats['oracle_calls'] = 0

    def _leaf(self, history, mass):
        lower, upper, node = super()._leaf(history, mass)
        if node is None or not history:
            return lower, upper, node
        self.stats['oracle_calls'] += 1
        improved = np.minimum(upper, self.oracle.upper(history, mass))
        if (improved < lower-1e-12).any():
            raise ArithmeticError('Relaxed value is below the feasible challenge')
        # Clamp roundoff only. The lower value and its action stay unchanged.
        node.upper = np.maximum(lower, improved)
        node.gap = priority_gap(lower, node.upper, mass.sum())
        return lower, node.upper, node
