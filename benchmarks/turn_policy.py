"""Scalar policy/BR oracle, not an independently trained external turn solver.

Uses pinned upstream exhaustive five-card-combination hand evaluation. It reads
the product's public tree and policy, but never its validity/sign/chance arrays
or counterfactual traversal. Tree semantics require separate fixture tests.
"""
from __future__ import annotations

from benchmarks.harness import verify_reference
from games.river_holdem import card_id, evaluate_7
from poker_spot.turn import Chance, Decision, Terminal


class TurnPolicyOracle:
    def __init__(self, solver):
        verify_reference()
        self.solver = solver
        self.hands = solver.hands
        self.weights = [list(map(float, side)) for side in solver.weights]
        self.rivers = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs' if r+s not in solver.board)
        if self.rivers != solver.rivers:
            raise ValueError('Different public river ordering')
        self.mass = sum(self.weights[0][i]*self.weights[1][j]
                        for i, a in enumerate(self.hands[0]) for j, b in enumerate(self.hands[1])
                        if not set(a) & set(b))
        self.profiles = {name: n.average().tolist() for name, n in solver.nodes.items()}
        self.sign = {}
        for k, river in enumerate(self.rivers):
            scores = [[evaluate_7([card_id(c) for c in (*solver.board, river, *h)])
                       if river not in h else None for h in side] for side in self.hands]
            for i, a in enumerate(self.hands[0]):
                for j, b in enumerate(self.hands[1]):
                    if set(a) & set(b) or river in a or river in b:
                        continue
                    self.sign[k, i, j] = (scores[0][i] > scores[1][j])-(scores[0][i] < scores[1][j])

    def _payoff(self, leaf, side, own, other, context):
        i, j = (own, other) if side == 0 else (other, own)
        if set(self.hands[0][i]) & set(self.hands[1][j]):
            return 0.0
        if context is not None and (context, i, j) not in self.sign:
            return 0.0
        pot = self.solver.pot+sum(leaf.contrib)
        cost = leaf.contrib[side]+self.solver.pot/2
        if leaf.kind == 'fold':
            return (pot if leaf.winner == side else 0)-cost
        if leaf.kind == 'runout':
            outcomes = [value for (k, a, b), value in self.sign.items() if a == i and b == j]
            if len(outcomes) != 44:
                raise AssertionError('Scalar oracle found wrong legal runout count')
            win_share = (1+sum(outcomes)/len(outcomes))/2
        else:
            win_share = (1+self.sign[context, i, j])/2
        if side == 1:
            win_share = 1-win_share
        return win_share*pot-cost

    def _walk(self, node, side, own, opponent, best_response, context=None):
        if isinstance(node, Terminal):
            return sum(weight*self._payoff(node, side, own, j, context) for j, weight in enumerate(opponent) if weight)
        if isinstance(node, Chance):
            total = 0.0
            for k, river in enumerate(self.rivers):
                if river in self.hands[side][own]:
                    continue
                weights = [weight if river not in h else 0.0
                           for weight, h in zip(opponent, self.hands[1-side], strict=True)]
                total += self._walk(node.child, side, own, weights, best_response, k)
            return total/44
        if not isinstance(node, Decision):
            raise TypeError('Unknown public tree node')
        policy = self.profiles[node.name] if context is None else self.profiles[node.name][context]
        values = []
        for action, child in enumerate(node.children):
            reach = opponent if node.player == side else [w*policy[j][action] for j, w in enumerate(opponent)]
            values.append(self._walk(child, side, own, reach, best_response, context))
        if node.player != side:
            return sum(values)
        if best_response:
            return max(values)
        return sum(value*policy[own][a] for a, value in enumerate(values))

    def evaluate(self):
        values, best = [], []
        for side in (0, 1):
            ev, br = 0.0, 0.0
            for i, hand in enumerate(self.hands[side]):
                opponent = [w if not set(hand) & set(h) else 0.0
                            for w, h in zip(self.weights[1-side], self.hands[1-side], strict=True)]
                ev += self.weights[side][i]*self._walk(self.solver.root, side, i, opponent, False)
                br += self.weights[side][i]*self._walk(self.solver.root, side, i, opponent, True)
            values.append(ev/self.mass)
            best.append(br/self.mass)
        return {'oop_ev': values[0], 'ip_ev': values[1], 'nash_conv_chips': sum(best)}
