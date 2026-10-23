"""Development-only full-policy storage/lookup experiment, not a shipped cache."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'turn-feasibility-v1'
ENGINE_FILES = ('poker_spot/core.py', 'poker_spot/turn.py')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def sources(paths=ENGINE_FILES):
    return {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths}


def identity(solver, iterations):
    """Retain expansion/order and absolute weights; no unproven equivalences."""
    import numpy as np
    if type(iterations) is not int or not 20 <= iterations <= 2000:
        raise ValueError('Iterations outside existing local bounds')
    return {'version': VERSION, 'engine_sha256_lf': sources(),
            'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
            'board': list(solver.board), 'pot': solver.pot, 'stack': solver.stack,
            'ranges': [[{'hand': list(h), 'weight': float(w)} for h, w in zip(hands, weights, strict=True)]
                       for hands, weights in zip(solver.hands, solver.weights, strict=True)],
            'sizes': [list(side) for side in solver.sizes], 'iterations': iterations,
            'rules': {'raises': 0, 'rake': 0, 'legal_rivers_per_deal': 44},
            'algorithm': 'Alternating CFR+, linear own-reach averaging; half-initial-pot EV'}


def candidate_input(solver, iterations):
    """Provisional study envelope only; admission never establishes convergence."""
    return (iterations == 2000 and max(map(len, solver.hands)) <= 4
            and all(len(side) <= 1 for side in solver.sizes))


def full_record(solver, result):
    import numpy as np
    collected = {}
    solver._walk(solver.root, *solver.weights, collect=collected)
    nodes = {}
    for name, node in solver.nodes.items():
        data = collected[name]
        ev = data['ev'].astype(object)
        ev[~np.isfinite(data['ev'])] = None
        nodes[name] = {'player': node.player, 'street': node.street, 'actions': list(node.actions),
                       'frequency': node.average().tolist(), 'ev': ev.tolist(),
                       'own': data['own'].tolist(), 'opponent': data['opponent'].tolist(),
                       'chance_reach': data['chance_reach']}
    game = identity(solver, solver.iterations)
    return {'identity': game, 'key': digest(game), 'rivers': list(solver.rivers),
            'diagnostics': result['diagnostics'], 'checkpoints': result['checkpoints'],
            'effective_bets': solver.effective_bets, 'nodes': nodes,
            'ev_warning': result['action_ev_interpretation']}


def validate_record(record, solver, iterations):
    """Fail closed before reporting a hit; local measurements include verification."""
    import numpy as np
    game = identity(solver, iterations)
    if record['identity'] != game or record['key'] != digest(game):
        raise ValueError('Mismatched/stale game, solver or accepted configuration')
    if record['rivers'] != list(solver.rivers) or record['effective_bets'] != solver.effective_bets:
        raise ValueError('River/tree mismatch')
    if set(record['nodes']) != set(solver.nodes):
        raise ValueError('Incomplete policy')
    for name, node in solver.nodes.items():
        row = record['nodes'][name]
        if (row['player'], row['street'], row['actions']) != (node.player, node.street, list(node.actions)):
            raise ValueError('Action mapping mismatch')
        policy = np.asarray(row['frequency'], dtype=float)
        if (policy.shape != node.strategy_sum.shape or not np.isfinite(policy).all()
                or (policy < 0).any() or (policy > 1).any()
                or not np.allclose(policy.sum(axis=-1), 1, rtol=0, atol=1e-12)):
            raise ValueError('Invalid full policy')
        ev = np.asarray(row['ev'], dtype=float)
        own, opponent = (np.asarray(row[k], dtype=float) for k in ('own', 'opponent'))
        if (ev.shape != policy.shape or own.shape != node.shape or opponent.shape != node.shape
                or not np.isfinite(own).all() or not np.isfinite(opponent).all()
                or (own < 0).any() or (opponent < 0).any()
                or not np.array_equal(np.isfinite(ev), np.broadcast_to(opponent[..., None] > 0, ev.shape))
                or row['chance_reach'] != (1/44 if node.street else 1)):
            raise ValueError('Invalid action EV/reach support')
    diagnostic = record['diagnostics']
    if (diagnostic['iterations'] != iterations or not all(math.isfinite(v) for v in diagnostic.values())
            or diagnostic['raw_nash_conv_chips'] < -1e-8
            or abs(diagnostic['zero_sum_residual']) > 1e-8
            or diagnostic['nash_conv_pct_pot'] > 0.5):
        raise ValueError('Not verified: unchanged convergence/finite-value gate')
    return record


def pack(record):
    raw = encoded(record)
    return gzip.compress(raw, mtime=0)


def unpack(blob, sha256, solver, iterations):
    if hashlib.sha256(blob).hexdigest() != sha256:
        raise ValueError('Corrupt compressed artifact')
    # This is a trusted bounded local experiment, not a hostile upload reader.
    return validate_record(json.loads(gzip.decompress(blob)), solver, iterations)


def view(record, solver, side, hand, river=None):
    """Same output-only filters as TurnSolver.solve; no game substitution."""
    import numpy as np
    from poker_spot.core import cards, combo_key
    if side not in (0, 1) or type(side) is not int:
        raise ValueError('Unknown player')
    index = solver.hands[side].index(combo_key(*cards(hand, 2)))
    if river is not None and river not in solver.rivers:
        raise ValueError('Unsupported river view')
    valid = solver.valid if side == 0 else solver.valid.T
    initial = float(valid[index] @ solver.weights[1-side])
    if initial <= 0:
        raise ValueError('No compatible opponent')
    rows = {}
    for name, data in record['nodes'].items():
        if data['player'] != side:
            continue
        for context in (range(48) if data['street'] else (None,)):
            if context is not None:
                card = solver.rivers[context]
                if card in solver.hands[side][index] or (river is not None and river != card):
                    continue
            location = (index,) if context is None else (context, index)
            key = name if context is None else name+'@'+solver.rivers[context]
            policy = np.asarray(data['frequency'])[location].tolist()
            ev = np.asarray(data['ev'], dtype=object)[location].tolist()
            own, opp = (float(np.asarray(data[k])[location]) for k in ('own', 'opponent'))
            rows[key] = {'frequency': dict(zip(data['actions'], policy, strict=True)),
                         'action_ev_relative_to_half_turn_pot': dict(zip(data['actions'], ev, strict=True)),
                         'reach_probability_given_hand': own/solver.weights[side][index]*opp/initial*data['chance_reach']}
    return {'combo': list(solver.hands[side][index]), 'node_strategy': rows}


def games():
    fixtures = json.loads((ROOT/'benchmarks/turn-independent-fixtures.json').read_text())
    selected = ('weighted_4x4_collision', 'four_flush_4x4', 'trips_3x4', 'draw_4x4_two_sizes')
    questions = ('Overpairs versus weighted draws on a dry turn',
                 'Flush blockers on a four-flush turn',
                 'Trips versus draws with full-house runouts',
                 'Double-barrel choices with two bet sizes')
    rows = []
    for name, question in zip(selected, questions, strict=True):
        original = next(f for f in fixtures if f['id'] == name)['config']
        config = {k: copy.deepcopy(original[k]) for k in ('pot', 'stack', 'turn_bet_sizes', 'river_bet_sizes')}
        config['board'] = ','.join(original['board'])
        for player in ('oop', 'ip'):
            config[player+'_range'] = ','.join(f'{h["hand"]}:{h["weight"]}' for h in original[player])
        rows.append({'id': name, 'question': question, 'config': config, 'iterations': 2000})
    return rows
