"""Cold-cost comparison for dense, lazy exact and reply-cutoff frontiers."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from frontier_cost import FactoredReply, LazyUpper
from one_face import OneFace, evaluate
from response_kernels import PreparedClaims
from revealed_frontier import RevealedUpper
from run_fixed_strategy import peak_memory
from run_gap_response import BASE, EXHAUSTIVE_CAP, TOL, WIDTH_TARGET, fixtures, normalized_hash, verify
from run_revealed_frontier import CAPS, make_search, decision

METHODS = ('prepared', 'dense', 'lazy', 'reply', 'factored')
BLOCKS = 3
REPEATS = 48
SOURCES = ('run_frontier_cost.py', 'frontier_cost.py', 'run_revealed_frontier.py',
           'revealed_frontier.py', 'response_kernels.py', 'run_gap_response.py',
           'gap_response.py', 'response_refinement.py', 'bounded_response.py',
           'game.py', 'one_face.py', 'fixed_strategy.py', 'guidance.py',
           'recall_ablation.py', 'run_fixed_strategy.py')


def make_oracle(method, guide, model, seat):
    game = model.target.game
    if method == 'prepared':
        return None
    if method == 'dense':
        return RevealedUpper(game, model, guide, seat)
    if method == 'factored':
        return FactoredReply(game, model, guide, seat)
    return LazyUpper(game, model, guide, seat, reply_only=method == 'reply')


def curve(method, guide, model, seat, claims, exact):
    oracle = make_oracle(method, guide, model, seat)
    search = make_search(method, guide, model, seat, EXHAUSTIVE_CAP, claims, oracle)
    points = [verify(search, search.advance(cap), model.target, exact) for cap in CAPS]
    if points[-1]['width'] > TOL:
        raise ArithmeticError('Exhaustive interval did not close')
    if callable(getattr(oracle, 'resources', None)):
        resources = oracle.resources()
    else:
        resources = getattr(oracle, 'resources', None)
    high = next(p['max_nodes'] for p in points if p['width'] <= WIDTH_TARGET)
    low = max((p['max_nodes']+1 for p in points if p['width'] > WIDTH_TARGET), default=1)
    while low < high:
        mid = (low+high)//2
        probe = make_search(method, guide, model, seat, mid, claims, oracle).solve()
        if probe['width'] <= WIDTH_TARGET:
            high = mid
        else:
            low = mid+1
    probe = make_search(method, guide, model, seat, high, claims, oracle)
    return points, verify(probe, probe.solve(), model.target, exact), resources


def measure(cases, point):
    blocks = []
    for b in range(BLOCKS):
        result = {}
        order = METHODS[b:] + METHODS[:b]
        for method in (order if b % 2 == 0 else order[::-1]):
            setup_cpu = setup_wall = search_cpu = search_wall = 0.
            for _ in range(REPEATS):
                for guide, model, claims, case in cases:
                    for row in case['seats']:
                        seat = row['seat']
                        expected = row['curves'][method][-2] if point == 'cap16' else row['width_target'][method]
                        w, c = time.perf_counter(), time.process_time()
                        oracle = make_oracle(method, guide, model, seat)
                        setup_cpu += time.process_time()-c
                        setup_wall += time.perf_counter()-w
                        w, c = time.perf_counter(), time.process_time()
                        actual = make_search(method, guide, model, seat, expected['max_nodes'], claims, oracle).solve()
                        search_cpu += time.process_time()-c
                        search_wall += time.perf_counter()-w
                        if any(abs(actual[k]-expected[k]) > TOL for k in ('lower', 'upper')):
                            raise ArithmeticError('Cold run changed a recorded endpoint')
            result[method] = {'setup_cpu_seconds': setup_cpu, 'setup_wall_seconds': setup_wall,
                              'search_cpu_seconds': search_cpu, 'search_wall_seconds': search_wall}
        blocks.append(result)
    return blocks


def compare(cases, timing):
    results = {}
    for method in METHODS[1:]:
        # Reuse #62's admission formula and thresholds. Deferred setup in
        # lazy methods is included in the search timer and thus in cold CPU.
        rows = [{**case, 'seats': [{**row, 'curves': {'prepared': row['curves']['prepared'],
                                                     'revealed': row['curves'][method]}}
                                  for row in case['seats']]} for case in cases]
        points = {p: [{'prepared': block['prepared'], 'revealed': block[method]} for block in blocks]
                  for p, blocks in timing.items()}
        results[method] = decision(rows, points)
        results[method]['width_target_cold_cpu_vs_dense'] = median(
            (b[method]['setup_cpu_seconds']+b[method]['search_cpu_seconds'])
            / (b['dense']['setup_cpu_seconds']+b['dense']['search_cpu_seconds']) for b in timing['width_target'])
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/frontier-cost.json')
    args = parser.parse_args()
    w, c = time.perf_counter(), time.process_time()
    archive = BASE/'outputs/revealed-frontier.json'
    old = json.loads(archive.read_text())
    report = {'status': 'running', 'platform': platform.platform(), 'python': platform.python_version(),
              'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'revealed_receipt_sha256_lf': normalized_hash(archive),
              'caps': CAPS, 'width_target': WIDTH_TARGET, 'timing_blocks': BLOCKS,
              'repeats_per_block': REPEATS, 'cases': []}
    try:
        cases = []
        for (label, guide, model), archived in zip(fixtures(), old['cases'], strict=True):
            game = model.game
            if type(game) is OneFace:
                game.rank = int
            if model.fingerprint() != archived['target_probabilities_sha256']:
                raise ArithmeticError('Fixture probabilities changed')
            exact = evaluate(game, model.policy)
            if any(abs(exact[k]-v) > TOL for k, v in archived['independent'].items()):
                raise ArithmeticError('Independent fixture values changed')
            claims = PreparedClaims(guide)
            case = {**label, 'target_probabilities_sha256': model.fingerprint(), 'independent': exact, 'seats': []}
            for seat in (0, 1):
                curves, widths, sizes = {}, {}, {}
                for method in METHODS:
                    curves[method], widths[method], sizes[method] = curve(method, guide, model, seat, claims, exact)
                for current, reference in (('prepared', 'prepared'), ('dense', 'revealed'), ('lazy', 'revealed')):
                    for now, past in zip(curves[current], archived['seats'][seat]['curves'][reference], strict=True):
                        if any(abs(now[k]-past[k]) > TOL for k in ('lower', 'upper')):
                            raise ArithmeticError('Prepared/dense/lazy endpoints differ from historical reference')
                for direct, factored in zip(curves['reply'], curves['factored'], strict=True):
                    if any(abs(direct[k]-factored[k]) > TOL for k in ('lower', 'upper')):
                        raise ArithmeticError('Factored reply endpoints differ from direct reply')
                case['seats'].append({'seat': seat, 'curves': curves, 'width_target': widths, 'resources': sizes})
            report['cases'].append(case)
            cases.append((guide, model, claims, case))
        report['timing'] = {p: measure(cases, p) for p in ('cap16', 'width_target')}
        report['admission'] = compare(report['cases'], report['timing'])
        if {n: normalized_hash(BASE/n) for n in SOURCES} != report['source_sha256_lf']:
            raise RuntimeError('Source changed during study')
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='incomplete', failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.update(wall_seconds=time.perf_counter()-w, cpu_seconds=time.process_time()-c,
                      peak_process_memory=peak_memory())
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['admission'], indent=2), flush=True)


if __name__ == '__main__':
    main()
