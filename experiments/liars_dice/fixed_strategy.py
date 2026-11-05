"""Fixed-strategy graph CFR reference; cumulative regrets, simultaneous updates.

This uses FSICFR's forward/backward structure, NOT Algorithm 2's visit-normalized
regret update. One iteration exactly sums frozen-policy tree updates over deals
and histories. Imperfect recall removes the general equilibrium guarantee.
"""
from collections import deque

import numpy as np


class TinyDudo:
    """OpenSpiel reset-face single-round 1v1: highest face wild, utility +/-1."""
    def __init__(self, sides=3):
        if type(sides) is not int or not 2 <= sides <= 6:
            raise ValueError('Tiny reference supports 2..6 sides')
        self.sides = sides
        self.hands = tuple(range(1, sides+1))
        self.prior = (1/sides,)*sides

    def actions(self, history):
        return tuple(([-1] if history else []) + list(range(history[-1]+1 if history else 0, 2*self.sides)))

    def payoff(self, history, hands, challenger):
        quantity, face = divmod(history[-1], self.sides)
        quantity, face = quantity+1, face+1
        matches = sum(self.hands[h] in (face, self.sides) for h in hands)
        winner = 1-challenger if matches >= quantity else challenger
        return 1.0 if winner == 0 else -1.0

    def rank(self, action):
        return action


class PublicGraph:
    """Seat + last m bids; None retains complete history. No private abstraction."""
    def __init__(self, game, recall=None, max_states=100000):
        if recall is not None and (type(recall) is not int or recall < 1):
            raise ValueError('Recall must be positive or None')
        if type(max_states) is not int or max_states < 1:
            raise ValueError('Positive state budget required')
        self.game, self.recall = game, recall
        seen, todo = {(0, ())}, deque([(0, ())])
        while todo:
            player, history = todo.popleft()
            for action in game.actions(history):
                if action == -1:
                    continue
                if history and self.rank(action) <= self.rank(history[-1]):
                    raise ValueError('Non-increasing bid graph')
                key = self.key(1-player, history+(action,))
                if key not in seen:
                    if len(seen) >= max_states:
                        raise MemoryError('Graph state budget exceeded before training')
                    seen.add(key)
                    todo.append(key)
        self.keys = [(0, ())] + sorted(seen-{(0, ())}, key=lambda k:(self.rank(k[1][-1]), k))
        self.index = {key:i for i, key in enumerate(self.keys)}
        self.actions = [game.actions(h) for _, h in self.keys]
        self.children = []
        for i, (player, history) in enumerate(self.keys):
            children = [None if a == -1 else self.index[self.key(1-player, history+(a,))]
                        for a in self.actions[i]]
            if any(c is not None and c <= i for c in children):
                raise ValueError('Graph is not topologically ordered')
            self.children.append(children)

    def rank(self, action):
        return self.game.rank(action) if hasattr(self.game, 'rank') else self.game.bids[action].rank

    def key(self, player, history):
        return player, tuple(history if self.recall is None else history[-self.recall:])


def normalize(rows):
    sums = rows.sum(axis=1, keepdims=True)
    return np.divide(rows, sums, out=np.full_like(rows, 1/rows.shape[1]), where=sums > 0)


class GraphCFR:
    """Exact deal enumeration for tiny games; not the planned full-rule trainer.

    Scratch retains both hands to compute payoffs/expectations. Policy rows and
    accumulated regrets are indexed ONLY by seat, own hand and public suffix.
    """
    def __init__(self, game, recall=None, max_states=100000, max_bytes=256*1024**2):
        if len(game.hands) > 6:
            raise ValueError('Exact-deal trainer is restricted to tiny references')
        self.graph = PublicGraph(game, recall, max_states)
        self.game = game
        n, states = len(game.hands), len(self.graph.keys)
        # Three persistent action arrays + conservative matrix scratch estimate.
        entries = sum(map(len, self.graph.actions))*n
        self.estimated_array_bytes = 8*(3*entries + 6*states*n*n)
        if self.estimated_array_bytes > max_bytes:
            raise MemoryError('Array budget exceeded before trainer allocation')
        self.regrets = [np.zeros((n, len(a))) for a in self.graph.actions]
        self.averages = [np.zeros_like(r) for r in self.regrets]
        self.terminals = []
        for player, history in self.graph.keys:
            self.terminals.append(None if not history else np.array([
                [game.payoff(history, (a,b), player) for b in range(n)] for a in range(n)]))
        self.iterations = 0

    def current(self):
        return [normalize(r.clip(0)) for r in self.regrets]

    def increments(self, strategies):
        graph, n = self.graph, len(self.game.hands)
        shape = (len(graph.keys), n, n)
        reach = np.zeros((2, *shape))
        reach[:, 0] = 1
        for i, (player, _) in enumerate(graph.keys):
            for j, child in enumerate(graph.children[i]):
                if child is None:
                    continue
                s = strategies[i][:, j, None] if player == 0 else strategies[i][None, :, j]
                reach[player, child] += reach[player, i]*s
                reach[1-player, child] += reach[1-player, i]
        values = np.zeros(shape)  # player-0 utility, independent of reach
        weight = np.outer(self.game.prior, self.game.prior)
        regrets, averages = [None]*len(graph.keys), [None]*len(graph.keys)
        for i in reversed(range(len(graph.keys))):
            player, _ = graph.keys[i]
            child_values = [self.terminals[i] if c is None else values[c] for c in graph.children[i]]
            for j, v in enumerate(child_values):
                s = strategies[i][:, j, None] if player == 0 else strategies[i][None, :, j]
                values[i] += s*v
            opponent_axis = 1 if player == 0 else 0
            sign = 1 if player == 0 else -1
            regrets[i] = np.stack([
                (weight*reach[1-player, i]*sign*(v-values[i])).sum(axis=opponent_axis)
                for v in child_values], axis=1)
            averages[i] = (weight*reach[player, i]).sum(axis=opponent_axis)[:, None]*strategies[i]
        return regrets, averages, float((weight*values[0]).sum())

    def step(self):
        delta, average, value = self.increments(self.current())
        for r, a, dr, da in zip(self.regrets, self.averages, delta, average):
            r += dr
            a += da
            if not np.isfinite(r).all() or not np.isfinite(a).all():
                raise ArithmeticError('Non-finite training state')
        self.iterations += 1
        return value

    def policy(self, player, hand, history):
        if player != len(history)%2:
            raise ValueError('Wrong seat to act')
        i = self.graph.index[self.graph.key(player, history)]
        row = self.averages[i][hand]
        return row/row.sum() if row.sum() > 0 else np.full(len(row), 1/len(row))


def tree_increments(game, graph, strategies):
    """Slow scalar oracle: visit every complete history and ordered private pair.

    No graph reach propagation or shared continuation values. Pool into policy
    rows only AFTER evaluating each deal/history. For bounded tiny fixtures.
    """
    regrets = [np.zeros_like(s) for s in strategies]
    averages = [np.zeros_like(s) for s in strategies]

    def walk(hands, history, reach, weight):
        player = len(history)%2
        i = graph.index[graph.key(player, history)]
        row = strategies[i][hands[player]]
        children = []
        for j, action in enumerate(game.actions(history)):
            if action == -1:
                v = game.payoff(history, hands, player)
            else:
                child_reach = list(reach)
                child_reach[player] *= row[j]
                v = walk(hands, history+(action,), child_reach, weight)
            children.append(v)
        value = sum(p*v for p,v in zip(row, children))
        sign = 1 if player == 0 else -1
        for j, v in enumerate(children):
            regrets[i][hands[player], j] += weight*reach[1-player]*sign*(v-value)
            averages[i][hands[player], j] += weight*reach[player]*row[j]
        return value

    value = 0.
    for a, pa in enumerate(game.prior):
        for b, pb in enumerate(game.prior):
            value += pa*pb*walk((a,b), (), [1.,1.], pa*pb)
    return regrets, averages, value
