"""Compare incremental response allocation against exhaustive small-game BRs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
from statistics import median
from types import SimpleNamespace
import time

import numpy as np

from bounded_response import ResponseSearch
from gap_response import FrontierResponse
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from recall_ablation import HouseFixture
from run_fixed_strategy import peak_memory

BASE = Path(__file__).resolve().parent
SOURCES = ('run_gap_response.py', 'gap_response.py', 'bounded_response.py', 'one_face.py',
           'game.py', 'guidance.py', 'recall_ablation.py', 'run_fixed_strategy.py')
METHODS = ('legacy', 'reach', 'gap')
BUDGETS = (2, 4, 8, 16)
EXHAUSTIVE_CAP = 4096
TIMING_REPEATS = 20
WIDTH_TARGET = 0.02
TOL = 1e-10


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized_hash(path):
    return sha(path.read_bytes().replace(b'\r\n', b'\n'))


class TableTarget:
    """Immutable behavioral rows indexed by complete public history."""

    def __init__(self, game, table):
        self.game = game
        self.target = self
        self.rows, self.sparse = {}, {}

        def visit(history):
            actions = game.actions(history)
            rows = np.asarray(table(history))
            if (rows.shape != (len(game.hands), len(actions)) or not np.isfinite(rows).all()
                    or (rows < 0).any() or not np.allclose(rows.sum(axis=1), 1, atol=1e-12, rtol=0)):
                raise ValueError('Invalid fixture target probabilities')
            rows.flags.writeable = False
            self.rows[history] = rows
            self.sparse[history] = {a: rows[:, i] for i, a in enumerate(actions) if rows[:, i].any()}
            for action in actions:
                if action != -1:
                    visit(history + (action,))

        visit(())

    def actions(self, player, history):
        if player != len(history) % 2:
            raise ValueError('Wrong target seat')
        return self.sparse[history]

    def policy(self, player, hand, history):
        return self.rows[history][hand]

    def fingerprint(self):
        return sha(b''.join(self.rows[h].astype('<f8').tobytes() for h in sorted(self.rows)))


def fixtures():
    receipt = json.loads((BASE/'outputs/recall-ablation.json').read_text())
    for entry in receipt['fixtures']:
        q = entry['zhai_quantity']
        game = HouseFixture(q)
        guide = SimpleNamespace(columns={a: a for a in range(len(game.bids))},
                                counts=np.array(game.counts),
                                quantities=np.array([b.quantity for b in game.bids]))
        for recall, seed in ((None, None), (1, 490021)):
            record, = [r for r in entry['runs'] if (r['recall'], r['seed']) == (recall, seed)]
            artifact = record['checkpoints'][-1]['policy']
            data = (BASE/'outputs'/artifact['file']).read_bytes()
            if sha(data) != artifact['sha256']:
                raise ValueError('Archived fixture target changed')
            archived = json.loads(data)
            target = TableTarget(game, lambda h: np.array(archived[','.join(map(str, h))]))
            yield {'game': 'restricted-house', 'zhai_quantity': q, 'recall': recall, 'seed': seed,
                   'artifact': artifact, 'archived_evaluation': record['checkpoints'][-1]['full_history_evaluation']}, guide, target
    game = OneFace(10)
    for seed in (490081, 490082):
        rng = np.random.default_rng(seed)

        def table(history):
            rows = rng.integers(0, 8, (len(game.hands), len(game.actions(history))))
            rows[rows.sum(axis=1) == 0, 0] = 1
            return rows / rows.sum(axis=1, keepdims=True)

        yield {'game': 'one-face', 'maximum': game.maximum, 'seed': seed}, ProbabilityGuide(game), TableTarget(game, table)


def build_search(method, guide, target, seat, cap):
    game = target.game
    if method == 'legacy':
        # Depth cannot bind on these finite increasing-bid trees.
        return ResponseSearch(game, guide, target, seat, depth=128, max_nodes=cap)
    return FrontierResponse(game, guide, target, seat, cap, allocation=method)


def verify(search, bound, target, exact):
    seat = search.seat
    br = exact[f'br{seat}']

    def profile(player, hand, history):
        return (search.policy if player == seat else target.policy)(player, hand, history)

    # Separate public-tree traversal with an explicit utility matrix per terminal.
    value = (1 if seat == 0 else -1) * evaluate(target.game, profile)['ev_p0']
    if abs(value - bound['lower']) > TOL or not bound['lower']-TOL <= br <= bound['upper']+TOL:
        raise ArithmeticError('Lower policy realization or independent BR containment failed')
    return {**bound, 'independent_lower': value, 'realization_error': abs(value-bound['lower']),
            'lower_error_to_br': br-bound['lower'], 'upper_error_to_br': bound['upper']-br}


def measure(guide, target, seat, expected):
    timing = {m: {'node_cap': expected[m]['max_nodes'], 'width': expected[m]['width'],
                  'cpu_seconds': 0., 'wall_seconds': 0.} for m in METHODS}
    # Interleave fresh runs in rotating order. Independent replay stays outside
    # the timer. Aggregate batches avoid comparing individual timer ticks.
    for repeat in range(TIMING_REPEATS):
        offset = repeat % len(METHODS)
        for method in METHODS[offset:] + METHODS[:offset]:
            w, c = time.perf_counter(), time.process_time()
            result = build_search(method, guide, target, seat, timing[method]['node_cap']).solve()
            timing[method]['cpu_seconds'] += time.process_time()-c
            timing[method]['wall_seconds'] += time.perf_counter()-w
            if any(abs(result[k]-expected[method][k]) > TOL for k in ('lower', 'upper')):
                raise ArithmeticError('Fresh timed search changed deterministic checkpoint')
    return timing


def width_checkpoint(method, guide, target, seat, exact, checkpoints):
    # Width is monotone with a cumulative cap. Find the first integer cap
    # reaching the operating point, outside the timed part of the comparison.
    right = next(c['max_nodes'] for c in checkpoints if c['width'] <= WIDTH_TARGET)
    left = max((c['max_nodes']+1 for c in checkpoints if c['width'] > WIDTH_TARGET), default=1)
    while left < right:
        mid = (left + right) // 2
        probe = build_search(method, guide, target, seat, mid).solve()
        if probe['width'] <= WIDTH_TARGET:
            right = mid
        else:
            left = mid + 1
    search = build_search(method, guide, target, seat, right)
    return verify(search, search.solve(), target, exact)


def study_case(guide, target, seat, exact):
    results = {}
    for method in METHODS:
        rows = []
        incremental = build_search(method, guide, target, seat, EXHAUSTIVE_CAP)
        for cap in (*BUDGETS, EXHAUSTIVE_CAP):
            if method == 'legacy':
                search = build_search(method, guide, target, seat, cap)
                bound = search.solve()
            else:
                search = incremental
                bound = search.advance(cap)
            rows.append(verify(search, bound, target, exact))
        if rows[-1]['width'] > TOL:
            raise ArithmeticError('Exhaustive fixture failed to recover exact BR')
        results[method] = rows

    timing = measure(guide, target, seat, {m: results[m][-2] for m in METHODS})
    width_bounds = {m: width_checkpoint(m, guide, target, seat, exact, results[m]) for m in METHODS}
    width_timing = measure(guide, target, seat, width_bounds)
    return {'seat': seat, 'checkpoints': results, 'timing': timing,
            'width_target_checkpoints': width_bounds, 'width_target_timing': width_timing}


def admission(cases):
    """Predeclared promotion gate based on partial fixture curves and cost."""
    pairs = [s for row in cases for s in row['seats']]
    ratios = {}
    cpu = {m: sum(s['timing'][m]['cpu_seconds'] for s in pairs) for m in METHODS}
    for control in ('legacy', 'reach'):
        widths = [[sum(c['width'] for c in s['checkpoints'][m][:-1]) for m in ('gap', control)]
                  for s in pairs]
        eligible = [a/b for a, b in widths if b > TOL]
        ratios[control] = {'median_summed_width_ratio': median(eligible),
                           'wins': sum(a < b-TOL for a, b in widths), 'cases': len(widths),
                           'worst_absolute_width_increase': max(
                               g['width']-r['width'] for s in pairs
                               for g, r in zip(s['checkpoints']['gap'][:-1], s['checkpoints'][control][:-1])),
                           'aggregate_cpu_ratio_at_cap16': cpu['gap']/cpu[control]}
    passed = all(r['median_summed_width_ratio'] <= 0.80
                 and r['worst_absolute_width_increase'] <= 0.05
                 and r['aggregate_cpu_ratio_at_cap16'] <= 1.25 for r in ratios.values())
    return {'passed': passed, 'controls': ratios, 'aggregate_cpu_seconds': cpu,
            'thresholds': {'median_summed_width_ratio': 0.80, 'worst_absolute_width_increase': 0.05,
                           'aggregate_cpu_ratio_at_cap16': 1.25}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/gap-response.json')
    args = parser.parse_args()
    start, cpu = time.perf_counter(), time.process_time()
    report = {'status': 'running', 'platform': platform.platform(), 'processor': platform.processor(),
              'python': platform.python_version(), 'numpy': np.__version__,
              'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'ablation_receipt_sha256_lf': normalized_hash(BASE/'outputs/recall-ablation.json'),
              'node_caps': [*BUDGETS, EXHAUSTIVE_CAP], 'timing_repeats_per_seat': TIMING_REPEATS,
              'supplemental_width_target': WIDTH_TARGET,
              'cases': []}

    def save():
        report['wall_seconds'], report['cpu_seconds'] = time.perf_counter()-start, time.process_time()-cpu
        report['peak_process_memory'] = peak_memory()
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')

    try:
        for label, guide, target in fixtures():
            exact = evaluate(target.game, target.policy)
            if any(abs(exact[k]-v) > TOL for k, v in label.get('archived_evaluation', {}).items()):
                raise ArithmeticError('Archived fixture evaluation changed')
            row = {**label, 'target_probabilities_sha256': target.fingerprint(),
                   'independent': exact, 'seats': []}
            report['cases'].append(row)
            for seat in (0, 1):
                row['seats'].append(study_case(guide, target, seat, exact))
                save()
        report['admission'] = admission(report['cases'])
        if {n: normalized_hash(BASE/n) for n in SOURCES} != report['source_sha256_lf']:
            raise RuntimeError('Source changed during fixture study')
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        report['status'], report['failure'] = 'incomplete', f'{type(error).__name__}: {error}'
        raise
    finally:
        save()
    print(json.dumps(report['admission'], indent=2), flush=True)


if __name__ == '__main__':
    main()
