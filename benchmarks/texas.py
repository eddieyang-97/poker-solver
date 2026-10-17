"""Development-only adapter for one explicitly supported TexasSolver pilot.

The external executable is never distributed or loaded by the hosted service.
Its JSON omits terminal payoffs, weights and EVs: these are independently checked
under the declared fixture, not presented as raw TexasSolver EV output.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from benchmarks.harness import (
    ROOT, SCALE, action_tokens, compare_fixture, evaluate_profile, hand_key,
    make_game, parse_hand, state_mapping, validate_fixture,
)

DATA = ROOT / 'texassolver'
SOURCE_COMMIT = '95f039c116fa7bcae7fb6c01aca56adb0f24c680'
EXE_SHA256 = '8b74cd6f687387a9ea6c567591642cfe0bfca88360a1748ff7c7db769d0c5c1a'
ZIP_SHA256 = '0a9122fa0cd9384e6c1cbe0492e8a3b8ac7809890c649e1a53f77a59d6d50a7c'
LOOKUP_SHA256 = '4b68eee7bd91224157b125aad7429bf25cedd96370bcd228f316058d197afba2'
RANGES = {'oop': 'KK', 'ip': 'AA,QJo:0.5'}


def load_fixture():
    fixture = json.loads((DATA / 'fixture.json').read_text())
    validate_fixture(fixture)
    if (fixture['board'] != ['2c', '3d', '4h', '8s', '9c'] or fixture['pot'] != 100
            or fixture['stack'] != 100 or fixture['bet_sizes'] != [1]):
        raise ValueError('Only the reviewed pot-sized rank-class pilot is supported')
    # Independently enumerate this pilot's class inputs; do not reuse core range expansion.
    suits = 'cdhs'
    expected = {
        'oop': {parse_hand('K'+a+'K'+b): 1 for a, b in itertools.combinations(suits, 2)},
        'ip': {parse_hand('A'+a+'A'+b): 1 for a, b in itertools.combinations(suits, 2)}
              | {parse_hand('Q'+a+'J'+b): 0.5 for a in suits for b in suits if a != b},
    }
    for side in ('oop', 'ip'):
        if {parse_hand(x['hand']): x['weight'] for x in fixture[side]} != expected[side]:
            raise ValueError('Declared class input differs from explicit fixture weights/combos')
    return fixture


def commands(fixture):
    if fixture != load_fixture():
        raise ValueError('Unsupported TexasSolver fixture; never substitute ranges silently')
    return '\n'.join([
        'set_pot 100', 'set_effective_stack 100', 'set_board '+','.join(fixture['board']),
        'set_range_oop '+RANGES['oop'], 'set_range_ip '+RANGES['ip'],
        'set_bet_sizes oop,river,bet,100', 'set_bet_sizes ip,river,bet,100',
        'set_bet_sizes oop,river,raise', 'set_bet_sizes ip,river,raise',
        'set_allin_threshold 100', 'build_tree', 'set_thread_num 1',
        'set_accuracy 0.001', 'set_max_iteration 4000', 'set_print_interval 100',
        'set_use_isomorphism 0', 'start_solve', 'set_dump_rounds 1',
        'dump_result strategy.json', ''])


def run_external(binary, fixture):
    captured = capture_commands(binary, commands(fixture))
    return dict(captured, ranges=RANGES, fixture=fixture)


def capture_commands(binary, command_text):
    """Local laboratory capture; accepted pilot validation stays in run_external/analyze.

    Callers generate fixed reviewed commands, never accept commands from hosted tools.
    """
    binary = Path(binary).resolve()
    if hashlib.sha256(binary.read_bytes()).hexdigest() != EXE_SHA256:
        raise ValueError('Executable differs from the inspected upstream Windows v0.2.0 release')
    resources = binary.parent / 'resources'
    comparer = resources / 'compairer' / 'card5_dic_sorted.txt'
    # Capture lookup data provenance too: the executable alone does not define evaluation.
    comparer_hash = hashlib.sha256(comparer.read_bytes()).hexdigest()
    if comparer_hash != LOOKUP_SHA256:
        raise ValueError('Hand-evaluation lookup differs from inspected release')
    artifact_dir = ROOT.parent / '.artifacts'
    artifact_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='texas-', dir=artifact_dir) as temp:
        work = Path(temp)
        (work / 'input.txt').write_text(command_text, encoding='ascii')
        result = subprocess.run([str(binary), '-r', str(resources), '-i', str(work / 'input.txt')],
                                cwd=work, capture_output=True, timeout=60, check=True)
        text = (result.stdout+result.stderr).decode('utf-8', errors='replace')
        marker = text.find('<<<START SOLVING>>>')
        if marker == -1:
            raise ValueError('Executable returned no solve-start evidence')
        log = text[marker:]
        records = [json.loads(line) for line in (work / 'tmp_log.txt').read_text().splitlines() if line.strip()]
        if not records:
            raise ValueError('Executable returned no convergence checkpoints')
        dump = json.loads((work / 'strategy.json').read_text())
    return {'provenance': 'Actual standalone upstream Windows v0.2.0 execution',
            'source_tag': 'v0.2.0', 'source_commit': SOURCE_COMMIT,
            'binary_sha256': EXE_SHA256, 'download_zip_sha256': ZIP_SHA256,
            'lookup_sha256': comparer_hash, 'input_commands': command_text,
            'exit_code': result.returncode,
            'log_after_start': log, 'checkpoints': records, 'strategy': dump}


def import_policy(game, dump):
    """Reject mismatched trees/combos; map Texas IP=0/OOP=1 explicitly."""
    profile = {0: {}, 1: {}}

    def walk(state, node):
        if not isinstance(node, dict) or node.get('node_type') != 'action_node':
            raise ValueError('Missing or non-action river node in dump')
        side = state.player
        if node['player'] != 1-side:
            raise ValueError('TexasSolver player mapping differs')
        actions = game.legal_actions(state)
        expected = action_tokens(actions)
        facing = max(state.contrib) > state.contrib[side]
        tokens = []
        for label in node['actions']:
            if label in ('CHECK', 'CALL'):
                if label != ('CALL' if facing else 'CHECK'):
                    raise ValueError('Check/call context differs')
                tokens.append('c')
            elif label == 'FOLD':
                tokens.append('f')
            elif re.fullmatch(r'BET \d+(?:\.\d+)?', label):
                amount = float(label.split()[1])*SCALE
                if not math.isfinite(amount) or abs(amount-round(amount)) > 1e-7:
                    raise ValueError('Nonrepresentable exported bet')
                tokens.append('b'+str(round(amount)))
            else:
                raise ValueError('Unsupported exported action, including raises/all-ins')
        if len(set(tokens)) != len(tokens) or set(tokens) != set(expected):
            raise ValueError('TexasSolver tree/bet amounts differ')
        strategy = node['strategy']
        if strategy['actions'] != node['actions']:
            raise ValueError('Exported strategy action order differs')
        rows = {}
        for text, row in strategy['strategy'].items():
            key = frozenset((text[:2], text[2:]))
            if len(text) != 4 or key in rows:
                raise ValueError('Invalid/duplicate exported combo')
            if (len(row) != len(tokens) or any(not math.isfinite(v) or v < 0 for v in row)
                    or abs(sum(row)-1) > 1e-6):
                raise ValueError('Invalid exported frequency row')
            rows[key] = [row[tokens.index(token)] for token in expected]
        if set(rows) != {hand_key(h) for h in game.hands[side]}:
            raise ValueError('Exported combo set differs from declared fixture')
        profile[side][game.infoset_key(state, side)] = (expected, [rows[hand_key(h)] for h in game.hands[side]])
        children = node.get('childrens') or {}
        expected_children = set()
        for action, token in zip(actions, expected):
            next_state = game.next_state(state, action)
            label = node['actions'][tokens.index(token)]
            # Texas omits terminals from JSON. Require every decision child and no others.
            if not game.is_terminal(next_state):
                expected_children.add(label)
                if label not in children:
                    raise ValueError('Export truncated before a river decision')
                walk(next_state, children[label])
        if set(children) != expected_children:
            raise ValueError('Unexpected exported descendants or extra streets')
    walk(game.initial_state(), dump)
    return profile


def analyze(evidence):
    fixture = load_fixture()
    if (evidence['fixture'] != fixture or evidence['ranges'] != RANGES
            or evidence['input_commands'] != commands(fixture)
            or evidence['source_commit'] != SOURCE_COMMIT or evidence['binary_sha256'] != EXE_SHA256
            or evidence['lookup_sha256'] != LOOKUP_SHA256 or evidence['exit_code'] != 0):
        raise ValueError('Recorded provenance/configuration differs from reviewed pilot')
    game = make_game(fixture)
    policy = import_policy(game, evidence['strategy'])
    evaluated = evaluate_profile(game, policy)
    comparison = compare_fixture(fixture)
    reported_percent = evidence['checkpoints'][-1]['exploitibility']
    if not math.isfinite(reported_percent) or reported_percent < 0:
        raise ValueError('Invalid reported convergence metric')
    # Source: (BR0+BR1)/2/P*100. Source payoffs are already zero-sum centered.
    normalized_gap = 2*fixture['pot']*reported_percent/100
    failures = list(comparison['failures'])
    if abs(evaluated['root'][0]+25) > evaluated['gap']+0.000051:
        failures.append('texas_policy_value_disagrees_with_analytical')
    if evaluated['gap']/fixture['pot'] > 0.005:
        failures.append('texas_exported_policy_convergence_failed')
    # Existing rounded chip-output tolerance covers float accumulation/dump rounding.
    if abs(normalized_gap-evaluated['gap']) > 0.000051:
        failures.append('texas_log_vs_exported_policy_gap_disagrees')
    pair_deltas = {}
    for label in ('local', 'reference'):
        pair_deltas[label] = abs(evaluated['root'][0]-comparison[label+'_root_ev'])/fixture['pot']
        bound = (evaluated['gap']+comparison[label+'_nashconv'])/fixture['pot']+1e-6
        if pair_deltas[label] > bound:
            failures.append(f'texas_vs_{label}_root_exceeds_combined_gaps')
    mapped = state_mapping(game, fixture)
    nodes = []
    for (side, key), node in evaluated['nodes'].items():
        tokens = policy[side][key][0]
        for i, hand in enumerate(game.hands[side]):
            nodes.append({'node': mapped[key], 'hand': sorted(hand_key(hand)), 'actions': tokens,
                          'frequency': node['strategy'][i].tolist(),
                          'independently_evaluated_action_ev':
                          [float(v) if math.isfinite(v) else None for v in node['q'][i]],
                          'joint_reach': float(node['reach'][i])})
    selected = {}
    for label, decision, hand, action in (
        ('qj_bet', 'ip_after_oop_check', {'Qh', 'Jd'}, 'b10000'),
        ('kk_call', 'oop_facing_ip_bet_1', {'Kh', 'Kd'}, 'c'),
        ('kk_check', 'oop_first', {'Kh', 'Kd'}, 'c'),
    ):
        row = next(n for n in nodes if n['node'] == decision and set(n['hand']) == hand)
        selected[label] = row['frequency'][row['actions'].index(action)]
    return {'fixture_id': fixture['id'], 'comparison': comparison,
            'texas_exported_policy_oop_ev': evaluated['root'][0],
            'texas_exported_policy_nashconv': evaluated['gap'],
            'texas_log_exploitability_percent': reported_percent,
            'texas_log_normalized_nashconv': normalized_gap,
            'texas_root_delta_pot': pair_deltas,
            'ev_provenance': 'Independent evaluation of actual Texas strategy; no raw EV field in its JSON',
            'terminal_payoffs': 'Reconstructed from declared fixture; Texas JSON omits terminals',
            'texas_selected_frequency': selected,
            'texas_nodes': nodes, 'failures': failures}
