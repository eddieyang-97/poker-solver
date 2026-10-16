"""Development-only differential benchmark; never imported by the hosted service."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time
import tracemalloc

import numpy as np

from poker_spot.core import RiverSolver, rank7

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor' / 'noambrown'
REFERENCE_COMMIT = '6a10442877ffc8fd28af93e16e279b9bbdd97b2a'
SCALE = 100


def verify_reference():
    manifest = json.loads((VENDOR / 'provenance.json').read_text())
    if manifest['commit'] != REFERENCE_COMMIT:
        raise ValueError('Unexpected reference version')
    for name, expected in manifest['sha256_lf'].items():
        content = (VENDOR / name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f'Reference source changed: {name}')


verify_reference()
sys.path.insert(0, str(VENDOR))
from algorithms.vector_cfr import VectorCFRConfig, VectorCFRTrainer
from algorithms.naive_eval import exploitability_naive, showdown_values_naive
from algorithms.vector_eval import (
    action_tokens, build_blocked_indices, build_strength_summary,
    fold_values, valid_opp_weights,
)
from games.river_holdem import RiverHoldemConfig, RiverHoldemGame, card_str, parse_cards, parse_hand

for _module in ('algorithms.vector_cfr', 'algorithms.vector_eval', 'algorithms.naive_eval', 'games.river_holdem'):
    if VENDOR.resolve() not in Path(sys.modules[_module].__file__).resolve().parents:
        raise ValueError('Reference module was shadowed by another installed package')


def validate_fixture(fixture):
    required = {'id', 'description', 'board', 'pot', 'stack', 'bet_sizes', 'oop', 'ip',
                'rake', 'max_raises', 'include_all_in'}
    if set(fixture) != required:
        raise ValueError('Fixture fields must exactly declare the supported game')
    if fixture['rake'] != 0 or fixture['max_raises'] != 0 or fixture['include_all_in'] is not False:
        raise ValueError('Same-tree comparison requires zero rake, no raises or implicit all-ins')
    board = fixture['board']
    if len(board) != 5 or len(set(board)) != 5:
        raise ValueError('Five distinct board cards required')
    parse_cards(board)
    for name in ('pot', 'stack'):
        value = fixture[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Finite positive amounts required')
        if not math.isclose(value*SCALE, round(value*SCALE), abs_tol=1e-7, rel_tol=0):
            raise ValueError('Amount not exactly representable in reference units')
    sizes = fixture['bet_sizes']
    if not 1 <= len(sizes) <= 3 or any(isinstance(x, bool) or not math.isfinite(x) or not 0 < x <= 3 for x in sizes):
        raise ValueError('One to three finite sizes in (0,3] required')
    amounts = [min(fixture['stack'], fixture['pot']*size) for size in sizes]
    if len(set(amounts)) != len(amounts):
        raise ValueError('Sizes collapse to duplicate actions')
    if amounts != sorted(amounts):
        raise ValueError('Canonical sizes must be in ascending order')
    for amount in amounts:
        if not math.isclose(amount*SCALE, round(amount*SCALE), abs_tol=1e-7, rel_tol=0):
            raise ValueError('Bet would be rounded by reference; trees would differ')
    for side in ('oop', 'ip'):
        seen = set()
        for entry in fixture[side]:
            if set(entry) != {'hand', 'weight'}:
                raise ValueError('Explicit combo and weight required')
            key = parse_hand(entry['hand'])
            weight = entry['weight']
            if key in seen or isinstance(weight, bool) or not math.isfinite(weight) or not 0 < weight <= 1:
                raise ValueError('Duplicate combo or invalid positive weight')
            seen.add(key)


def make_game(fixture, raises=0):
    validate_fixture(fixture)
    game = RiverHoldemGame(RiverHoldemConfig(
        board=fixture['board'], pot=round(SCALE*fixture['pot']),
        stacks=(round(SCALE*fixture['stack']),)*2, bet_sizes=fixture['bet_sizes'],
        include_all_in=False, max_raises=raises,
        ranges=tuple([x['hand'] for x in fixture[side]] for side in ('oop', 'ip')),
        range_weights=tuple([x['weight'] for x in fixture[side]] for side in ('oop', 'ip'))))
    return game


def hand_key(hand):
    return frozenset(card_str(c) for c in hand.cards)


def state_mapping(game, fixture):
    """Check the complete legal tree before mapping any strategies."""
    names = {}
    amounts = {round(min(fixture['stack'], fixture['pot']*b)*SCALE): b for b in fixture['bet_sizes']}

    def visit(state):
        if game.is_terminal(state):
            return
        history = state.history
        if not history:
            name = 'oop_first'
        elif history == ('c',):
            name = 'ip_after_oop_check'
        elif len(history) in (1, 2) and history[-1].startswith('b'):
            size = amounts[int(history[-1][1:])]
            name = f'{"ip_facing_oop_bet" if len(history) == 1 else "oop_facing_ip_bet"}_{size:g}'
        else:
            raise ValueError('Reference tree contains unsupported history')
        actions = game.legal_actions(state)
        facing = max(state.contrib) > state.contrib[state.player]
        expected = {'c', 'f'} if facing else {'c'} | {f'b{a}' for a in amounts}
        if set(action_tokens(actions)) != expected:
            raise ValueError('Reference action set differs from restricted tree')
        names[game.infoset_key(state, state.player)] = name
        for action in actions:
            visit(game.next_state(state, action))
    visit(game.initial_state())
    return names


def product_profile(solver, game, mapping):
    profile = {0: {}, 1: {}}
    core_hands = (solver.h0, solver.h1)

    def visit(state):
        if game.is_terminal(state):
            return
        side = state.player
        key = game.infoset_key(state, side)
        node = solver.nodes[mapping[key]]
        actions = game.legal_actions(state)
        labels = []
        for action in actions:
            if action.label == 'c':
                label = 'call' if max(state.contrib) > state.contrib[side] else 'check'
            elif action.label == 'f':
                label = 'fold'
            else:
                matches = [b for b in solver.sizes if abs(min(solver.stack, b*solver.pot)*SCALE-action.amount) < 1e-7]
                if len(matches) != 1:
                    raise ValueError('Bet mapping is not unique')
                label = f'bet_{matches[0]:g}pot'
            labels.append(label)
        if set(labels) != set(node.actions):
            raise ValueError('Product action set differs from reference')
        index = {frozenset(hand): i for i, hand in enumerate(core_hands[side])}
        if set(index) != {hand_key(h) for h in game.hands[side]}:
            raise ValueError('Card removal differs between engines')
        matrix = node.average()
        profile[side][key] = (action_tokens(actions), [
            [float(matrix[index[hand_key(hand)], node.actions.index(label)]) for label in labels]
            for hand in game.hands[side]])
        for action in actions:
            visit(game.next_state(state, action))
    visit(game.initial_state())
    return profile


def evaluate_profile(game, profile):
    """Evaluate either engine's policy using the reference's own terminal values.

    The upstream best-response/exploitability routines are used separately below.
    This traversal adds conditional Q-values and actual joint node reach.
    """
    summaries = {p: build_strength_summary(game.hands[1-p]) for p in (0, 1)}
    blocked = {p: build_blocked_indices(game.hands[p], summaries[p]) for p in (0, 1)}
    joint = sum(w*v for w, v in zip(game.hand_weights[0], valid_opp_weights(blocked[0], game.hand_weights[1])))
    if joint <= 0:
        raise ValueError('No compatible chance pairs')
    collected = {}

    def traverse(state, target, own, opponent):
        valid = np.asarray(valid_opp_weights(blocked[target], opponent))
        if game.is_terminal(state):
            if state.terminal_winner is not None:
                payoff = (game.pot_total(state)-state.contrib[target]
                          if target == state.terminal_winner else -state.contrib[target])
                value = fold_values(payoff, blocked[target], opponent)
            else:
                value = showdown_values_naive(game.hands[target], game.hands[1-target],
                                              opponent, game.pot_total(state), state.contrib[target])
            return (np.asarray(value)-game.base_pot/2*valid)/SCALE
        actor = state.player
        key = game.infoset_key(state, actor)
        actions = game.legal_actions(state)
        tokens, strategy = profile[actor][key]
        if tokens != action_tokens(actions):
            raise ValueError('Policy action order mismatch')
        strategy = np.asarray(strategy)
        values = []
        for i, action in enumerate(actions):
            if actor == target:
                values.append(traverse(game.next_state(state, action), target, own*strategy[:, i], opponent))
            else:
                values.append(traverse(game.next_state(state, action), target, own, opponent*strategy[:, i]))
        matrix = np.stack(values, axis=1)
        if actor != target:
            return matrix.sum(axis=1)
        q = np.divide(matrix, valid[:, None], out=np.full_like(matrix, np.nan), where=valid[:, None] > 1e-14)
        collected[(actor, key)] = {'q': q, 'reach': own*valid/joint, 'strategy': strategy}
        return (matrix*strategy).sum(axis=1)

    roots = []
    for side in (0, 1):
        roots.append(float(np.asarray(game.hand_weights[side]) @ traverse(
            game.initial_state(), side, np.asarray(game.hand_weights[side]),
            np.asarray(game.hand_weights[1-side])))/joint)
    gap = max(0.0, 2*exploitability_naive(game, profile)/SCALE)
    return {'root': roots, 'gap': gap, 'nodes': collected}


def measured(function):
    # Python allocations only, not RSS/native NumPy allocations; benchmark-only.
    tracemalloc.start()
    start = time.perf_counter()
    result = function()
    elapsed = time.perf_counter()-start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {'seconds': elapsed, 'python_peak_bytes': peak}


def compare_fixture(fixture, iterations=1500, reference_iterations=4000):
    game = make_game(fixture)
    mapping = state_mapping(game, fixture)
    ranges = [','.join(f'{x["hand"]}:{x["weight"]}' for x in fixture[p]) for p in ('oop', 'ip')]
    solver = RiverSolver(','.join(fixture['board']), *ranges, fixture['pot'], fixture['stack'], fixture['bet_sizes'])
    local, local_cost = measured(lambda: solver.solve(iterations))
    imported = product_profile(solver, game, mapping)
    local_external = evaluate_profile(game, imported)
    trainer = VectorCFRTrainer(game, VectorCFRConfig(use_plus=True, linear_weighting=True, use_naive_eval=True))
    _, reference_cost = measured(lambda: trainer.run(reference_iterations))
    reference = evaluate_profile(game, trainer.average_strategy_profile())
    checks = []
    pot = fixture['pot']
    delta = abs(local['root_ev_oop_relative_to_split_pot']-reference['root'][0])/pot
    # Any two approximate equilibria's value difference is bounded by their gaps.
    bound = (local_external['gap']+reference['gap'])/pot + 1e-6
    if delta > bound:
        checks.append('root_ev_exceeds_combined_gap_bound')
    if max(local_external['gap'], reference['gap'])/pot > 0.005:
        checks.append('convergence_exceeds_existing_half_percent_pot_gate')
    if abs(local_external['root'][0]-local['root_ev_oop_relative_to_split_pot']) > 0.000051:
        checks.append('independent_root_evaluation_disagrees')
    if abs(local_external['gap']-local['nash_conv_chips']) > 0.000051:
        checks.append('independent_best_response_disagrees')
    rank_mismatches = []
    for side in (0, 1):
        for hand in game.hands[side]:
            if rank7(tuple(sorted(fixture['board']+list(hand_key(hand))))) != hand.strength:
                rank_mismatches.append(sorted(hand_key(hand)))
    if rank_mismatches:
        checks.append('hand_rank_disagreement')
    core_nodes = {}
    solver._eval(solver.root, solver.w0, solver.w1, collect=core_nodes)
    node_report = []
    max_q_delta = 0.0
    weighted_l1 = total_reach = 0.0
    for (side, key), own in local_external['nodes'].items():
        ref = reference['nodes'][(side, key)]
        core = solver.nodes[mapping[key]]
        tokens = imported[side][key][0]
        # Reference c/f ordering is opposite to core's fold/call ordering.
        permutation = ([core.actions.index('call'), core.actions.index('fold')]
                       if 'f' in tokens else list(range(len(tokens))))
        hand_index = {frozenset(h): i for i, h in enumerate((solver.h0, solver.h1)[side])}
        for i, hand in enumerate(game.hands[side]):
            core_q = core_nodes[core.name]['ev'][hand_index[hand_key(hand)], permutation]
            external_q = own['q'][i]
            if not np.array_equal(np.isfinite(core_q), np.isfinite(external_q)):
                checks.append('action_ev_reach_disagreement')
            finite = np.isfinite(core_q) & np.isfinite(external_q)
            if finite.any():
                max_q_delta = max(max_q_delta, float(np.max(np.abs(core_q[finite]-external_q[finite])))/pot)
            reach = float((own['reach'][i]+ref['reach'][i])/2)
            l1 = float(np.abs(own['strategy'][i]-ref['strategy'][i]).sum())
            weighted_l1 += reach*l1
            total_reach += reach
            ref_q = ref['q'][i]
            available = np.isfinite(ref_q).all()
            q_separation = float(np.max(ref_q)-np.partition(ref_q, -2)[-2]) if available else None
            node_report.append({'node': core.name, 'hand': ''.join(sorted(hand_key(hand))), 'actions': tokens,
                                'local_frequency': own['strategy'][i].tolist(),
                                'reference_frequency': ref['strategy'][i].tolist(),
                                'local_joint_reach': float(own['reach'][i]), 'reference_joint_reach': float(ref['reach'][i]),
                                'rare': reach < 1e-5, 'strategy_l1': l1,
                                'local_action_ev': [float(x) if math.isfinite(x) else None for x in external_q],
                                'reference_action_ev': [float(x) if math.isfinite(x) else None for x in ref_q],
                                'reference_best_second_ev_gap': q_separation,
                                'local_action_regret_vs_reference_opponent':
                                float(np.max(ref_q)-own['strategy'][i] @ ref_q) if available else None,
                                'best_action_agrees': bool(np.argmax(external_q) == np.argmax(ref_q))
                                if available and np.isfinite(external_q).all() and q_separation/pot > 0.005 else None})
    if max_q_delta > 1e-9:
        checks.append('independent_same_profile_action_ev_disagrees')
    return {'id': fixture['id'], 'local_iterations': iterations, 'reference_iterations': reference_iterations,
            'local_root_ev': local['root_ev_oop_relative_to_split_pot'], 'reference_root_ev': reference['root'][0],
            'root_ev_delta_pot': delta, 'combined_gap_bound_pot': bound,
            'local_nashconv': local_external['gap'], 'reference_nashconv': reference['gap'],
            'same_profile_max_action_ev_delta_pot': max_q_delta,
            'reach_weighted_strategy_l1': weighted_l1/total_reach,
            'rank_mismatches': rank_mismatches, 'local_cost': local_cost, 'reference_cost': reference_cost,
            'nodes': node_report, 'failures': sorted(set(checks))}


def tree_sensitivity(fixture, iterations=4000):
    """Reference-only model experiment; never scored as same-tree correctness."""
    output = []
    for raises in (0, 2):  # Upstream counts the opening bet as its first raise.
        game = make_game(fixture, raises)
        trainer = VectorCFRTrainer(game, VectorCFRConfig(use_plus=True, linear_weighting=True, use_naive_eval=True))
        trainer.run(iterations)
        result = evaluate_profile(game, trainer.average_strategy_profile())
        output.append({'upstream_max_raises': raises, 'extra_raises_allowed': 0 if raises == 0 else 1,
                       'root_ev': result['root'][0], 'nashconv': result['gap'],
                       'infosets': len(result['nodes'])})
    return {'id': fixture['id'], 'classification': 'model sensitivity, excluded from correctness gates',
            'reference_iterations': iterations, 'results': output}
