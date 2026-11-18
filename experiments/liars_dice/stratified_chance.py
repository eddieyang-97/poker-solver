"""Integer stratification of each private-hand list for crossed CFR blocks."""
from bisect import bisect_right
from itertools import accumulate


class StratifiedHands:
    def __init__(self, weights, size):
        if type(size) is not int or size < 1 or not weights or any(type(w) is not int or w < 0 for w in weights):
            raise ValueError('Positive batch size and nonnegative integer weights required')
        self.total = sum(weights)
        if self.total == 0:
            raise ValueError('Positive total chance mass required')
        self.ends = tuple(size * x for x in accumulate(weights))
        self.starts = range(0, size * self.total, self.total)

    def draw(self, rng):
        return [bisect_right(self.ends, start + rng.randrange(self.total)) for start in self.starts]

    def deal(self, rng):
        return self.draw(rng), self.draw(rng)
