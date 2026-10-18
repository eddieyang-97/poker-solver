"""Differential adapter: independent full turn training, tree and policy checks."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from benchmarks.reference_worker import COMMIT
from benchmarks.turn_reference import DECK, IndependentTurnGame
from poker_spot.turn import TurnSolver

ROOT = Path(__file__).resolve().parents[1]


def product_solver(config):
    text = [','.join(f'{row["hand"]}:{row["weight"]}' for row in config[side]) for side in ('oop', 'ip')]
    return TurnSolver(','.join(config['board']), *text, config['pot'], config['stack'],
                      config['turn_bet_sizes'], config['river_bet_sizes'])


def history_location(history):
    name, river = 'turn', None
    for token in history:
        if token == 'X':
            name += '/check'
        elif token == 'C':
            name += '/call'
        elif token.startswith('B:'):
            amount = int(token[2:])/100
            name += '/bet_'+(str(int(amount)) if amount.is_integer() else repr(amount))
        elif token.startswith('R:') and river is None:
            name += '/river'
            river = token[2:]
        else:
            raise ValueError('Unsupported public history in independent profile')
    return name, river


def action_label(action):
    if action in ('X', 'C', 'F'):
        return {'X': 'check', 'C': 'call', 'F': 'fold'}[action]
    if action.startswith('B:'):
        amount = int(action[2:])/100
        return 'bet_'+(str(int(amount)) if amount.is_integer() else repr(amount))
    raise ValueError('Unknown action token')


def mapping(game, solver):
    for side in (0, 1):
        actual = {frozenset(h): float(w) for h, w in zip(solver.hands[side], solver.weights[side], strict=True)}
        expected = {frozenset(h): w for h, w in zip(game.hands[side], game.weights[side], strict=True)}
        if actual != expected:
            raise ValueError('Input card/weight expansion differs between models')
    expected_support = set()
    for name, node in solver.nodes.items():
        side = node.player
        for hand in game.hands[side]:
            opponents = [h for h in game.hands[1-side] if not set(hand) & set(h)]
            if not opponents:
                continue
            contexts = [None] if node.street == 0 else [card for card in DECK
                       if card not in game.board and card not in hand and any(card not in other for other in opponents)]
            expected_support.update((side, frozenset(hand), name, card) for card in contexts)
    seen, rows = set(), []
    for info in game.infos:
        side, hand = info['player'], frozenset(info['hand'])
        name, river = history_location(info['history'])
        support = side, hand, name, river
        if support not in expected_support or support in seen:
            raise ValueError('Independent tree has an unsupported/duplicate information set')
        seen.add(support)
        node = solver.nodes[name]
        if node.player != side or node.street != (river is not None):
            raise ValueError('Actor/street mismatch')
        labels = [action_label(token) for token in info['actions']]
        if len(set(labels)) != len(labels) or set(labels) != set(node.actions):
            raise ValueError('Action tree or exact bet amount differs; no rounding/adaptation allowed')
        index = next(i for i, h in enumerate(solver.hands[side]) if frozenset(h) == hand)
        location = (index,) if river is None else (solver.rivers.index(river), index)
        rows.append((node, location, [node.actions.index(label) for label in labels]))
    if seen != expected_support:
        raise ValueError('Product contains supported information sets absent from independent tree')
    return rows


def product_profile(game, solver):
    profile = game.uniform.copy()
    averages = {name: node.average() for name, node in solver.nodes.items()}
    for index, (node, location, order) in enumerate(mapping(game, solver)):
        profile[index, :game.counts[index]] = averages[node.name][location][order]
    return profile


def install_reference_profile(game, solver, profile):
    for index, (node, location, order) in enumerate(mapping(game, solver)):
        node.strategy_sum[location] = 0
        for action, target in enumerate(order):
            node.strategy_sum[location+(target,)] = profile[index, action]


def product_evaluation(solver, diagnostics=None):
    result = dict(solver.diagnostics() if diagnostics is None else diagnostics)
    best0 = solver._walk(solver.root, *solver.weights, best_response=0)[0]
    best1 = solver._walk(solver.root, *solver.weights, best_response=1)[1]
    result.update(oop_lower_bound=-float(solver.weights[1] @ best1/solver.mass),
                  oop_upper_bound=float(solver.weights[0] @ best0/solver.mass))
    result['nash_conv_chips'] = result['raw_nash_conv_chips']
    return result


def independent_train(config, iterations):
    command = [sys.executable, '-I', str(ROOT/'benchmarks/turn_reference_worker.py'), '--iterations', str(iterations)]
    process = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True, check=True, timeout=120,
                             env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    exported = json.loads(process.stdout)
    if (exported['config'] != config or exported['iterations'] != iterations or exported['pid'] == os.getpid()
            or exported['product_modules_loaded'] or exported['ranker_commit'] != COMMIT):
        raise ValueError('Unexpected independent trainer provenance/configuration')
    source_files = {'benchmarks/turn_reference.py', 'benchmarks/turn_reference_worker.py', 'benchmarks/reference_worker.py'}
    if set(exported['source_sha256_lf']) != source_files:
        raise ValueError('Incomplete/unexpected independent source provenance')
    for name, digest in exported['source_sha256_lf'].items():
        if hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != digest:
            raise ValueError('Independent worker source mismatch')
    return exported


def compare_fixture(fixture, iterations=2000, reference_iterations=4000):
    config = fixture['config']
    if not config['turn_bet_sizes']:
        raise ValueError('Full-turn training fixtures require a strategic turn bet')
    game = IndependentTurnGame(config)
    solver = product_solver(config)
    started = time.perf_counter()
    result = solver.solve(iterations)
    product_seconds = time.perf_counter()-started
    own = product_profile(game, solver)
    product_external = game.evaluate(own)
    exported = independent_train(config, reference_iterations)
    reference = game.import_profile(exported['profile'])
    reference_external = game.evaluate(reference)
    transfer = product_solver(config)
    install_reference_profile(game, transfer, reference)
    reference_product = product_evaluation(transfer)
    product_internal = product_evaluation(solver, result['diagnostics'])
    diagnostics = (product_external, product_internal, reference_external, reference_product, exported['checkpoints'][-1])
    metrics = ('oop_ev', 'ip_ev', 'nash_conv_chips', 'oop_lower_bound', 'oop_upper_bound')
    if not all(math.isfinite(row[key]) for row in diagnostics for key in metrics):
        raise ValueError('Nonfinite value or best-response diagnostic')
    numeric = max(abs(evaluated[key]-expected[key]) for evaluated, expected in (
        (product_external, product_internal), (reference_external, reference_product),
        (reference_external, exported['checkpoints'][-1])) for key in metrics)
    tolerance, convergence = 1e-8, config['pot']*0.005
    value_delta = abs(product_external['oop_ev']-reference_external['oop_ev'])
    bound = product_external['nash_conv_chips']+reference_external['nash_conv_chips']+tolerance
    failures = []
    if numeric > tolerance:
        failures.append('Independent same-policy value/BR or reverse transfer differs')
    if value_delta > bound:
        failures.append('Separately trained values differ beyond combined convergence gaps')
    if max(product_external['nash_conv_chips'], reference_external['nash_conv_chips']) > convergence:
        failures.append('Convergence exceeds unchanged 0.5%-of-pot gate')
    for label, evaluated in (('product', product_external), ('reference', reference_external)):
        if (evaluated['oop_ev'] < evaluated['oop_lower_bound']-tolerance
                or evaluated['oop_ev'] > evaluated['oop_upper_bound']+tolerance
                or evaluated['nash_conv_chips'] < -tolerance):
            failures.append(f'{label}: invalid best-response interval')
        if 'analytic_oop_ev' in fixture and abs(evaluated['oop_ev']-fixture['analytic_oop_ev']) > evaluated['nash_conv_chips']+tolerance:
            failures.append(f'{label}: analytic singleton value lies outside convergence bound')
        if ('analytic_oop_ev' in fixture and not evaluated['oop_lower_bound']-tolerance
                <= fixture['analytic_oop_ev'] <= evaluated['oop_upper_bound']+tolerance):
            failures.append(f'{label}: analytic singleton value lies outside best-response interval')
    if abs(result['diagnostics']['zero_sum_residual']) > tolerance:
        failures.append('Product zero-sum residual differs')
    mixed = own.copy()
    mixed[game.info_player == 1] = reference[game.info_player == 1]
    reverse_mixed = own.copy()
    reverse_mixed[game.info_player == 0] = reference[game.info_player == 0]
    cross = game.evaluate(mixed)['oop_ev']
    reverse_cross = game.evaluate(reverse_mixed)['oop_ev']
    if not product_external['oop_lower_bound']-tolerance <= cross <= reference_external['oop_upper_bound']+tolerance:
        failures.append('Product/reference cross-play violates security bounds')
    if not reference_external['oop_lower_bound']-tolerance <= reverse_cross <= product_external['oop_upper_bound']+tolerance:
        failures.append('Reference/product cross-play violates security bounds')
    analytical_frequencies = []
    for target in fixture.get('analytic_turn_frequencies', []):
        text = target['hand']
        key = target['player'], tuple(sorted((text[:2], text[2:]))), tuple(target['history'])
        index = game.info_lookup[key]
        action = game.infos[index]['actions'].index(target['action'])
        measured = {label: float(profile[index, action]) for label, profile in (('product', own), ('reference', reference))}
        analytical_frequencies.append(dict(target=target, computed=measured, absolute_tolerance=0.04))
        if any(abs(value-target['frequency']) > 0.04 for value in measured.values()):
            failures.append('Analytical mixed-turn frequency differs beyond existing 0.04 frequency allowance')
    return {'id': fixture['id'], 'config': config, 'product_iterations': iterations,
            'reference_iterations': reference_iterations, 'product_wall_seconds': product_seconds,
            'product_diagnostics': result['diagnostics'], 'product_policy_in_product': product_internal,
            'product_policy_in_reference': product_external,
            'reference_policy_in_reference': reference_external, 'reference_policy_in_product': reference_product,
            'same_policy_numeric_delta': numeric, 'trained_value_delta': value_delta, 'combined_gap_bound': bound,
            'cross_play_oop_ev': {'product_oop_vs_reference_ip': cross, 'reference_oop_vs_product_ip': reverse_cross},
            'gates': {'same_policy_numeric_chips': tolerance, 'convergence_chips': convergence},
            'analytic_oop_ev': fixture.get('analytic_oop_ev'), 'reference_export': exported,
            'analytical_frequency_checks': analytical_frequencies,
            'product_profile': game.export_profile(own), 'failures': failures}
