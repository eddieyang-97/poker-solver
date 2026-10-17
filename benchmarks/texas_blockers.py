"""Separate failing reference diagnostic; never part of passing fixture acceptance."""
from __future__ import annotations

import copy
import json
import math

from benchmarks.harness import compare_fixture, evaluate_profile, hand_key, make_game
from benchmarks.texas import (
    DATA, EXE_SHA256, LOOKUP_SHA256, SOURCE_COMMIT, capture_commands,
    commands, import_policy, load_fixture,
)

FIXTURE = DATA / 'blocker-fixture.json'
CHIP_GATE = 0.5  # Existing 0.5%-of-£100 convergence gate, unchanged.


def load_blocker_fixture():
    expected = copy.deepcopy(load_fixture())
    expected['id'] = 'texas_weighted_blocker_diagnostic'
    expected['description'] = 'Weighted cross-range KK blockers; separate reference convergence audit'
    expected['ip'] += [dict(hand, weight=0.5) for hand in expected['oop']]
    fixture = json.loads(FIXTURE.read_text())
    if fixture != expected:
        raise ValueError('Diagnostic differs from the reviewed weighted-blocker game')
    return fixture


def diagnostic_commands(iterations):
    if iterations not in (4000, 40000):
        raise ValueError('Only the two reviewed convergence budgets are supported')
    return (commands(load_fixture()).replace('AA,QJo:0.5', 'AA,KK:0.5,QJo:0.5')
            .replace('set_max_iteration 4000', f'set_max_iteration {iterations}')
            .replace('set_print_interval 100\n', f'set_print_interval {iterations//40}\n'))


def capture(binary):
    fixture = load_blocker_fixture()
    return {'fixture': fixture, 'runs': [dict(capture_commands(binary, diagnostic_commands(n)),
                                            maximum_iterations=n) for n in (4000, 40000)]}


def chance_diagnostics(fixture):
    compatible = 0
    mass = 0.0
    categories = {'AA': 0.0, 'KK': 0.0, 'QJ': 0.0}
    for oop in fixture['oop']:
        first = {oop['hand'][:2], oop['hand'][2:]}
        for ip in fixture['ip']:
            if first & {ip['hand'][:2], ip['hand'][2:]}:
                continue
            weight = oop['weight']*ip['weight']
            mass += weight
            compatible += 1
            categories[ip['hand'][0]+ip['hand'][2]] += weight
    return {'compatible_pairs': compatible, 'unnormalized_joint_weight': mass,
            'ip_category_probability_after_card_removal': {k: v/mass for k, v in categories.items()}}


def analytical_profile(game, template):
    """Derived rank equilibrium: KK tie hands also bet, shifting QJ to 23/48.

    OOP call-minus-fold indifference is 6*(-100) + .5*50 + 6*x*200 = 0.
    The independent best-response evaluator checks the complete policy below.
    """
    profile = copy.deepcopy(template)
    for side in (0, 1):
        for key, (tokens, matrix) in profile[side].items():
            for i, hand in enumerate(game.hands[side]):
                ranks = {c[0] for c in hand_key(hand)}
                if side == 0:
                    frequencies = {'c': 0.5, 'f': 0.5} if 'f' in tokens else {'c': 1, 'b10000': 0}
                elif 'f' in tokens:
                    call = 0 if ranks == {'Q', 'J'} else 1
                    frequencies = {'c': call, 'f': 1-call}
                else:
                    bet = 23/48 if ranks == {'Q', 'J'} else 1
                    frequencies = {'c': 1-bet, 'b10000': bet}
                matrix[i] = [frequencies[token] for token in tokens]
    return profile


def evaluate_runs(evidence):
    fixture = load_blocker_fixture()
    if evidence['fixture'] != fixture or len(evidence['runs']) != 2:
        raise ValueError('Wrong diagnostic fixture or missing run')
    game = make_game(fixture)
    output = []
    analytical = None
    for run, budget in zip(evidence['runs'], (4000, 40000), strict=True):
        if (run['maximum_iterations'] != budget or run['input_commands'] != diagnostic_commands(budget)
                or run['source_commit'] != SOURCE_COMMIT or run['binary_sha256'] != EXE_SHA256
                or run['lookup_sha256'] != LOOKUP_SHA256 or run['exit_code'] != 0):
            raise ValueError('Diagnostic provenance/configuration differs')
        profile = import_policy(game, run['strategy'])
        evaluated = evaluate_profile(game, profile)
        if analytical is None:
            analytical = evaluate_profile(game, analytical_profile(game, profile))
        last = run['checkpoints'][-1]
        reported = last['exploitibility']
        if not math.isfinite(reported):
            raise ValueError('Nonfinite upstream convergence observation')
        output.append({'maximum_iterations': budget, 'oop_root_ev': evaluated['root'][0],
                       'independently_evaluated_nashconv': evaluated['gap'],
                       'convergence_gate_chips': CHIP_GATE,
                       'status': 'FAIL' if evaluated['gap'] > CHIP_GATE else 'PASS',
                       'last_logged_iteration_index': last['iteration'],
                       'last_logged_exploitability_percent': reported,
                       'last_logged_normalized_nashconv': 2*fixture['pot']*reported/100,
                       'log_and_dump_are_different_checkpoints': True})
    return {'fixture_id': fixture['id'], 'chance': chance_diagnostics(fixture),
            'analytical': {'oop_root_ev': analytical['root'][0], 'nashconv': analytical['gap'],
                           'qj_bet': 23/48, 'kk_call': 0.5, 'ip_kk_bet': 1.0},
            'runs': output,
            'failed_runs': [r['maximum_iterations'] for r in output if r['status'] == 'FAIL']}


def analyze(evidence):
    report = evaluate_runs(evidence)
    independent = compare_fixture(load_blocker_fixture())
    report['product_and_noambrown'] = independent
    report['classification'] = 'Reference convergence discrepancy; excluded from passing corpus'
    report['independent_failures'] = independent['failures']
    return report
