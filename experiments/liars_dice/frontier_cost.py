"""Demand-built revealed-hand frontier bounds with explicit work limits."""
import numpy as np

from response_refinement import CachedRecallModel
from run_gap_response import TableTarget


class LazyUpper:
    """Cache known-deal values for the full continuation or just one reply.

    The reply version uses +1 if the opponent raises. Both versions use
    actual opponent action probabilities and exact challenge payoffs.
    """

    def __init__(self, game, model, guide, seat, *, reply_only=False,
                 max_bytes=192*1024**2, max_pair_edges=2_000_000_000):
        if type(seat) is not int or seat not in (0, 1) or type(reply_only) is not bool:
            raise ValueError('Seat 0/1 and boolean reply mode required')
        if any(type(x) is not int or x < 1 for x in (max_bytes, max_pair_edges)):
            raise ValueError('Positive integer memory and work limits required')
        if type(model) not in (CachedRecallModel, TableTarget) or model.target.game is not game:
            raise ValueError('Require a validated frozen target for the same game')
        self.game, self.model, self.guide, self.seat = game, model, guide, seat
        self.reply_only = reply_only
        self.max_bytes, self.max_pair_edges = max_bytes, max_pair_edges
        self.graph = model.target.layout.graph if type(model) is CachedRecallModel else None
        self.n = len(game.hands)
        self.shape = (self.n, self.n)
        self.matrix_bytes = self.n**2*8
        self.values = {}
        self.live_matrices = 0
        self.peak_matrix_bytes = 0
        self.pair_edges = 0

    def _truth(self, action):
        col = self.guide.columns[action]
        counts = self.guide.counts[:, col]
        return np.add.outer(counts, counts) >= self.guide.quantities[col]

    def _work(self):
        if self.pair_edges + self.n**2 > self.max_pair_edges:
            raise MemoryError('Lazy oracle pair-edge cap exceeded')
        self.pair_edges += self.n**2

    def _reply(self, history, result):
        result.fill(-np.inf)
        for action in self.game.actions(history):
            self._work()
            if action == -1:
                value = 1 - 2*self._truth(history[-1])
            else:
                prefix = history+(action,)
                challenge = self.model.actions(1-self.seat, prefix).get(-1)
                # A true claim is a win on a challenge and receives +1 on
                # a raise. A false claim loses on a challenge.
                value = 1. if challenge is None else 1 - 2*challenge*(~self._truth(action))
            np.maximum(result, value, out=result)

    def _exact(self, history, actor, result):
        if actor == self.seat:
            result.fill(-np.inf)
            for action in self.game.actions(history):
                self._work()
                value = 1 - 2*self._truth(history[-1]) if action == -1 else self.matrix(history+(action,))
                np.maximum(result, value, out=result)
        else:
            result.fill(0.)
            rows = self.model.actions(actor, history)
            # Keep the dense oracle's action and accumulation order.
            for action in self.game.actions(history):
                if action not in rows:
                    continue
                self._work()
                value = 2*self._truth(history[-1]) - 1 if action == -1 else self.matrix(history+(action,))
                result += value*rows[action]

    def matrix(self, history):
        actor = len(history) % 2
        if self.reply_only and actor != self.seat:
            raise ValueError('Reply cutoff starts on a responder turn')
        key = history if self.graph is None else self.graph.key(actor, history)
        if key not in self.values:
            # Include pending matrices along the recursion and a conservative
            # allowance for temporary truth/value/weighted matrices.
            projected = (len(self.values)+self.live_matrices+5)*self.matrix_bytes
            if projected > self.max_bytes:
                raise MemoryError('Lazy oracle pair-matrix cap exceeded')
            self.peak_matrix_bytes = max(self.peak_matrix_bytes, projected)
            self.live_matrices += 1
            try:
                result = np.empty(self.shape)
                if self.reply_only:
                    self._reply(history, result)
                else:
                    self._exact(history, actor, result)
                result.flags.writeable = False
                self.values[key] = result
            finally:
                self.live_matrices -= 1
        return self.values[key]

    def upper(self, history, mass):
        return self.matrix(history) @ mass

    def resources(self):
        return {'cached_matrices': len(self.values), 'pair_edges': self.pair_edges,
                'estimated_matrix_bytes': self.peak_matrix_bytes}


class FactoredReply(LazyUpper):
    """Split the one-reply penalty into a rule mask and an opponent vector."""

    def __init__(self, game, model, guide, seat, **limits):
        super().__init__(game, model, guide, seat, reply_only=True, **limits)
        self.truth = {}
        self.bad = {}
        self.risk = {}

    def _reserve(self, extra):
        used = (len(self.bad)+len(self.truth))*self.n**2 + len(self.risk)*self.n*8
        projected = used + extra + 2*self.n**2 + 4*self.n*8
        if projected > self.max_bytes:
            raise MemoryError('Factored reply cache exceeds pair-memory cap')
        self.peak_matrix_bytes = max(projected, self.peak_matrix_bytes)

    def _truth(self, action):
        if action not in self.truth:
            self._reserve(self.n**2)
            self._work()
            col = self.guide.columns[action]
            counts = self.guide.counts[:, col]
            self.truth[action] = counts[None, :] >= (self.guide.quantities[col]-counts)[:, None]
        return self.truth[action]

    def _mask(self, history, raises):
        last = history[-1] if history else None
        key = last, raises
        if key not in self.bad:
            self._reserve(self.n**2)
            self._work()
            mask = self._truth(last).copy() if history else np.ones(self.shape, dtype=bool)
            for action in raises:
                self._work()
                mask &= ~self._truth(action)
            self._reserve(self.n**2)
            self.bad[key] = mask
        return self.bad[key]

    def _factors(self, history):
        if len(history) % 2 != self.seat:
            raise ValueError('Reply cutoff starts on a responder turn')
        key = history if self.graph is None else self.graph.key(self.seat, history)
        raises = self.game.actions(history)
        if raises[0] == -1:
            raises = raises[1:]
        if key not in self.risk:
            self._reserve(self.n*8)
            risk = np.ones(self.n)
            for action in raises:
                p = self.model.actions(1-self.seat, history+(action,)).get(-1)
                if p is None:
                    risk.fill(0.)
                    break
                np.minimum(risk, p, out=risk)
            self.risk[key] = risk if risk.any() else None
        risk = self.risk[key]
        if risk is None:
            return None, None
        return self._mask(history, raises), risk

    def matrix(self, history):
        mask, risk = self._factors(history)
        self._reserve(3*self.matrix_bytes)
        self._work()
        return np.ones(self.shape) if mask is None else 1 - 2*mask*risk

    def upper(self, history, mass):
        mask, risk = self._factors(history)
        reach = mass.sum()
        if mask is None:
            return np.full(self.n, reach)
        self._work()
        penalty = np.einsum('ij,j->i', mask, risk*mass, optimize=False)
        return reach - 2*penalty

    def resources(self):
        return {**super().resources(), 'rule_masks': len(self.bad), 'truth_masks': len(self.truth),
                'opponent_vectors': len(self.risk)}
