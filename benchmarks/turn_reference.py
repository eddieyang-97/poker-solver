"""Independent development turn trainer; no product imports or product tree.

An explicit private-deal/public-chance extensive tree is compiled into breadth
layers. Regrets and best responses pool concrete nodes by information set.
Only the pinned exhaustive hand ranker is reused from the river reference.
This is new repository code, not an externally audited turn engine.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
import math
from pathlib import Path
import sys

import numpy as np

from benchmarks.reference_worker import VENDOR, verify_reference

SCALE = 100
DECK = tuple(rank+suit for rank in '23456789TJQKA' for suit in 'cdhs')


def concrete_hand(text):
    if not isinstance(text, str) or len(text) != 4:
        raise ValueError('Explicit four-character hole cards required')
    pair = tuple(sorted((text[:2], text[2:])))
    if any(card not in DECK for card in pair) or pair[0] == pair[1]:
        raise ValueError('Two distinct valid hole cards required')
    return pair


def cents(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1e9:
        raise ValueError('Finite positive chip amount at most 1e9 required')
    amount = Fraction(str(value))*SCALE
    if amount.denominator != 1:
        raise ValueError('Reference rejects sub-cent rounding')
    return int(amount)


@dataclass(frozen=True)
class State:
    street: int = 0
    committed: tuple[int, int] = (0, 0)
    player: int = 0
    checked: bool = False
    river: str | None = None
    history: tuple[str, ...] = ()
    phase: str = 'act'
    winner: int | None = None


class IndependentTurnGame:
    def __init__(self, config):
        required = {'board', 'pot', 'stack', 'turn_bet_sizes', 'river_bet_sizes',
                    'oop', 'ip', 'rake', 'max_raises', 'include_all_in'}
        if not isinstance(config, dict) or set(config) != required or config['rake'] != 0 or config['max_raises'] != 0 or config['include_all_in'] is not False:
            raise ValueError('Explicit no-raise/no-rake tree without implicit sizes required')
        board = config['board']
        if (not isinstance(board, list) or len(board) != 4
                or any(not isinstance(c, str) or c not in DECK for c in board) or len(set(board)) != 4):
            raise ValueError('Four distinct valid board cards required')
        self.config = config
        self.board = tuple(board)
        self.pot, self.stack = cents(config['pot']), cents(config['stack'])
        self.sizes = []
        for name in ('turn_bet_sizes', 'river_bet_sizes'):
            values = config[name]
            if (not isinstance(values, list) or len(values) > 2
                    or any(isinstance(x, bool) or not isinstance(x, (int, float))
                           or not math.isfinite(x) or not 0 < x <= 3 for x in values)
                    or len(set(values)) != len(values)):
                raise ValueError('Zero to two distinct explicit fractions per street required')
            self.sizes.append(tuple(Fraction(str(x)) for x in values))
        self.hands, self.weights = [], []
        for name in ('oop', 'ip'):
            entries = config[name]
            if not isinstance(entries, list) or not 1 <= len(entries) <= 4:
                raise ValueError('Independent development limit: 1-4 explicit combos per side')
            hands, weights = [], []
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {'hand', 'weight'}:
                    raise ValueError('Explicit hand and weight required')
                hand, weight = concrete_hand(entry['hand']), entry['weight']
                if (hand in hands or set(hand) & set(board) or isinstance(weight, bool)
                        or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 < weight <= 1):
                    raise ValueError('Duplicate/blocked combo or invalid weight')
                hands.append(hand)
                weights.append(float(weight))
            self.hands.append(hands)
            self.weights.append(weights)
        self.deals = [(i, j) for i, a in enumerate(self.hands[0]) for j, b in enumerate(self.hands[1]) if not set(a) & set(b)]
        self.mass = math.fsum(self.weights[0][i]*self.weights[1][j] for i, j in self.deals)
        if not math.isfinite(self.mass) or self.mass <= 0:
            raise ValueError('No representable compatible joint mass')
        verify_reference()
        sys.path.insert(0, str(VENDOR))
        from games.river_holdem import card_id, evaluate_7
        if VENDOR.resolve() not in Path(sys.modules['games.river_holdem'].__file__).resolve().parents:
            raise ValueError('Independent ranker import was shadowed')
        self.sign = {}
        self.legal_rivers = {}
        ranks = {}
        for i, j in self.deals:
            dead = set(board) | set(self.hands[0][i]) | set(self.hands[1][j])
            rivers = tuple(card for card in DECK if card not in dead)
            if len(rivers) != 44:
                raise AssertionError('Each concrete deal must have 44 legal rivers')
            self.legal_rivers[i, j] = rivers
            for card in rivers:
                scores = []
                for side, index in ((0, i), (1, j)):
                    key = side, index, card
                    if key not in ranks:
                        ranks[key] = evaluate_7([card_id(c) for c in (*board, card, *self.hands[side][index])])
                    scores.append(ranks[key])
                self.sign[i, j, card] = (scores[0] > scores[1])-(scores[0] < scores[1])
        self.infos = []
        self.info_lookup = {}
        self.coalesced = {}
        self._compile()

    def actions(self, state):
        if state.phase != 'act':
            return ()
        if state.committed[state.player] < max(state.committed):
            return ('F', 'C')
        available = self.stack-state.committed[state.player]
        if available <= 0:
            raise AssertionError('All-in states must have no betting decisions')
        amounts = []
        for size in self.sizes[state.street]:
            amount = Fraction(min(available, (self.pot+sum(state.committed))*size))
            if amount.denominator != 1:
                raise ValueError('A future bet would require sub-cent rounding')
            amounts.append(int(amount))
        distinct = list(dict.fromkeys(amounts))
        if len(distinct) != len(amounts):
            self.coalesced[state.history] = amounts
        return ('X',)+tuple(f'B:{amount}' for amount in distinct)

    @staticmethod
    def close_round(state):
        return replace(state, phase='river' if state.street == 0 else 'showdown')

    def next_state(self, state, action):
        if action not in self.actions(state):
            raise ValueError('Illegal action')
        updated = replace(state, history=state.history+(action,))
        if action == 'F':
            return replace(updated, phase='fold', winner=1-state.player)
        if action == 'C':
            return self.close_round(replace(updated, committed=(max(state.committed),)*2))
        if action == 'X':
            return self.close_round(updated) if state.checked else replace(updated, checked=True, player=1-state.player)
        committed = list(state.committed)
        committed[state.player] += int(action.split(':')[1])
        return replace(updated, committed=tuple(committed), player=1-state.player)

    def terminal_utility(self, state, deal):
        total = self.pot+sum(state.committed)
        if state.phase == 'fold':
            collected = total if state.winner == 0 else 0
        elif state.phase == 'showdown':
            if state.committed[0] != state.committed[1] or state.river is None:
                raise AssertionError('Showdown requires matched chips and a public river')
            collected = total*(1+self.sign[deal[0], deal[1], state.river])/2
        else:
            raise ValueError('Not a terminal state')
        # Collect the whole pot, subtract own chips and the initial half-pot.
        # This refunds an uncalled own bet algebraically, without a special case.
        return collected-state.committed[0]-self.pot/2

    def _compile(self):
        self.records = [dict(state=None, deal=None, depth=0, actor=-1, info=-1, children=[], actions=())]
        edges = []
        self.info_depth = []
        cursor = 0
        while cursor < len(self.records):
            record = self.records[cursor]
            state, deal, depth = record['state'], record['deal'], record['depth']
            branches = []
            if state is None:
                branches = [(State(), pair, self.weights[0][pair[0]]*self.weights[1][pair[1]]/self.mass)
                            for pair in self.deals]
            elif state.phase == 'act':
                record['actor'] = state.player
                actions = self.actions(state)
                record['actions'] = actions
                key = state.player, self.hands[state.player][deal[state.player]], state.history
                if key not in self.info_lookup:
                    self.info_lookup[key] = len(self.infos)
                    self.infos.append(dict(player=key[0], hand=key[1], history=key[2], actions=actions))
                    self.info_depth.append(depth)
                info = self.info_lookup[key]
                if self.infos[info]['actions'] != actions or self.info_depth[info] != depth:
                    raise AssertionError('Inconsistent information set')
                record['info'] = info
                branches = [(self.next_state(state, action), deal, 1.0) for action in actions]
            elif state.phase == 'river':
                branches = [(replace(state, street=1, river=card, checked=False, player=0,
                                     history=state.history+(f'R:{card}',),
                                     phase='showdown' if state.committed[0] == self.stack else 'act'), deal, 1/44)
                            for card in self.legal_rivers[deal]]
            for action, (child_state, child_deal, probability) in enumerate(branches):
                child = len(self.records)
                record['children'].append(child)
                edges.append((cursor, child, action, probability))
                self.records.append(dict(state=child_state, deal=child_deal, depth=depth+1,
                                         actor=-1, info=-1, children=[], actions=()))
            if len(self.records) > 200000:
                raise ValueError('Independent development tree exceeds 200000 concrete nodes')
            cursor += 1
        self.parent, self.child, self.action = [np.array([edge[k] for edge in edges], dtype=int) for k in range(3)]
        self.chance_probability = np.array([edge[3] for edge in edges])
        self.actor = np.array([r['actor'] for r in self.records])
        self.info = np.array([r['info'] for r in self.records])
        self.info_player = np.array([r['player'] for r in self.infos])
        self.counts = np.array([len(r['actions']) for r in self.infos])
        self.width = int(max(self.counts))
        self.allowed = np.arange(self.width)[None, :] < self.counts[:, None]
        self.uniform = self.allowed/self.counts[:, None]
        self.decision_edges = np.flatnonzero(self.actor[self.parent] >= 0)
        self.decision_nodes = np.flatnonzero(self.actor >= 0)
        self.first_edge = np.full(len(self.records), -1, dtype=int)
        self.layers = []
        edge_depth = np.array([self.records[node]['depth'] for node in self.child])
        for depth in sorted(set(edge_depth)):
            edge = np.flatnonzero(edge_depth == depth)
            parents, starts = np.unique(self.parent[edge], return_index=True)
            self.layers.append((edge, parents, starts))
            self.first_edge[parents] = edge[starts]
        self.chance_reach = np.zeros(len(self.records))
        self.chance_reach[0] = 1
        for edge, _, _ in self.layers:
            self.chance_reach[self.child[edge]] = self.chance_reach[self.parent[edge]]*self.chance_probability[edge]
        self.leaf_values = np.zeros(len(self.records))
        for k, record in enumerate(self.records):
            if not record['children']:
                self.leaf_values[k] = self.terminal_utility(record['state'], record['deal'])

    def probabilities(self, profile):
        probability = self.chance_probability.copy()
        edge = self.decision_edges
        probability[edge] = profile[self.info[self.parent[edge]], self.action[edge]]
        return probability

    def reaches(self, profile):
        reach = np.ones((len(self.records), 2))
        probability = self.probabilities(profile)
        for edge, _, _ in self.layers:
            parent, child = self.parent[edge], self.child[edge]
            for side in (0, 1):
                reach[child, side] = reach[parent, side]*np.where(self.actor[parent] == side, probability[edge], 1)
        return reach, probability

    def values(self, profile, best_response=None, reach=None, probability=None):
        if reach is None or probability is None:
            reach, probability = self.reaches(profile)
        values = self.leaf_values.copy()
        for edge, parents, starts in reversed(self.layers):
            values[parents] = np.add.reduceat(probability[edge]*values[self.child[edge]], starts)
            if best_response is not None:
                chosen_nodes = parents[self.actor[parents] == best_response]
                if not len(chosen_nodes):
                    continue
                own_edges = edge[self.actor[self.parent[edge]] == best_response]
                parent = self.parent[own_edges]
                weights = self.chance_reach[parent]*reach[parent, 1-best_response]
                scores = np.bincount(self.info[parent]*self.width+self.action[own_edges],
                                     weights=weights*values[self.child[own_edges]]*(1 if best_response == 0 else -1),
                                     minlength=len(self.infos)*self.width).reshape(self.uniform.shape)
                scores[~self.allowed] = -np.inf
                choices = scores.argmax(axis=1)
                selected_edges = self.first_edge[chosen_nodes]+choices[self.info[chosen_nodes]]
                values[chosen_nodes] = values[self.child[selected_edges]]
        return values

    def evaluate(self, profile):
        reach, probability = self.reaches(profile)
        value = float(self.values(profile, reach=reach, probability=probability)[0]/SCALE)
        upper = float(self.values(profile, 0, reach, probability)[0]/SCALE)
        lower = float(self.values(profile, 1, reach, probability)[0]/SCALE)
        return {'oop_ev': value, 'ip_ev': -value, 'nash_conv_chips': upper-lower,
                'oop_lower_bound': lower, 'oop_upper_bound': upper}

    def export_profile(self, profile):
        return [dict(player=info['player'], hand=list(info['hand']), history=list(info['history']),
                     actions=list(info['actions']), probabilities=profile[k, :self.counts[k]].tolist())
                for k, info in enumerate(self.infos)]

    def import_profile(self, rows):
        profile = self.uniform.copy()
        seen = set()
        for row in rows:
            key = row['player'], tuple(sorted(row['hand'])), tuple(row['history'])
            if key not in self.info_lookup or key in seen:
                raise ValueError('Unknown or duplicate information set')
            seen.add(key)
            index = self.info_lookup[key]
            actions, probabilities = row['actions'], np.asarray(row['probabilities'], dtype=float)
            if (len(set(actions)) != len(actions) or set(actions) != set(self.infos[index]['actions'])
                    or probabilities.shape != (len(actions),) or not np.isfinite(probabilities).all()
                    or (probabilities < 0).any() or not math.isclose(float(sum(probabilities)), 1, rel_tol=0, abs_tol=1e-12)):
                raise ValueError('Invalid information-set strategy')
            profile[index, :self.counts[index]] = [probabilities[actions.index(action)] for action in self.infos[index]['actions']]
        if len(seen) != len(self.infos):
            raise ValueError('Incomplete profile')
        return profile


class IndependentCFR:
    def __init__(self, game):
        self.game = game
        self.regret = np.zeros_like(game.uniform)
        self.average_sum = np.zeros_like(game.uniform)
        self.iterations = 0

    def average(self):
        total = self.average_sum.sum(axis=1, keepdims=True)
        return np.divide(self.average_sum, total, out=self.game.uniform.copy(), where=total > 0)

    def step(self):
        game = self.game
        for side in (0, 1):
            positive = np.maximum(self.regret, 0)
            total = positive.sum(axis=1, keepdims=True)
            strategy = np.divide(positive, total, out=game.uniform.copy(), where=total > 0)
            reach, probability = game.reaches(strategy)
            values = game.values(strategy, reach=reach, probability=probability)
            nodes = game.decision_nodes[game.actor[game.decision_nodes] == side]
            average_weight = np.bincount(game.info[nodes], weights=game.chance_reach[nodes]*reach[nodes, side],
                                         minlength=len(game.infos))
            self.average_sum += (self.iterations+1)*average_weight[:, None]*strategy
            edge = game.decision_edges[game.actor[game.parent[game.decision_edges]] == side]
            parent = game.parent[edge]
            increments = np.bincount(game.info[parent]*game.width+game.action[edge],
                                     weights=game.chance_reach[parent]*reach[parent, 1-side]
                                     *(values[game.child[edge]]-values[parent])*(1 if side == 0 else -1),
                                     minlength=len(game.infos)*game.width).reshape(game.uniform.shape)
            self.regret = np.maximum(0, self.regret+increments)
        self.iterations += 1

    def train(self, iterations):
        if type(iterations) is not int or not 20 <= iterations <= 10000 or self.iterations:
            raise ValueError('Fresh development trainer requires 20-10000 iterations')
        checkpoints = []
        marks = {iterations//4, iterations//2, iterations}
        for _ in range(iterations):
            self.step()
            if self.iterations in marks:
                checkpoints.append(dict(iterations=self.iterations, **self.game.evaluate(self.average())))
        return checkpoints
