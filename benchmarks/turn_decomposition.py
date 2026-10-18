"""Development-only river decomposition with separately trained river games."""
from __future__ import annotations

import math

import numpy as np

from benchmarks.harness import (
    SCALE, action_tokens, evaluate_profile, hand_key, import_reference, make_game,
    reference_config, run_reference, state_mapping, validate_fixture,
)
from poker_spot.turn import TurnSolver


def ranges_text(entries):
    return ','.join(f'{entry["hand"]}:{entry["weight"]}' for entry in entries)


def pair_mass(left, right):
    """Explicit compatible joint mass; no product validity/chance matrices."""
    return math.fsum(a['weight']*b['weight'] for a in left for b in right
                     if not {a['hand'][:2], a['hand'][2:]} & {b['hand'][:2], b['hand'][2:]})


def partition(fixture):
    if fixture['turn_bet_sizes'] != []:
        raise ValueError('River decomposition requires disabled turn betting')
    # Validate original explicit hands and trees using the river adapter below;
    # validate turn bounds before attempting any independent calculations.
    solver = TurnSolver(','.join(fixture['board']), ranges_text(fixture['oop']), ranges_text(fixture['ip']),
                        fixture['pot'], fixture['stack'], [], fixture['bet_sizes'])
    if [set(map(frozenset, side)) for side in solver.hands] != [
            {frozenset((x['hand'][:2], x['hand'][2:])) for x in fixture[p]} for p in ('oop', 'ip')]:
        raise ValueError('Original explicit hands differ after expansion/board removal')
    initial = pair_mass(fixture['oop'], fixture['ip'])
    if initial <= 0:
        raise ValueError('No compatible initial pairs')
    output = []
    # Build our own deck; do not read solver.rivers/masks/river_valid.
    for card in (rank+suit for rank in '23456789TJQKA' for suit in 'cdhs'):
        if card in fixture['board']:
            continue
        river = {k: v for k, v in fixture.items() if k != 'turn_bet_sizes'}
        river['board'] = fixture['board']+[card]
        for side in ('oop', 'ip'):
            river[side] = [entry for entry in fixture[side]
                          if card not in (entry['hand'][:2], entry['hand'][2:])]
        mass = pair_mass(river['oop'], river['ip'])
        if mass:
            validate_fixture(river)
        output.append({'card': card, 'mass': mass, 'probability': mass/(44*initial), 'fixture': river})
    return solver, initial, output


def turn_river_profile(solver, card, fixture, game):
    """Map independently generated river histories, hands and actions explicitly."""
    state_mapping(game, fixture)  # Reject extra raises/actions/implicit sizing.
    prefix = 'turn/check/check/river'
    context = solver.rivers.index(card)
    profile = {0: {}, 1: {}}
    seen = set()
    amounts = {round(min(fixture['stack'], fixture['pot']*size)*SCALE):
               float(min(fixture['stack'], fixture['pot']*size)) for size in fixture['bet_sizes']}

    def visit(state):
        if game.is_terminal(state):
            return
        name = prefix
        for token in state.history:
            if token == 'c':
                name += '/check'
            elif token.startswith('b') and int(token[1:]) in amounts:
                amount = amounts[int(token[1:])]
                name += '/bet_'+(str(int(amount)) if amount.is_integer() else repr(amount))
            else:
                raise ValueError('Unsupported independent public history')
        node = solver.nodes[name]
        if node.player != state.player or node.street != 1:
            raise ValueError('Turn/river actor or street mismatch')
        actions = game.legal_actions(state)
        facing = max(state.contrib) > state.contrib[state.player]
        labels = []
        for action in actions:
            if action.label == 'c':
                labels.append('call' if facing else 'check')
            elif action.label == 'f':
                labels.append('fold')
            else:
                amount = amounts[action.amount]
                labels.append('bet_'+(str(int(amount)) if amount.is_integer() else repr(amount)))
        if set(labels) != set(node.actions):
            raise ValueError('Independent and product action trees differ')
        index = {frozenset(hand): k for k, hand in enumerate(solver.hands[state.player])}
        average = node.average()[context]
        profile[state.player][game.infoset_key(state, state.player)] = (action_tokens(actions), [
            [float(average[index[hand_key(hand)], node.actions.index(label)]) for label in labels]
            for hand in game.hands[state.player]])
        seen.add(name)
        for action in actions:
            visit(game.next_state(state, action))

    visit(game.initial_state())
    if seen != {name for name in solver.nodes if name.startswith(prefix)}:
        raise ValueError('Unmapped product river histories')
    return profile


def compare_decomposition(fixture, iterations=2000, reference_iterations=4000, progress=None):
    solver, mass, runouts = partition(fixture)
    result = solver.solve(iterations)
    weighted = {'product_ev': 0.0, 'product_gap': 0.0, 'reference_ev': 0.0, 'reference_gap': 0.0}
    cases, failures = [], []
    allowance = 1e-8
    convergence = 0.005*fixture['pot']
    for number, runout in enumerate(runouts, 1):
        row = {key: runout[key] for key in ('card', 'mass', 'probability')}
        if runout['mass']:
            river = runout['fixture']
            game = make_game(river)
            product = evaluate_profile(game, turn_river_profile(solver, runout['card'], river, game))
            exported = run_reference(reference_config(river), reference_iterations)
            reference = evaluate_profile(game, import_reference(game, exported))
            row.update(product_ev=product['root'][0], product_gap=product['gap'],
                       reference_ev=reference['root'][0], reference_gap=reference['gap'],
                       reference_export=exported)
            for name in weighted:
                weighted[name] += row['probability']*row[name]
            if abs(product['root'][0]-reference['root'][0]) > product['gap']+reference['gap']+allowance:
                failures.append(f'{runout["card"]}: root difference exceeds combined gaps')
            if max(product['gap'], reference['gap']) > convergence:
                failures.append(f'{runout["card"]}: subgame convergence exceeds 0.5% initial pot')
            if abs(reference['gap']-2*exported['checkpoints'][-1]['raw_exploitability']/SCALE) > allowance:
                failures.append(f'{runout["card"]}: reference normalization mismatch')
        else:
            row['skipped'] = 'No compatible positive-weight deal; probability zero'
        cases.append(row)
        if progress:
            progress(number, row)
    probability = math.fsum(row['probability'] for row in cases)
    ev_delta = abs(result['diagnostics']['oop_ev']-weighted['product_ev'])
    gap_delta = abs(result['diagnostics']['nash_conv_chips']-weighted['product_gap'])
    independent_delta = abs(result['diagnostics']['oop_ev']-weighted['reference_ev'])
    bound = result['diagnostics']['nash_conv_chips']+weighted['reference_gap']+allowance
    if abs(probability-1) > 1e-12:
        failures.append('Runout probabilities do not sum to one')
    if ev_delta > allowance or gap_delta > allowance:
        failures.append('Turn chance/EV/BR differs from independent river-tree decomposition')
    if independent_delta > bound:
        failures.append('Independent aggregate EV differs beyond combined gap bound')
    if max(result['diagnostics']['nash_conv_chips'], weighted['reference_gap']) > convergence:
        failures.append('Aggregate convergence exceeds 0.5% initial pot')
    if not np.isfinite(list(weighted.values())).all():
        failures.append('Nonfinite aggregate output')
    return {'id': fixture['id'], 'fixture': fixture, 'iterations': iterations,
            'reference_iterations': reference_iterations, 'initial_joint_mass': mass,
            'probability_sum': probability, 'turn': result['diagnostics'], 'decomposition': weighted,
            'same_policy_ev_delta': ev_delta, 'same_policy_gap_delta': gap_delta,
            'independent_ev_delta': independent_delta, 'combined_gap_bound': bound,
            'gates': {'numeric_chips': allowance, 'convergence_chips': convergence},
            'runouts': cases, 'failures': failures}
