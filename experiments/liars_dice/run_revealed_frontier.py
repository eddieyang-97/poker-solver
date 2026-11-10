"""Compare an information-relaxed frontier with the prepared +1 frontier."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from game import Game
from one_face import OneFace, evaluate
from recall_training import Layout
from response_kernels import PreparedClaims, PreparedFrontier
from revealed_frontier import RevealedFrontier, RevealedUpper, oracle_resources
from run_fixed_strategy import peak_memory
from run_gap_response import (BASE, BUDGETS, EXHAUSTIVE_CAP, TOL, WIDTH_TARGET,
                              fixtures, normalized_hash, verify)

SOURCES = ('run_revealed_frontier.py', 'revealed_frontier.py', 'response_kernels.py',
           'gap_response.py', 'bounded_response.py', 'one_face.py', 'fixed_strategy.py',
           'run_gap_response.py', 'recall_ablation.py', 'game.py', 'guidance.py', 'response_refinement.py',
           'recall_training.py')
CAPS = (1, *BUDGETS, EXHAUSTIVE_CAP)
METHODS = ('prepared', 'revealed')
TIMING_BLOCKS = 3
REPEATS = 48


def make_search(method, guide, model, seat, cap, claims, oracle):
    game = model.target.game
    if method == 'prepared':
        return PreparedFrontier(game, guide, model, seat, cap, claims, reuse_reach=True)
    return RevealedFrontier(game, guide, model, seat, cap, claims, oracle)


def check_curve(guide, model, seat, claims, oracle, exact):
    curves = {}
    minimum = {}
    for method in METHODS:
        search = make_search(method, guide, model, seat, EXHAUSTIVE_CAP, claims, oracle)
        points = [verify(search, search.advance(cap), model.target, exact) for cap in CAPS]
        if points[-1]['width'] > TOL:
            raise ArithmeticError('Exhaustive check did not close to the independent BR')
        curves[method] = points
        high = next(p['max_nodes'] for p in points if p['width'] <= WIDTH_TARGET)
        low = max((p['max_nodes']+1 for p in points if p['width'] > WIDTH_TARGET), default=1)
        while low < high:
            mid = (low + high) // 2
            probe = make_search(method, guide, model, seat, mid, claims, oracle).solve()
            if probe['width'] <= WIDTH_TARGET:
                high = mid
            else:
                low = mid + 1
        probe = make_search(method, guide, model, seat, high, claims, oracle)
        minimum[method] = verify(probe, probe.solve(), model.target, exact)
    return {'seat': seat, 'curves': curves, 'width_target': minimum}


def timings(cases, point):
    blocks = []
    for block in range(TIMING_BLOCKS):
        row = {}
        for method in (METHODS if block % 2 == 0 else METHODS[::-1]):
            setup_cpu = setup_wall = search_cpu = search_wall = 0.
            for _ in range(REPEATS):
                for guide, model, claims, case in cases:
                    for seat_row in case['seats']:
                        seat = seat_row['seat']
                        expected = (seat_row['curves'][method][-2] if point == 'cap16'
                                    else seat_row['width_target'][method])
                        oracle = None
                        if method == 'revealed':
                            w, c = time.perf_counter(), time.process_time()
                            oracle = RevealedUpper(model.target.game, model, guide, seat)
                            setup_cpu += time.process_time()-c
                            setup_wall += time.perf_counter()-w
                        w, c = time.perf_counter(), time.process_time()
                        result = make_search(method, guide, model, seat, expected['max_nodes'], claims, oracle).solve()
                        search_cpu += time.process_time()-c
                        search_wall += time.perf_counter()-w
                        if any(abs(result[k]-expected[k]) > TOL for k in ('lower', 'upper')):
                            raise ArithmeticError('Fresh timed search changed deterministic endpoint')
            row[method] = {'setup_cpu_seconds': setup_cpu, 'setup_wall_seconds': setup_wall,
                           'search_cpu_seconds': search_cpu, 'search_wall_seconds': search_wall}
        blocks.append(row)
    return blocks


def decision(cases, timed):
    slack_ratios = []
    width_ratios = []
    increases = []
    for case in cases:
        for row in case['seats']:
            br = case['independent'][f'br{row["seat"]}']
            base, reveal = (row['curves'][m][:-1] for m in METHODS)
            upper_slack = [sum(max(0., p['upper']-br) for p in curve) for curve in (base, reveal)]
            if upper_slack[0] > TOL:
                slack_ratios.append(upper_slack[1]/upper_slack[0])
            widths = [sum(p['width'] for p in curve) for curve in (base, reveal)]
            if widths[0] > TOL:
                width_ratios.append(widths[1]/widths[0])
            increases.extend(r['upper']-b['upper'] for b, r in zip(base, reveal, strict=True))
    width_cpu = timed['width_target']
    cold = median((b['revealed']['setup_cpu_seconds'] + b['revealed']['search_cpu_seconds'])
                  / b['prepared']['search_cpu_seconds'] for b in width_cpu)
    warm = median(b['revealed']['search_cpu_seconds']/b['prepared']['search_cpu_seconds'] for b in width_cpu)
    limits = {'median_upper_slack_ratio': .70, 'worst_upper_increase': .02, 'width_target_cold_cpu_ratio': 1.25}
    return {'median_upper_slack_ratio': median(slack_ratios), 'median_width_ratio': median(width_ratios),
            'worst_upper_increase': max(increases), 'width_target_cold_cpu_ratio': cold,
            'width_target_search_cpu_ratio': warm, 'thresholds': limits,
            'passed': median(slack_ratios) <= limits['median_upper_slack_ratio']
            and max(increases) <= limits['worst_upper_increase'] and cold <= limits['width_target_cold_cpu_ratio']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/revealed-frontier.json')
    args = parser.parse_args()
    w, c = time.perf_counter(), time.process_time()
    archive = BASE/'outputs/gap-response.json'
    previous = json.loads(archive.read_text())
    report = {'status': 'running', 'platform': platform.platform(), 'python': platform.python_version(),
              'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'gap_receipt_sha256_lf': normalized_hash(archive), 'caps': CAPS, 'width_target': WIDTH_TARGET,
              'timing_blocks': TIMING_BLOCKS, 'repeats_per_block': REPEATS, 'cases': []}
    try:
        cases = []
        for (label, guide, model), archived in zip(fixtures(), previous['cases'], strict=True):
            game = model.game
            if type(game) is OneFace:
                game.rank = int
            if model.fingerprint() != archived['target_probabilities_sha256']:
                raise ArithmeticError('Fixture probabilities changed')
            exact = evaluate(game, model.policy)
            if any(abs(exact[k]-v) > TOL for k, v in archived['independent'].items()):
                raise ArithmeticError('Fixture reference changed')
            case = {**label, 'target_probabilities_sha256': model.fingerprint(), 'independent': exact, 'seats': []}
            claims = PreparedClaims(guide)
            for seat in (0, 1):
                oracle = RevealedUpper(game, model, guide, seat)
                prior = np.asarray(game.prior)
                root = float(prior @ oracle.upper((), prior))
                if not exact[f'br{seat}']-TOL <= root <= 1+TOL:
                    raise ArithmeticError('Revealed root value violates best response bounds')
                row = check_curve(guide, model, seat, claims, oracle, exact)
                row.update(revealed_root_upper=root, oracle_resources=oracle.resources)
                case['seats'].append(row)
            report['cases'].append(case)
            cases.append((guide, model, claims, case))
        report['timing'] = {point: timings(cases, point) for point in ('cap16', 'width_target')}
        report['admission'] = decision(report['cases'], report['timing'])
        full = Game()
        report['full_rule_static_inventory'] = oracle_resources(Layout(full).graph, len(full.hands))
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
