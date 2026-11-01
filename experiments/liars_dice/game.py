"""Standalone, assumption-labelled finite Liar's Dice game. No product imports."""
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations_with_replacement
from math import factorial


@dataclass(frozen=True)
class Rules:
    # Defaults are owner-confirmed house rules (31 October 2026); other values are research sensitivity profiles.
    face_one: bool = True
    all_ones_wild_seven: bool = True
    zhai_mixed_bonus: bool = False
    opening_zhai: bool = True
    quantity_floor: int = 1
    max_quantity: int = 14

    def __post_init__(self):
        if self.quantity_floor not in (1, 3) or self.max_quantity != 14:
            raise ValueError("Supported research floors: 1/3; additive bonus cap: 14")


@dataclass(frozen=True, order=True)
class Bid:
    quantity: int
    face: int
    mode: str

    @property
    def rank(self):
        # Strictly increases even across the quantity-reducing mode transition.
        return (2 * self.quantity + (3 if self.mode == "zhai" else 0), self.face)


def contribution(hand, face, mode, rules=Rules()):
    if len(hand) != 5 or any(type(d) is not int or not 1 <= d <= 6 for d in hand):
        raise ValueError("Expected five integer dice in 1..6")
    if face not in range(1, 7) or mode not in ("fly", "zhai"):
        raise ValueError("Invalid face/mode")
    target, ones = hand.count(face), hand.count(1)
    if target == 5:
        return 7
    if face == 1:
        return ones
    if mode == "fly":
        if ones == 5:
            return 7 if rules.all_ones_wild_seven else 6
        return 6 if target + ones == 5 else target + ones
    if rules.zhai_mixed_bonus and target and target + ones == 5:
        return 6
    return target


@lru_cache(maxsize=None)
def hand_distribution():
    """252 lossless unordered hands, with exact ordered-roll multiplicities."""
    result = []
    for hand in combinations_with_replacement(range(1, 7), 5):
        weight = factorial(5)
        for face in range(1, 7):
            weight //= factorial(hand.count(face))
        result.append((hand, weight))
    return tuple(result)


class Game:
    def __init__(self, rules=Rules()):
        self.rules = rules
        self.hands = tuple(h for h, _ in hand_distribution())
        self.prior = tuple(n / 7776 for _, n in hand_distribution())
        faces = range(1 if rules.face_one else 2, 7)
        self.bids = tuple(Bid(q, f, m) for q in range(rules.quantity_floor, 15)
                          for f in faces for m in ("fly", "zhai"))
        self.counts = tuple(tuple(contribution(h, b.face, b.mode, rules)
                                  for b in self.bids) for h in self.hands)
        self._actions = {(): self._legal(None)}
        for i, bid in enumerate(self.bids):
            self._actions[i] = self._legal(bid)

    def _legal(self, last):
        legal = [] if last is None else [-1]  # challenge
        for i, bid in enumerate(self.bids):
            if last is None:
                ok = bid.quantity >= 3 and (self.rules.opening_zhai or bid.mode == "fly")
            elif bid.mode == last.mode:
                ok = (bid.quantity, bid.face) > (last.quantity, last.face)
            elif last.mode == "fly":
                ok = bid.quantity >= last.quantity - 1
            else:
                ok = bid.quantity >= last.quantity + 2
            if ok:
                legal.append(i)
                if last is not None:
                    assert bid.rank > last.rank
        return tuple(legal)

    def actions(self, history):
        return self._actions[history[-1] if history else ()]

    def payoff(self, history, hands, challenger):
        bid = history[-1]
        true = self.counts[hands[0]][bid] + self.counts[hands[1]][bid] >= self.bids[bid].quantity
        winner = 1 - challenger if true else challenger
        return 1.0 if winner == 0 else -1.0

    def sample(self, rng):
        return tuple(rng.choices(range(len(self.hands)), weights=self.prior, k=2))

    def key(self, player, hand, history):
        # Full public history and own exact multiset preserve perfect recall.
        return player, hand, history
