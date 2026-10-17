"""Measure maximum-dimension local turn workloads in disposable, time-bounded workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_worker(config, iterations, timeout):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    start = time.perf_counter()
    try:
        process = subprocess.run([sys.executable, '-I', str(root/'benchmarks/turn_performance.py')],
                                 input=json.dumps({'config': config, 'iterations': iterations}),
                                 capture_output=True, text=True, env=environment, timeout=timeout, check=True)
        result = json.loads(process.stdout)
        result['process_wall_seconds'] = time.perf_counter()-start
        result['status'] = 'COMPLETED'
        return result
    except subprocess.TimeoutExpired:
        return {'status': 'TIMEOUT', 'process_wall_seconds': time.perf_counter()-start,
                'timeout_seconds': timeout, 'failure': 'Worker killed at local study deadline; no result or memory peak available'}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
        return {'status': 'ERROR', 'process_wall_seconds': time.perf_counter()-start,
                'failure': str(error), 'stderr': getattr(error, 'stderr', '')[-4000:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-performance'))
    args = parser.parse_args()
    if not 20 <= args.iterations <= 2000 or not 1 <= args.repeats <= 3 or not 1 <= args.timeout <= 180:
        parser.error('Use 20-2000 iterations, 1-3 repeats and a 1-180 second deadline')
    root = Path(__file__).resolve().parents[1]
    paths = ['benchmarks/turn-performance-fixtures.json', 'benchmarks/turn_performance.py',
             'scripts/benchmark_turn_performance.py', 'poker_spot/turn.py', 'poker_spot/core.py']
    report = {'mode': 'Actual fresh local subprocess measurements; no hosted request',
              'limitations': 'Maximum configured dimensions on two synthetic inputs, not a proof of worst runtime over all inputs. '
                             'Resident-memory peaks include imports/native allocations; not address-space usage or an enforced memory cap. '
                             'Timing and memory are observations, not portable performance acceptance thresholds.',
              'iterations': args.iterations, 'repeats': args.repeats, 'worker_timeout_seconds': args.timeout,
              'source_sha256_lf': {p: hashlib.sha256((root/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                   for p in paths}, 'cases': [], 'failures': []}
    lines = ['# Maximum-dimension local turn performance', '', report['limitations'], '',
             '| Fixture / repeat | Process seconds | Compute seconds | Peak resident MiB | NashConv % pot | Status |',
             '| --- | --- | --- | --- | --- | --- |']
    for fixture in json.loads((root/paths[0]).read_text()):
        case = {'id': fixture['id'], 'config': fixture['config'], 'runs': []}
        for repeat in range(1, args.repeats+1):
            result = run_worker(fixture['config'], args.iterations, args.timeout)
            result['repeat'] = repeat
            case['runs'].append(result)
            if result['status'] == 'COMPLETED':
                if result['range_combos'] != {'oop': 24, 'ip': 24} or result['river_decision_templates'] != 30:
                    result['status'] = 'ERROR'
                    result['failure'] = 'Fixture did not exercise maximum range and uncollapsed tree dimensions'
                row = (f'| {fixture["id"]} / {repeat} | {result["process_wall_seconds"]:.3f} | '
                       f'{result["total_seconds"]:.3f} | {result["peak_resident_memory"]["bytes"]/2**20:.2f} | '
                       f'{result["diagnostics"]["nash_conv_pct_pot"]:.6g} | {result["status"]} |')
            else:
                row = f'| {fixture["id"]} / {repeat} | {result["process_wall_seconds"]:.3f} | — | — | — | {result["status"]} |'
            if result['status'] != 'COMPLETED':
                report['failures'].append(f'{fixture["id"]} / {repeat}: {result["failure"]}')
            lines.append(row)
            print(row, flush=True)
        report['cases'].append(case)
    lines += ['', '## Unresolved gates', '',
              'No hosted timeout, address-space limit, concurrency, OAuth or ChatGPT turn acceptance was tested.',
              'Convergence is reported, not used as a performance pass criterion.']
    lines += [f'- {failure}' for failure in report['failures']]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
