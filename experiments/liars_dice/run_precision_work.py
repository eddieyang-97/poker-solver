"""Precision sensitivity, global query-effect diagnostics and paired cold timing."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from one_face import OneFace, evaluate
from precision_work import TracedSelective
from response_kernels import PreparedClaims
from run_fixed_strategy import peak_memory
from run_gap_response import BASE, TOL, fixtures, normalized_hash, verify
from run_selective_frontier import make_oracle, make_search

METHODS = ('prepared', 'factored', 'selective4', 'selective16')
WIDTHS = (.1, .02, .005)
MAX_NODES = 256
BLOCKS = 6
REPEATS = 96
SOURCES = ('run_precision_work.py', 'precision_work.py', 'run_selective_frontier.py',
           'selective_frontier.py', 'frontier_cost.py', 'run_revealed_frontier.py',
           'revealed_frontier.py', 'response_kernels.py', 'run_gap_response.py',
           'gap_response.py', 'response_refinement.py', 'bounded_response.py',
           'game.py', 'one_face.py', 'fixed_strategy.py', 'guidance.py',
           'recall_ablation.py', 'run_fixed_strategy.py')


def new_search(method, guide, model, seat, cap, claims, traced=False):
    oracle = make_oracle(method, guide, model, seat)
    if traced and method.startswith('selective'):
        return TracedSelective(model.game, guide, model, seat, cap, claims, oracle,
                               max_queries=int(method.removeprefix('selective')))
    return make_search(method, guide, model, seat, cap, claims, oracle)


def trajectory(method, guide, model, seat, claims, exact):
    search = new_search(method, guide, model, seat, MAX_NODES, claims, traced=True)
    points, selected = [], {}
    for cap in range(1, MAX_NODES+1):
        bound = search.advance(cap)
        points.append(bound)
        for width in WIDTHS:
            if str(width) not in selected and bound['width'] <= width:
                selected[str(width)] = verify(search, bound, model, exact)
        if bound['width'] <= TOL:
            closure = verify(search, bound, model, exact)
            break
    else:
        raise ArithmeticError('Fixture failed to close within declared expansion cap')
    if len(selected) != len(WIDTHS):
        raise ArithmeticError('Missing precision checkpoint')
    # Instrumentation is outside the cold benchmark. Compare its final
    # policy and endpoints with an uninstrumented fresh solve.
    plain = new_search(method, guide, model, seat, cap, claims)
    baseline = plain.solve()
    if any(abs(bound[k]-baseline[k]) > TOL for k in ('lower', 'upper')):
        raise ArithmeticError('Instrumentation changed bounds')
    if search.decisions.keys() != plain.decisions.keys() or any(
            not np.array_equal(search.decisions[h], plain.decisions[h]) for h in search.decisions):
        raise ArithmeticError('Instrumentation changed feasible actions')
    events = getattr(search, 'events', [])
    return {'curve': points, 'precision': selected, 'closure': closure, 'events': events}


def timed(cases, width):
    blocks = []
    for block in range(BLOCKS):
        totals = {m: {'cpu_ns': 0, 'wall_ns': 0, 'solves': 0} for m in METHODS}
        # Interleave methods for each case. Reverse/rotate order each repetition
        # so a long sequential method batch cannot absorb a whole drift period.
        for repeat in range(REPEATS):
            order = METHODS[(block+repeat) % len(METHODS):]+METHODS[:(block+repeat) % len(METHODS)]
            if block % 2:
                order = order[::-1]
            for guide, model, claims, case in cases:
                for row in case['seats']:
                    for method in order:
                        expected = row['methods'][method]['precision'][str(width)]
                        w, c = time.perf_counter_ns(), time.process_time_ns()
                        search = new_search(method, guide, model, row['seat'], expected['max_nodes'], claims)
                        actual = search.solve()
                        totals[method]['cpu_ns'] += time.process_time_ns()-c
                        totals[method]['wall_ns'] += time.perf_counter_ns()-w
                        totals[method]['solves'] += 1
                        if any(abs(actual[k]-expected[k]) > TOL for k in ('lower', 'upper')):
                            raise ArithmeticError('Fresh cold solve differs from precision checkpoint')
        blocks.append(totals)
    return blocks


def summarize(cases, timing):
    result = {}
    for width, blocks in timing.items():
        methods = {}
        for method in METHODS:
            cpu = [b[method]['cpu_ns']/b['prepared']['cpu_ns'] for b in blocks]
            wall = [b[method]['wall_ns']/b['prepared']['wall_ns'] for b in blocks]
            points = [s['methods'][method]['precision'][width] for c in cases for s in c['seats']]
            methods[method] = {'median_cpu_ratio': median(cpu), 'cpu_ratio_min': min(cpu),
                               'cpu_ratio_max': max(cpu), 'median_wall_ratio': median(wall),
                               'expansions': sum(p['stats']['expanded_own_nodes'] for p in points),
                               'queries': sum(p['stats'].get('oracle_queries', p['stats'].get('oracle_calls', 0))
                                              for p in points)}
        result[width] = methods
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/precision-work.json')
    args = parser.parse_args()
    w, c = time.perf_counter(), time.process_time()
    archive = BASE/'outputs/selective-frontier.json'
    old = json.loads(archive.read_text())
    report = {'status': 'running', 'platform': platform.platform(), 'python': platform.python_version(),
              'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'selective_receipt_sha256_lf': normalized_hash(archive), 'widths': WIDTHS,
              'max_nodes': MAX_NODES, 'blocks': BLOCKS, 'repeats': REPEATS,
              'admission': 'unchanged_no_go', 'cases': []}
    try:
        cases = []
        for (label, guide, model), archived in zip(fixtures(), old['cases'], strict=True):
            if type(model.game) is OneFace:
                model.game.rank = int
            if model.fingerprint() != archived['target_probabilities_sha256']:
                raise ArithmeticError('Target fingerprint changed')
            claims = PreparedClaims(guide)
            exact = evaluate(model.game, model.policy)
            if any(abs(exact[k]-v) > TOL for k, v in archived['independent'].items()):
                raise ArithmeticError('Independent fixture reference changed')
            case = {**label, 'target_probabilities_sha256': model.fingerprint(), 'independent': exact, 'seats': []}
            for seat in (0, 1):
                methods = {m: trajectory(m, guide, model, seat, claims, exact) for m in METHODS}
                for m in METHODS:
                    for width in (.02,):
                        before = archived['seats'][seat]['width_target'][m]
                        now = methods[m]['precision'][str(width)]
                        if any(abs(now[k]-before[k]) > TOL for k in ('lower', 'upper', 'max_nodes')):
                            raise ArithmeticError('Historical precision checkpoint changed')
                case['seats'].append({'seat': seat, 'methods': methods})
            report['cases'].append(case)
            cases.append((guide, model, claims, case))
        report['timing'] = {str(width): timed(cases, width) for width in WIDTHS}
        report['summary'] = summarize(report['cases'], report['timing'])
        if {n: normalized_hash(BASE/n) for n in SOURCES} != report['source_sha256_lf']:
            raise RuntimeError('Source changed during measurement')
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='incomplete', failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.update(wall_seconds=time.perf_counter()-w, cpu_seconds=time.process_time()-c,
                      peak_process_memory=peak_memory())
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=2), flush=True)


if __name__ == '__main__':
    main()
