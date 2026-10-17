"""Experimental local heads-up turn/river CFR+; never a hosted dependency.

River information sets are batched, not merged: each public river has its own
strategy and regret row. Chance is uniform over the 44 rivers legal for each
compatible four-hole-card deal, not over the union of either player's range.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from .core import DECK, cards, combo_key, expand_range, rank7


@dataclass(frozen=True)
class Terminal:
    kind: str
    contrib: tuple[float, float]
    street: int
    winner: int | None = None


@dataclass(frozen=True)
class Chance:
    child: object


@dataclass
class Decision:
    name: str
    player: int
    street: int
    actions: tuple[str, ...]
    children: tuple[object, ...]
    shape: tuple[int, ...]
    regret: np.ndarray = field(init=False)
    strategy_sum: np.ndarray = field(init=False)
    strategy: np.ndarray = field(init=False)

    def __post_init__(self):
        self.regret = np.zeros(self.shape+(len(self.actions),))
        self.strategy_sum = np.zeros_like(self.regret)
        self.strategy = np.full_like(self.regret, 1/len(self.actions))

    def update_strategy(self):
        positive = np.maximum(self.regret, 0)
        total = positive.sum(axis=-1, keepdims=True)
        self.strategy.fill(1/len(self.actions))
        np.divide(positive, total, out=self.strategy, where=total > 0)

    def average(self):
        total = self.strategy_sum.sum(axis=-1, keepdims=True)
        result = np.full_like(self.strategy_sum, 1/len(self.actions))
        np.divide(self.strategy_sum, total, out=result, where=total > 0)
        return result


class TurnSolver:
    """Fixed arrival ranges, exact public chance, check/bet/call/fold each street.

    Bounds are deliberately small for this local development milestone. There
    are no MCP registrations, network calls, rake, raises or range inference.
    """

    def __init__(self, board: str, oop_range: str, ip_range: str, pot: float,
                 stack: float, turn_bet_sizes: list[float] | None = None,
                 river_bet_sizes: list[float] | None = None):
        self.board = cards(board, 4)
        if any(not isinstance(text, str) or not 1 <= len(text) <= 8000 for text in (oop_range, ip_range)):
            raise ValueError('Ranges must be strings of 1-8000 characters')
        for value in (pot, stack):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1e9:
                raise ValueError('Pot and stack must be finite positive numbers at most 1e9')
        self.pot, self.stack = float(pot), float(stack)
        self.sizes = []
        for values in (turn_bet_sizes, river_bet_sizes):
            values = [0.5] if values is None else values
            if (not isinstance(values, list) or len(values) > 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) or not 0 < v <= 3 for v in values)
                    or len(set(values)) != len(values)):
                raise ValueError('Each street accepts 0-2 distinct pot fractions in (0,3]')
            self.sizes.append(tuple(float(v) for v in values))
        ranges = [expand_range(text, self.board) for text in (oop_range, ip_range)]
        if max(map(len, ranges)) > 24:
            raise ValueError('Experimental local turn limit: 24 combos per side')
        self.hands = [list(r) for r in ranges]
        self.weights = [np.array(list(r.values()), dtype=float) for r in ranges]
        self.valid = np.array([[not set(a) & set(b) for b in self.hands[1]] for a in self.hands[0]], dtype=float)
        self.mass = float(self.weights[0] @ self.valid @ self.weights[1])
        if self.mass <= 0:
            raise ValueError('Ranges have no compatible hole-card pairs')
        self.rivers = tuple(c for c in DECK if c not in self.board)
        self.masks = [np.array([[c not in h for h in side] for c in self.rivers], dtype=float) for side in self.hands]
        self.river_valid = self.valid[None, :, :]*self.masks[0][:, :, None]*self.masks[1][:, None, :]
        # A deal has four board cards + four distinct hole cards: 52 - 8 = 44.
        if not np.array_equal(self.river_valid.sum(axis=0), 44*self.valid):
            raise AssertionError('Incorrect per-deal river chance mass')
        signs = []
        for river in self.rivers:
            scores = [[rank7(tuple(sorted(self.board+(river,)+h))) if river not in h else (-1,)
                       for h in side] for side in self.hands]
            order = {s: i for i, s in enumerate(sorted(set(scores[0]+scores[1])))}
            left, right = [np.array([order[s] for s in side]) for side in scores]
            signs.append(np.sign(left[:, None]-right[None, :]))
        self.river_sign = np.array(signs)*self.river_valid
        self.runout_sign = self.river_sign.sum(axis=0)/44
        self.nodes: dict[str, Decision] = {}
        self.effective_bets: dict[str, list[float]] = {}
        self.root = self._street('turn', 0, 0.0)
        self.iterations = 0

    def _decision(self, name, player, street, actions, children):
        shape = (len(self.hands[player]),)
        if street == 1:
            shape = (len(self.rivers),)+shape
        node = Decision(name, player, street, tuple(actions), tuple(children), shape)
        if name in self.nodes:
            raise AssertionError('Public histories must not share a decision node')
        self.nodes[name] = node
        return node

    def _finish(self, name, street, matched):
        if street == 1:
            return Terminal('showdown', (matched, matched), street)
        if matched >= self.stack:
            return Terminal('runout', (matched, matched), street)
        return Chance(self._street(name+'/river', 1, matched))

    def _street(self, name, street, matched):
        # Sizes use this street's pot. Equal clipped all-ins become one explicit
        # amount-labelled action; the normalized amounts are returned to callers.
        pot, remaining = self.pot+2*matched, self.stack-matched
        bets = list(dict.fromkeys(min(remaining, pot*f) for f in self.sizes[street]))
        self.effective_bets[name] = bets
        ip_facing, oop_facing = [], []
        labels = tuple('bet_'+(str(int(b)) if b.is_integer() else repr(b)) for b in bets)
        for amount, action in zip(bets, labels, strict=True):
            ip_facing.append(self._decision(name+'/'+action, 1, street, ('fold', 'call'), (
                Terminal('fold', (matched+amount, matched), street, 0),
                self._finish(name+'/'+action+'/call', street, matched+amount))))
            oop_facing.append(self._decision(name+'/check/'+action, 0, street, ('fold', 'call'), (
                Terminal('fold', (matched, matched+amount), street, 1),
                self._finish(name+'/check/'+action+'/call', street, matched+amount))))
        after = self._decision(name+'/check', 1, street, ('check',)+labels, (
            self._finish(name+'/check/check', street, matched), *oop_facing))
        return self._decision(name, 0, street, ('check',)+labels, (after, *ip_facing))

    @staticmethod
    def _product(matrix, r0, r1):
        if matrix.ndim == 2:
            return matrix @ r1, matrix.T @ r0
        return np.einsum('rij,rj->ri', matrix, r1), np.einsum('rij,ri->rj', matrix, r0)

    def _terminal(self, leaf, r0, r1):
        if leaf.kind == 'fold':
            payoff = self.pot/2+leaf.contrib[1] if leaf.winner == 0 else -self.pot/2-leaf.contrib[0]
            matrix = self.river_valid if leaf.street else self.valid
        else:
            if leaf.contrib[0] != leaf.contrib[1]:
                raise AssertionError('Showdown requires matched contributions')
            payoff = self.pot/2+leaf.contrib[0]
            matrix = self.runout_sign if leaf.kind == 'runout' else self.river_sign
        left, right = self._product(matrix, r0, r1)
        return payoff*left, -payoff*right

    def _walk(self, node, r0, r1, *, iteration=0, update_player=None,
              best_response=None, collect=None, chance_reach=1.0):
        if isinstance(node, Terminal):
            return self._terminal(node, r0, r1)
        if isinstance(node, Chance):
            left, right = self._walk(node.child, r0[None, :]*self.masks[0], r1[None, :]*self.masks[1],
                                     iteration=iteration, update_player=update_player,
                                     best_response=best_response, collect=collect, chance_reach=chance_reach/44)
            return left.sum(axis=0)/44, right.sum(axis=0)/44
        side = node.player
        strategy = node.strategy if iteration else node.average()
        own = r0 if side == 0 else r1
        if update_player == side:
            node.strategy_sum += iteration*chance_reach*own[..., None]*strategy
        values = []
        for index, child in enumerate(node.children):
            reach0 = r0*strategy[..., index] if side == 0 else r0
            reach1 = r1*strategy[..., index] if side == 1 else r1
            values.append(self._walk(child, reach0, reach1, iteration=iteration, update_player=update_player,
                                     best_response=best_response, collect=collect, chance_reach=chance_reach))
        actor = np.stack([v[side] for v in values], axis=-1)
        mixed = (actor*strategy).sum(axis=-1)
        if update_player == side:
            node.regret = np.maximum(0, node.regret+chance_reach*(actor-mixed[..., None]))
        if collect is not None:
            valid = self.river_valid if node.street else self.valid
            reach = self._product(valid, r0, r1)[side]
            ev = np.full_like(actor, np.nan)
            # Reach carries arbitrary arrival weights. Every positive opponent
            # reach supports a conditional EV, regardless of its absolute scale.
            np.divide(actor, reach[..., None], out=ev, where=reach[..., None] > 0)
            collect[node.name] = {'ev': ev, 'own': own, 'opponent': reach, 'chance_reach': chance_reach}
        own_value = actor.max(axis=-1) if best_response == side else mixed
        other_value = np.sum([v[1-side] for v in values], axis=0)
        return (own_value, other_value) if side == 0 else (other_value, own_value)

    def diagnostics(self):
        left, right = self._walk(self.root, *self.weights)
        best0 = self._walk(self.root, *self.weights, best_response=0)[0]
        best1 = self._walk(self.root, *self.weights, best_response=1)[1]
        ev0 = float(self.weights[0] @ left/self.mass)
        ev1 = float(self.weights[1] @ right/self.mass)
        gap = float((self.weights[0] @ best0+self.weights[1] @ best1)/self.mass)
        return {'iterations': self.iterations, 'oop_ev': ev0, 'ip_ev': ev1,
                'raw_nash_conv_chips': gap, 'zero_sum_residual': ev0+ev1,
                'nash_conv_chips': max(0.0, gap), 'nash_conv_pct_pot': max(0.0, gap)/self.pot*100}

    def solve(self, iterations=500, oop_hand=None, ip_hand=None, river_card=None):
        if type(iterations) is not int or not 20 <= iterations <= 2000:
            raise ValueError('Experimental local iterations must be an integer in [20,2000]')
        if self.iterations:
            raise ValueError('Construct a fresh TurnSolver for each solve')
        queries = {}
        for side, text in enumerate((oop_hand, ip_hand)):
            if text is not None:
                if not isinstance(text, str):
                    raise ValueError('Queried hands must be concrete card strings')
                hand = combo_key(*cards(text, 2))
                if hand not in self.hands[side]:
                    raise ValueError('Queried hand is not in its arrival range')
                index = self.hands[side].index(hand)
                valid = self.valid if side == 0 else self.valid.T
                if valid[index] @ self.weights[1-side] <= 0:
                    raise ValueError('Queried hand has no compatible opponent combos')
                queries[side] = index
        if river_card is not None and river_card not in self.rivers:
            raise ValueError('Requested river must be one card outside the turn board')
        checkpoints = []
        marks = {iterations, max(1, iterations//4), max(1, iterations//2)}
        for iteration in range(1, iterations+1):
            for side in (0, 1):
                for node in self.nodes.values():
                    node.update_strategy()
                self._walk(self.root, *self.weights, iteration=iteration, update_player=side)
            self.iterations = iteration
            if iteration in marks:
                checkpoints.append(self.diagnostics())
        output = {'model': 'Experimental local heads-up turn/river, no raises, no rake',
                  'board': list(self.board), 'pot': self.pot, 'stack': self.stack,
                  'bet_sizes': {'turn': list(self.sizes[0]), 'river': list(self.sizes[1])},
                  'effective_bets_by_public_history': self.effective_bets,
                  'range_combos': {'oop': len(self.hands[0]), 'ip': len(self.hands[1])},
                  'chance': {'enumerated_public_rivers': 48, 'legal_rivers_per_compatible_deal': 44},
                  'computation': 'Alternating CFR+, linear own-reach averaging, exact river enumeration',
                  'ev_baseline': 'Half of the initial turn pot; cumulative turn and river contributions included',
                  'action_ev_interpretation': 'One action followed by fixed average continuation; future deviations are not optimized. Low-reach continuations may be poorly converged despite a small root gap.',
                  'diagnostics': checkpoints[-1], 'checkpoints': checkpoints, 'hands': {},
                  'limitations': 'Small fixed arrival ranges; no independent external turn-engine validation; local only'}
        if queries:
            collected = {}
            self._walk(self.root, *self.weights, collect=collected)
            for side, index in queries.items():
                hand, node_rows = self.hands[side][index], {}
                valid = self.valid if side == 0 else self.valid.T
                initial_opponent = valid[index] @ self.weights[1-side]
                for name, node in self.nodes.items():
                    if node.player != side:
                        continue
                    strategy = node.average()
                    data = collected[name]
                    contexts = range(48) if node.street else (None,)
                    for context in contexts:
                        if context is not None:
                            card = self.rivers[context]
                            if card in hand or (river_card is not None and card != river_card):
                                continue
                        row = (index,) if context is None else (context, index)
                        key = name if context is None else name+'@'+self.rivers[context]
                        opp = data['opponent'][row]
                        node_rows[key] = {
                            'frequency': dict(zip(node.actions, strategy[row].tolist(), strict=True)),
                            'action_ev_relative_to_half_turn_pot': {
                                action: float(ev) if np.isfinite(ev) else None
                                for action, ev in zip(node.actions, data['ev'][row], strict=True)},
                            'reach_probability_given_hand': float(data['own'][row]/self.weights[side][index]
                                                                  *opp/initial_opponent*data['chance_reach'])}
                output['hands']['oop' if side == 0 else 'ip'] = {'combo': list(hand), 'node_strategy': node_rows}
        return output


def evaluate_turn_all_in_call(board, hero_hand, villain_betting_range, pot, bet):
    """Exact terminal all-in call EV; never a non-all-in turn recommendation."""
    hand = combo_key(*cards(hero_hand, 2))
    solver = TurnSolver(board, ''.join(hand), villain_betting_range, pot, bet, [], [])
    equity = float((solver.weights[0] @ (solver.valid+solver.runout_sign) @ solver.weights[1])/(2*solver.mass))
    ev = equity*(pot+2*bet)-bet
    return {'board': list(solver.board), 'hero_hand': list(solver.hands[0][0]),
            'pot_before_bet': pot, 'all_in_call_amount': bet,
            'equity': equity, 'required_equity': bet/(pot+2*bet),
            'ev_call_minus_fold': ev,
            'best_action_given_range': 'call' if ev > 1e-8 else 'fold' if ev < -1e-8 else 'indifferent',
            'legal_rivers_per_compatible_deal': 44,
            'assumption': 'Terminal effective all-in: no future betting, supplied betting range; not a general turn call EV'}
