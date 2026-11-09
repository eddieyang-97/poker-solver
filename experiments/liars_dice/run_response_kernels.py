"""Matched profiling and fixture gate for the prepared terminal kernel."""
import argparse
import cProfile
import json
import os
from pathlib import Path
import platform
import pstats
from statistics import median
import time

import numpy as np

from one_face import evaluate
from response_kernels import PreparedClaims, PreparedDepthFirst, PreparedFrontier
from run_fixed_strategy import peak_memory
from run_gap_response import (BASE, BUDGETS, EXHAUSTIVE_CAP, METHODS, TOL,
                              admission, build_search, fixtures, normalized_hash, verify)

SOURCES = ('run_response_kernels.py', 'response_kernels.py', 'run_gap_response.py',
           'gap_response.py', 'bounded_response.py', 'guidance.py', 'one_face.py',
           'recall_ablation.py', 'game.py', 'run_fixed_strategy.py')
MODES = tuple(f'{m}-{k}' for k in ('original', 'prepared', 'combined') for m in METHODS)
TIMING_BLOCKS = 3
REPEATS_PER_BLOCK = 24


def search(mode, guide, target, seat, cap, claims):
    schedule, kernel = mode.split('-')
    if kernel == 'original':
        return build_search(schedule, guide, target, seat, cap)
    if schedule == 'legacy':
        return PreparedDepthFirst(target.game, guide, target, seat, cap, claims,
                                  reuse_reach=kernel == 'combined')
    return PreparedFrontier(target.game, guide, target, seat, cap, claims, schedule,
                            reuse_reach=kernel == 'combined')


def parity(mode, guide, target, claims, archived):
    exact = evaluate(target.game, target.policy)
    rows = []
    max_error = 0.
    schedule = mode.split('-')[0]
    for seat in (0, 1):
        expected = archived['seats'][seat]
        for cap in (*BUDGETS, EXHAUSTIVE_CAP, expected['width_target_checkpoints'][schedule]['max_nodes']):
            reference = search(f'{schedule}-original', guide, target, seat, cap, claims)
            candidate = search(mode, guide, target, seat, cap, claims)
            old, new = reference.solve(), candidate.solve()
            error = max(abs(old[k]-new[k]) for k in ('lower', 'upper'))
            if (error > TOL or old['stats'] != new['stats'] or reference.decisions.keys() != candidate.decisions.keys()
                    or any(not np.array_equal(reference.decisions[h], candidate.decisions[h]) for h in reference.decisions)):
                raise ArithmeticError('Prepared scoring changed the search trajectory')
            max_error = max(max_error, error)
            replay = verify(candidate, new, target, exact)
            rows.append({'seat': seat, 'cap': cap, 'lower': new['lower'], 'upper': new['upper'],
                         'reference_error': error, 'replay_error': replay['realization_error']})
        for cap, row in zip(BUDGETS, expected['checkpoints'][schedule], strict=False):
            actual = next(x for x in rows if x['seat'] == seat and x['cap'] == cap)
            if any(abs(actual[k] - row[k]) > TOL for k in ('lower', 'upper')):
                raise ArithmeticError('Archived #60 bounds changed')
    return {'max_reference_error': max_error, 'checks': rows}


def timed_batch(cases, mode, operating_point, repeats):
    schedule = mode.split('-')[0]
    for _ in range(repeats):
        for guide, target, claims, archived in cases:
            for seat in (0, 1):
                cap = (16 if operating_point == 'cap16'
                       else archived['seats'][seat]['width_target_checkpoints'][schedule]['max_nodes'])
                search(mode, guide, target, seat, cap, claims).solve()


def profile(cases, mode):
    profiler = cProfile.Profile()
    profiler.runcall(timed_batch, cases, mode, 'cap16', REPEATS_PER_BLOCK)
    stats = pstats.Stats(profiler)
    # Sort by self time and retain full keys, including filenames for functions
    # that share a name in the old and new implementations.
    largest = sorted(stats.stats.items(), key=lambda x: -x[1][2])[:15]
    return {'total_seconds': stats.total_tt,
            'hotspots': [{'file': Path(file).name, 'line': line, 'function': name,
                          'calls': calls, 'self_seconds': own, 'cumulative_seconds': cumulative}
                         for (file, line, name), (_, calls, own, cumulative, _) in largest]}


def timing(cases, point):
    blocks = []
    for block in range(TIMING_BLOCKS):
        # Within each block compare fresh runs on the same games and policies.
        # Alternate each implementation's position and reverse the second block.
        modes = MODES[block:] + MODES[:block]
        if block == 1:
            modes = modes[::-1]
        result = {}
        for mode in modes:
            w, c = time.perf_counter(), time.process_time()
            timed_batch(cases, mode, point, REPEATS_PER_BLOCK)
            result[mode] = {'cpu_seconds': time.process_time()-c, 'wall_seconds': time.perf_counter()-w}
        blocks.append(result)
    return blocks


def comparison(archived, cap16, width):
    # Use the unchanged #60 gate on a fresh, interleaved comparison with its
    # original controls. Keep prepared controls as a separate cost comparison.
    def ratio(blocks, numerator, denominator):
        return median(b[numerator]['cpu_seconds']/b[denominator]['cpu_seconds'] for b in blocks)

    quality = admission(archived['cases'])
    threshold = quality['thresholds']
    results = {}
    for control in ('legacy', 'reach'):
        old = quality['controls'][control]
        results[control] = {
            'median_summed_width_ratio': old['median_summed_width_ratio'],
            'worst_absolute_width_increase': old['worst_absolute_width_increase'],
            'cap16_original_control_cpu_ratio': ratio(cap16, 'gap-combined', f'{control}-original'),
            'cap16_combined_control_cpu_ratio': ratio(cap16, 'gap-combined', f'{control}-combined'),
            'width_target_combined_control_cpu_ratio': ratio(width, 'gap-combined', f'{control}-combined'),
            'cap16_claim_only_original_control_cpu_ratio': ratio(cap16, 'gap-prepared', f'{control}-original'),
        }
    return {'controls': results, 'thresholds': threshold,
            'cap16_gap_kernel_cpu_ratio': ratio(cap16, 'gap-combined', 'gap-original'),
            'cap16_gap_reach_reuse_cpu_ratio': ratio(cap16, 'gap-combined', 'gap-prepared'),
            'width_target_gap_kernel_cpu_ratio': ratio(width, 'gap-combined', 'gap-original'),
            'passed': all(row['median_summed_width_ratio'] <= threshold['median_summed_width_ratio']
                          and row['worst_absolute_width_increase'] <= threshold['worst_absolute_width_increase']
                          and row['cap16_original_control_cpu_ratio'] <= threshold['aggregate_cpu_ratio_at_cap16']
                          for row in results.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/response-kernels.json')
    args = parser.parse_args()
    w, c = time.perf_counter(), time.process_time()
    archive = BASE/'outputs/gap-response.json'
    previous = json.loads(archive.read_text())
    report = {'status': 'running', 'platform': platform.platform(), 'processor': platform.processor(),
              'python': platform.python_version(), 'numpy': np.__version__,
              'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'gap_receipt_sha256_lf': normalized_hash(archive),
              'timing_blocks': TIMING_BLOCKS, 'repeats_per_block': REPEATS_PER_BLOCK, 'fixtures': []}
    try:
        cases = []
        for (_, guide, target), old in zip(fixtures(), previous['cases'], strict=True):
            if target.fingerprint() != old['target_probabilities_sha256']:
                raise ArithmeticError('Fixture target fingerprint changed')
            begin = time.perf_counter()
            claims = PreparedClaims(guide)
            setup = time.perf_counter()-begin
            cases.append((guide, target, claims, old))
            report['fixtures'].append({'probabilities_sha256': target.fingerprint(), 'setup_wall_seconds': setup,
                                       'parity': {m: parity(m, guide, target, claims, old)
                                                  for m in MODES if not m.endswith('-original')}})
        report['profile'] = {m: profile(cases, m) for m in ('gap-original', 'gap-prepared', 'gap-combined')}
        report['cap16'] = timing(cases, 'cap16')
        report['width_target'] = timing(cases, 'width')
        report['admission'] = comparison(previous, report['cap16'], report['width_target'])
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
