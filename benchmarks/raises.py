"""Development-only exact-tree and bidirectional policy validation for raises."""
import hashlib
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from benchmarks.harness import (REFERENCE_COMMIT, SCALE, action_tokens, evaluate_profile,
                                hand_key, import_reference, verify_reference)
from games.river_holdem import RiverHoldemConfig, RiverHoldemGame
from algorithms.naive_eval import best_response_value_naive
from poker_spot.core import Node
from poker_spot.raises import RaiseRiverSolver, label

ROOT = Path(__file__).resolve().parents[1]


def upstream_config(config):
    # A second parser: fixture/reference input is concrete-combo text only.
    players = []
    for side in ('oop_range', 'ip_range'):
        hands, weights = [], []
        for token in config[side].split(','):
            hand, separator, weight = token.partition(':')
            if len(hand) != 4 or hand in hands:
                raise ValueError('Reference adapter requires distinct explicit concrete combos')
            hands.append(hand)
            weights.append(float(weight) if separator else 1.0)
        players.append({'hands': hands, 'weights': weights})
    bets, raises = config.get('bet_sizes'), config.get('raise_sizes')
    if 'bet_amounts_cents' in config or 'raise_to_cents' in config:
        if bets is not None or raises is not None or len(config['bet_amounts_cents']) != 1:
            raise ValueError('Exact reference comparison supports one opening amount; no mixed sizing or tree adaptation')
        with localcontext(Context(prec=600)):
            pot, stack = [Decimal(str(config[k]))*100 for k in ('pot', 'stack')]
        if any(v != v.to_integral_value() for v in (pot, stack)):
            raise ValueError('Exact reference pot/stack must be cent-exact')
        pot, stack = int(pot), int(stack)
        bet = config['bet_amounts_cents'][0]
        targets = config['raise_to_cents']
        if (type(bet) is not int or not 0 < bet < stack or not isinstance(targets, list)
                or not 1 <= len(targets) <= 2 or targets != sorted(set(targets))
                or any(type(t) is not int or not bet < t <= stack or t-bet < bet and t != stack for t in targets)):
            raise ValueError('Invalid exact reference bet/raise totals')
        def encoded(numerator, denominator):
            value = Fraction(numerator, denominator)
            return {'numerator': value.numerator, 'denominator': value.denominator}
        bets = [encoded(bet, pot)]
        raises = [encoded(t-bet, pot+2*bet) for t in targets]
    return {'board': config['board'].split(','), 'pot': round(config['pot']*100), 'stack': round(config['stack']*100),
            'bet_sizes': bets, 'raise_sizes': raises,
            'include_all_in': False, 'max_raises': 2, 'players': players}


def reference_game(config):
    verify_reference()
    u = upstream_config(config)
    game = RiverHoldemGame(RiverHoldemConfig(
        board=u['board'], pot=u['pot'], stacks=(u['stack'],)*2, bet_sizes=reference_sizes(u['bet_sizes']),
        oop_first_raises=reference_sizes(u['raise_sizes']), ip_first_raises=reference_sizes(u['raise_sizes']), include_all_in=False, max_raises=2,
        ranges=tuple(p['hands'] for p in u['players']), range_weights=tuple(p['weights'] for p in u['players'])))
    return game, u


def reference_sizes(values):
    return [Fraction(v['numerator'], v['denominator']) if isinstance(v, dict) else v for v in values]


def check_tree(solver, game):
    seen = set()
    bets, raises = solver.sizes, solver.raise_sizes
    if solver.exact_sizing:
        if len(solver.bet_cents) != 1:
            raise ValueError('Exact reference comparison supports one opening amount')
        bet = solver.bet_cents[0]
        bets = [Fraction(bet, solver.pot_cents)]
        raises = [Fraction(t-bet, solver.pot_cents+2*bet) for t in solver.raise_to_cents]
    if (game.base_pot != solver.pot_cents or game.stacks != (solver.stack_cents,)*2
            or set(game.config.board) != set(solver.board) or game.include_all_in is not False or game.max_raises != 2
            or game.bet_sizes != bets or game.oop_first_raises != raises or game.ip_first_raises != raises):
        raise ValueError('Declared board/pot/stacks/sizing/raise cap differ')
    for p in (0, 1):
        hands = solver.h0 if p == 0 else solver.h1
        weights = solver.w0 if p == 0 else solver.w1
        actual = {frozenset(h): w for h, w in zip(hands, weights, strict=True)}
        expected = {hand_key(h): w for h, w in zip(game.hands[p], game.hand_weights[p], strict=True)}
        if set(actual) != set(expected) or any(not math.isclose(actual[k], expected[k], rel_tol=1e-13, abs_tol=0) for k in actual):
            raise ValueError('Reference hand identity/card removal/weights differ')

    def visit(state, node):
        if game.is_terminal(state):
            if isinstance(node, Node) or tuple(state.contrib) != node.contributions or state.terminal_winner != node.winner:
                raise ValueError('Terminal contributions/winner differ')
            return
        key = game.infoset_key(state, state.player)
        if not isinstance(node, Node) or node.name != key or node.player != state.player:
            raise ValueError('History/actor/information-set mapping differs')
        if solver.locations[key]['contributions_cents'] != list(state.contrib):
            raise ValueError('Intermediate chip ledger differs')
        seen.add(key)
        labels = reference_labels(game, state)
        if len(set(labels)) != len(labels) or set(labels) != set(node.actions):
            raise ValueError('Exact action tree differs; no rounding, filtering or implicit all-ins')
        for action, name in zip(game.legal_actions(state), labels, strict=True):
            visit(game.next_state(state, action), node.children[node.actions.index(name)])
    visit(game.initial_state(), solver.root)
    if seen != set(solver.nodes):
        raise ValueError('Product contains an unmapped information set')


def reference_labels(game, state):
    facing = max(state.contrib) > state.contrib[state.player]
    return [('call' if facing else 'check') if a.label == 'c' else 'fold' if a.label == 'f' else
            label('bet', state.contrib[state.player]+a.amount) if a.label == 'b' else
            label('raise', max(state.contrib)+a.amount) for a in game.legal_actions(state)]


def product_profile(solver, game):
    check_tree(solver, game)
    profile = {0: {}, 1: {}}

    def visit(state):
        if game.is_terminal(state):
            return
        side = state.player
        key = game.infoset_key(state, side)
        node = solver.nodes[key]
        hands = solver.h0 if side == 0 else solver.h1
        index = {frozenset(h): i for i, h in enumerate(hands)}
        names = reference_labels(game, state)
        profile[side][key] = (action_tokens(game.legal_actions(state)),
                              [[float(node.average()[index[hand_key(h)], node.actions.index(name)]) for name in names]
                               for h in game.hands[side]])
        for action in game.legal_actions(state):
            visit(game.next_state(state, action))
    visit(game.initial_state())
    return profile


def set_profile(solver, game, profile):
    check_tree(solver, game)
    if set(profile) != {0, 1} or any(set(profile[p]) != {k for k, n in solver.nodes.items() if n.player == p} for p in (0, 1)):
        raise ValueError('Transferred information-set support differs')

    def visit(state):
        if game.is_terminal(state):
            return
        side = state.player
        key = game.infoset_key(state, side)
        node = solver.nodes[key]
        tokens, matrix = profile[side][key]
        if tokens != action_tokens(game.legal_actions(state)):
            raise ValueError('Transferred action order differs')
        matrix = np.asarray(matrix, dtype=float)
        if (matrix.shape != (len(game.hands[side]), len(tokens)) or not np.isfinite(matrix).all()
                or (matrix < 0).any() or not np.allclose(matrix.sum(axis=1), 1, rtol=0, atol=1e-12)):
            raise ValueError('Transferred policy has invalid probabilities')
        names = reference_labels(game, state)
        hands = solver.h0 if side == 0 else solver.h1
        for j, h in enumerate(game.hands[side]):
            i = next(i for i, hand in enumerate(hands) if frozenset(hand) == hand_key(h))
            for a, name in enumerate(names):
                node.avg_sum[i, node.actions.index(name)] = matrix[j, a]
        for action in game.legal_actions(state):
            visit(game.next_state(state, action))
    visit(game.initial_state())


def product_value(solver):
    cfv = {}
    root = solver._eval(solver.root, solver.w0, solver.w1, collect=cfv)
    br = [float(w@solver._eval(solver.root, solver.w0, solver.w1, side)[side]/solver.prob)
          for side, w in enumerate((solver.w0, solver.w1))]
    return {'root': [float(w@root[p]/solver.prob) for p, w in enumerate((solver.w0, solver.w1))],
            'br': br, 'gap': sum(br), 'nodes': cfv}


def policy_delta(solver, game, profile):
    reference = evaluate_profile(game, profile)
    reference['br'] = [best_response_value_naive(game, p, profile[1-p])/SCALE-game.base_pot/(2*SCALE) for p in (0, 1)]
    actual = product_value(solver)
    error = max(abs(actual['root'][p]-reference['root'][p]) for p in (0, 1))
    error = max(error, abs(actual['gap']-reference['gap']))
    error = max(error, *(abs(actual['br'][p]-reference['br'][p]) for p in (0, 1)))
    for (side, key), row in reference['nodes'].items():
        names = reference_labels(game, state_for_key(game, key))
        node = solver.nodes[key]
        error = max(error, abs(actual['nodes'][key]['joint_reach']-float(row['reach'].sum())))
        hands = solver.h0 if side == 0 else solver.h1
        for i, hand in enumerate(game.hands[side]):
            j = next(j for j, h in enumerate(hands) if frozenset(h) == hand_key(hand))
            for a, name in enumerate(names):
                x, y = actual['nodes'][key]['ev'][j, node.actions.index(name)], row['q'][i, a]
                if np.isfinite(x) != np.isfinite(y):
                    raise ValueError('Conditional action EV support differs')
                if np.isfinite(x):
                    error = max(error, abs(x-y))
    return error, actual, reference


def state_for_key(game, key):
    state = game.initial_state()
    if key == 'root':
        return state
    for token in key.split('/'):
        actions = game.legal_actions(state)
        state = game.next_state(state, actions[action_tokens(actions).index(token)])
    return state



def recommendations(solver, game, profile, values):
    """Query-hand mixtures with conditional regret and actual joint hand/node mass."""
    rows = []
    for name, node in solver.nodes.items():
        side = node.player
        hand = (solver.h0 if side == 0 else solver.h1)[0]
        i = next(i for i, h in enumerate(game.hands[side]) if hand_key(h) == frozenset(hand))
        names = reference_labels(game, state_for_key(game, name))
        frequency = dict(zip(names, profile[side][name][1][i], strict=True))
        q = values['nodes'][name]['ev'][0]
        reached = bool(np.isfinite(q).all())
        regrets = np.max(q)-q if reached else [None]*len(q)
        cfv = values['nodes'][name]
        rows.append({'side': side, 'hand': list(hand), 'node': name,
                     'joint_node_reach': cfv['joint_reach'],
                     'joint_queried_hand_reach': float(cfv['own_reach'][0]*cfv['opponent_reach'][0]/solver.prob),
                     'actions': {action: {'frequency': float(frequency[action]),
                                          'ev': float(q[a]) if reached else None,
                                          'regret': float(regrets[a]) if reached else None}
                                 for a, action in enumerate(node.actions)},
                     'mixture_conditional_regret': float(sum(frequency[a]*regrets[j] for j, a in enumerate(node.actions))) if reached else None})
    return rows


def compare(config, iterations=2000, reference_iterations=4000):
    solver = RaiseRiverSolver(**config)
    game, upstream = reference_game(config)
    check_tree(solver, game)
    started = time.perf_counter()
    result = solver.solve(iterations, ''.join(solver.h0[0]), ''.join(solver.h1[0]))
    elapsed = time.perf_counter()-started
    local_profile = product_profile(solver, game)
    delta, local, _ = policy_delta(solver, game, local_profile)
    child = subprocess.run([sys.executable, '-I', str(ROOT/'benchmarks/raise_reference_worker.py'),
                            '--iterations', str(reference_iterations)], input=json.dumps(upstream),
                           capture_output=True, text=True, timeout=120,
                           env=dict({k: v for k, v in os.environ.items() if k.upper() in
                                     {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'VIRTUAL_ENV'}},
                                    OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    if child.returncode:
        raise ValueError('Independent worker failed: '+child.stderr[-1000:])
    exported = json.loads(child.stdout)
    if (exported['reference_commit'] != REFERENCE_COMMIT or exported['product_modules_loaded']
            or exported['config'] != upstream or exported['iterations'] != reference_iterations):
        raise ValueError('Independent training provenance differs')
    reference_policy = import_reference(game, exported)
    set_profile(solver, game, reference_policy)
    other_delta, transferred, reference = policy_delta(solver, game, reference_policy)
    delta = max(delta, other_delta)
    gate = config['pot']*0.005
    failures = []
    if delta > 1e-8:
        failures.append('Same-policy numerical disagreement')
    if max(local['gap'], reference['gap']) > gate:
        failures.append('Training convergence gate')
    ev_delta = abs(local['root'][0]-reference['root'][0])
    if ev_delta > local['gap']+reference['gap']+1e-8:
        failures.append('Separately trained EV outside combined gaps')
    if abs(exported['checkpoints'][-1]['raw_average_exploitability_cents']*2/SCALE-reference['gap']) > 1e-8:
        failures.append('Reference exploitability normalization differs')
    return {'input': config, 'product_root_ev': local['root'][0], 'reference_root_ev': reference['root'][0],
            'product_nashconv': local['gap'], 'reference_nashconv': reference['gap'],
            'product_best_response_ev': local['br'], 'reference_best_response_ev': reference['br'],
            'reference_policy_product_gap': transferred['gap'], 'same_policy_max_delta': delta,
            'query_recommendations': {'product': recommendations(solver, game, local_profile, local),
                                      'reference': recommendations(solver, game, reference_policy, transferred)},
            'trained_ev_delta': ev_delta, 'convergence_gate_chips': gate, 'failures': failures,
            'product_seconds': elapsed, 'product_output': result,
            'reference_profile_sha256': hashlib.sha256(json.dumps(exported['players'], sort_keys=True).encode()).hexdigest(),
            'reference_metadata': {k: v for k, v in exported.items() if k != 'players'},
            'reference_export': exported, 'product_profile': local_profile}
