"""Prepared terminal arithmetic shared by response-search schedules."""
import numpy as np

from bounded_response import ResponseSearch
from gap_response import FrontierResponse


class PreparedClaims:
    """Precompute the hand-to-histogram lookups once per immutable game guide."""

    def __init__(self, guide):
        self.lookups = {}
        for action, col in guide.columns.items():
            counts = guide.counts[:, col].astype(int)
            needed = np.clip(guide.quantities[col] - counts, 0, 8)
            counts.flags.writeable = needed.flags.writeable = False
            self.lookups[action] = counts, needed

    def value(self, action, mass, challenging):
        counts, needed = self.lookups[action]
        histogram = np.bincount(counts, weights=mass, minlength=8)
        tails = np.empty(9)
        histogram[::-1].cumsum(out=tails[7::-1])
        tails[8] = 0.
        value = 2 * tails[needed] - mass.sum()
        return -value if challenging else value


class PreparedBranches:
    """Compute each positive branch's reach once and retain the legacy order."""

    def _branches(self, player, history, mass):
        if not self.reuse_reach:
            return super()._branches(player, history, mass)
        self.stats['opponent_nodes'] += 1
        ranked = []
        for action, probability in self.model.actions(player, history).items():
            branch = mass * probability
            reach = float(branch.sum())
            if reach > 0:
                ranked.append((-reach, action, branch))
        ranked.sort()
        return [(action, branch) for _, action, branch in ranked]


class PreparedDepthFirst(PreparedBranches, ResponseSearch):
    def __init__(self, game, guide, model, seat, max_nodes, claims, *, reuse_reach=False):
        super().__init__(game, guide, model, seat, depth=128, max_nodes=max_nodes)
        self.claims = claims
        self.reuse_reach = reuse_reach

    def _claim_value(self, action, mass, challenging):
        return self.claims.value(action, mass, challenging)


class PreparedFrontier(PreparedBranches, FrontierResponse):
    def __init__(self, game, guide, model, seat, max_nodes, claims, allocation='gap',
                 max_histories=20000, *, reuse_reach=False):
        super().__init__(game, guide, model, seat, max_nodes, allocation, max_histories)
        self.claims = claims
        self.reuse_reach = reuse_reach

    def _claim_value(self, action, mass, challenging):
        self.stats['claim_values'] += 1
        return self.claims.value(action, mass, challenging)
