"""Exact full-history evaluation on ten-bid house-rule research games."""
import random

import numpy as np

from axis_batches import AxisUpdates
from crossed_batches import BatchUpdates
from fixed_strategy import PublicGraph
from game import Bid, Game, hand_distribution
from recall_training import Layout, RecallTrainer

BRIDGE_QUANTITIES = (2, 3)
RECALLS = (1, 2, 3, None)
MAX_STATES = 1024
MAX_ARRAY_BYTES = 32 * 1024**2


class BridgeGame:
    """All private hands and the original rules restricted to ten named bids."""

    def __init__(self, quantity):
        if quantity not in BRIDGE_QUANTITIES:
            raise ValueError('Bridge zhai quantity must be 2 or 3')
        full = Game()
        self.selected = tuple(full.bids.index(Bid(q, f, mode))
                              for q, mode, faces in ((3, 'fly', range(1, 7)),
                                                     (quantity, 'zhai', (2, 4)),
                                                     (quantity+2, 'fly', (2, 4)))
                              for f in faces)
        self.bids = tuple(full.bids[a] for a in self.selected)
        self.hands, self.prior = full.hands, full.prior
        self.weights = [weight for _, weight in hand_distribution()]
        self.counts = tuple(tuple(row[a] for a in self.selected) for row in full.counts)
        translate = {a: i for i, a in enumerate(self.selected)} | {-1: -1}
        self.legal = {
            last: tuple(translate[a] for a in full.actions((self.selected[last],) if last is not None else ())
                        if a in translate)
            for last in (None, *range(len(self.bids)))
        }

    def actions(self, history):
        return self.legal[history[-1] if history else None]

    def payoff(self, history, hands, challenger):
        bid = history[-1]
        true = sum(self.counts[h][bid] for h in hands) >= self.bids[bid].quantity
        return 1. if (challenger == 1) == true else -1.


class BridgeLayout(Layout):
    def __init__(self, game, recall):
        self.game = game
        self.graph = PublicGraph(game, recall, max_states=MAX_STATES)
        self.offsets = np.cumsum([0] + [len(row)*len(game.hands) for row in self.graph.actions])
        self.entries = int(self.offsets[-1])
        self.children = [np.array([-1 if c is None else c for c in row]) for row in self.graph.children]
        self.players = [p for p, _ in self.graph.keys]


class BridgeTrainer(AxisUpdates, BatchUpdates, RecallTrainer):
    """Use the established crossed CFR update with a bounded new layout."""

    def __init__(self, game, recall, seed, size=8):
        self.layout = BridgeLayout(game, recall)
        self.game = game
        self.array_bytes = self.layout.entries * 16
        if self.array_bytes > MAX_ARRAY_BYTES:
            raise MemoryError('Bridge trainer arrays exceed 32 MiB')
        self.regret = np.zeros(self.layout.entries)
        self.average = np.zeros_like(self.regret)
        self.rng = random.Random(seed)
        self.visits = np.zeros((2, len(game.hands)), dtype=np.int64)
        self.iterations = 0
        self.maximum_reach = 0.
        self.configure_batch(size, True)


class BridgeEvaluator:
    """Full public histories, with each terminal grouping opponent mass by count."""

    def __init__(self, game):
        self.graph = PublicGraph(game, None, max_states=MAX_STATES)
        self.prior = np.asarray(game.prior)
        self.counts = np.asarray(game.counts).T
        self.minimum = [np.clip(bid.quantity - count, 0, 8) for bid, count in zip(game.bids, self.counts, strict=True)]
        self.zero = np.zeros_like(self.prior)

    def claim_values(self, bid, reach):
        # A player's own hand matters only through its count for this bid.
        # Index 8 is the empty tail because per-seat counts are 0 through 7.
        mass = np.bincount(self.counts[bid], weights=reach, minlength=8)
        tail = np.append(np.cumsum(mass[::-1])[::-1], 0.)
        return 2 * tail[self.minimum[bid]] - tail[0]

    def evaluate(self, policy):
        def walk(node, reach):
            seat, history = self.graph.keys[node]
            actions = policy.actions(seat, history)
            ev, options = 0., []
            for action, child in zip(self.graph.actions[node], self.graph.children[node], strict=True):
                probs = actions.get(action, self.zero)
                path_reach = list(reach)
                path_reach[seat] = path_reach[seat] * probs
                if child is None:
                    bid = history[-1]
                    sign = 1 if seat == 1 else -1
                    reply0 = sign * self.claim_values(bid, path_reach[1])
                    reply1 = -sign * self.claim_values(bid, path_reach[0])
                    ev += float(path_reach[0] @ reply0)
                    options.append((reply0, reply1))
                else:
                    child_ev, replies = walk(child, path_reach)
                    ev += child_ev
                    options.append(replies)
            options = np.asarray(options)
            replies = options.sum(axis=0)
            # A responder has one choice per own hand after integrating hidden mass.
            # Every legal action is evaluated, including zero frozen-policy actions.
            replies[seat] = options[:, seat].max(axis=0)
            return ev, replies

        if policy.game is not self.graph.game:
            raise ValueError('Policy and evaluator must use the same declared game')
        ev, (r0, r1) = walk(0, (self.prior, self.prior))
        br0, br1 = float(self.prior @ r0), float(self.prior @ r1)
        return {'ev_p0': ev, 'br0': br0, 'br1': br1, 'gain0': br0-ev, 'gain1': br1+ev,
                'nashconv': br0+br1, 'exploitability': (br0+br1)/2}
