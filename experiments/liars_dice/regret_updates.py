"""Alternative simultaneous regret and averaging updates for crossed bridge blocks."""
import numpy as np

from recall_bridge import BridgeTrainer

VARIANTS = ('signed-uniform', 'signed-linear', 'plus-linear')


class RegretUpdateTrainer(BridgeTrainer):
    def __init__(self, game, recall, seed, variant, size=8):
        if variant not in VARIANTS:
            raise ValueError('Expected signed-uniform, signed-linear or plus-linear')
        super().__init__(game, recall, seed, size)
        self.linear_average = variant != 'signed-uniform'
        self.clip_regret = variant == 'plus-linear'

    def step(self, hands=None):
        if not self.linear_average:
            return super().step(hands)
        size, n = self.batch_size, len(self.game.hands)
        if hands is None:
            sampled = self.rng.choices(range(n), weights=self.game.prior, k=2*size)
            hands = (sampled[:size], sampled[size:])
        delta, average, value, max_reach = self.batch_increments(hands)
        ids = np.asarray(hands)
        weight = self.iterations + 1
        for i, seat in enumerate(self.layout.players):
            a, b = self.layout.offsets[i:i+2]
            regret = self.regret[a:b].reshape(n, -1)
            total = self.average[a:b].reshape(n, -1)
            own = ids[seat]
            np.add.at(regret, own, delta[i])
            np.add.at(total, own, weight * average[i])
            updated = regret[own]
            if not np.isfinite(updated).all() or not np.isfinite(total[own]).all():
                raise ArithmeticError('Nonfinite cumulative crossed block update')
            if self.clip_regret:
                # A repeated hand gets every contribution before applying the floor.
                # Each repeated destination now receives the same clipped row.
                regret[own] = np.maximum(updated, 0.)
        for seat in (0, 1):
            np.add.at(self.visits[seat], ids[seat], 1)
        self.maximum_reach = max(self.maximum_reach, max_reach)
        self.iterations += 1
        return value
