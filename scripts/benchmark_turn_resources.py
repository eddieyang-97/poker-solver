"""Probe unchanged turn workloads under existing Linux budgets; never hosted acceptance."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.turn_resources import ADDRESS_BYTES, CPU_SECONDS


def workloads():
    originals = json.loads((ROOT/'benchmarks/turn-performance-fixtures.json').read_text())
    rows = [dict(id=f['id'], config=copy.deepcopy(f['config']), iterations=2000) for f in originals]
    for name, count, sizes, iterations in (
            ('deep_4x4_two_sizes', 4, [0.5, 1.5], 2000),
            ('deep_12x12_two_sizes', 12, [0.5, 1.5], 2000),
            ('deep_24x24_one_size', 24, [0.5], 2000),
            ('deep_24x24_500_iterations', 24, [0.5, 1.5], 500)):
        config = copy.deepcopy(originals[0]['config'])
        for key in ('oop_range', 'ip_range'):
            config[key] = ','.join(config[key].split(',')[:count])
        config.update(turn_bet_sizes=sizes, river_bet_sizes=sizes)
        rows.append(dict(id=name, config=config, iterations=iterations))
    return rows


def run_probe(config, iterations, mode='limits', wall_seconds=20):
    if mode not in ('limits', 'profile') or not 0 < wall_seconds <= (20 if mode == 'limits' else 180):
        raise ValueError('Invalid mode or deadline; limited probes cannot exceed the hosted wall budget')
    started = time.perf_counter()
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    command = [sys.executable, '-I', str(ROOT/'benchmarks/turn_resources.py'), '--mode', mode]
    try:
        process = subprocess.run(command, input=json.dumps({'config': config, 'iterations': iterations}),
                                 capture_output=True, text=True, env=environment, timeout=wall_seconds)
    except subprocess.TimeoutExpired as error:
        progress = error.stderr or ''
        if isinstance(progress, bytes):
            progress = progress.decode(errors='replace')
        return {'status': 'WALL_TIMEOUT', 'process_wall_seconds': time.perf_counter()-started,
                'deadline_seconds': wall_seconds, 'progress': progress,
                'failure': 'Parent killed and reaped the worker; no completed result or memory peak available'}
    elapsed = time.perf_counter()-started
    if process.returncode:
        try:
            rejected = json.loads(process.stdout)
        except json.JSONDecodeError:
            rejected = {}
        if process.returncode > 0 and rejected.get('status') == 'ERROR':
            return dict(rejected, process_wall_seconds=elapsed, returncode=process.returncode, progress=process.stderr[-4000:])
        name = None
        if process.returncode < 0 and sys.platform != 'win32':
            try:
                name = signal.Signals(-process.returncode).name
            except ValueError:
                name = f'SIGNAL_{-process.returncode}'
        return {'status': 'SIGNAL' if name else 'ERROR', 'signal': name, 'returncode': process.returncode,
                'process_wall_seconds': elapsed, 'progress': process.stderr[-4000:],
                'failure': 'Worker did not complete; signal alone does not identify CPU limit versus another cause'}
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {'status': 'ERROR', 'process_wall_seconds': elapsed, 'failure': 'Worker did not return JSON'}
    result.update(process_wall_seconds=elapsed, deadline_seconds=wall_seconds)
    if mode == 'limits' and result['status'] == 'COMPLETED':
        if result['limits'] != {'cpu_seconds': [CPU_SECONDS]*2, 'address_space_bytes': [ADDRESS_BYTES]*2}:
            raise ValueError('Worker did not enforce the exact existing Linux budgets')
        result['within_observed_budgets'] = (elapsed <= wall_seconds and result['whole_process_cpu_seconds'] <= CPU_SECONDS
                                             and result['linux_memory']['VmPeak_bytes'] <= ADDRESS_BYTES)
        result['convergence_gate_passed'] = result['measurement']['diagnostics']['nash_conv_pct_pot'] <= 0.5
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', action='store_true', help='Add one separate unlimited cProfile run; instrumented timing is not budget evidence')
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-resources'))
    args = parser.parse_args()
    paths = ['benchmarks/turn-performance-fixtures.json', 'benchmarks/turn_resources.py',
             'benchmarks/turn_performance.py', 'scripts/benchmark_turn_resources.py', 'poker_spot/turn.py', 'poker_spot/core.py']
    report = {'mode': 'Development Linux budget probes of unchanged solver; separate instrumented profile',
              'limitations': 'Synthetic samples, not a portable runtime bound, Render capacity or authenticated hosted acceptance. '
                             'Windows probes are unsupported. Instrumented profile is unlimited and not resource acceptance.',
              'budgets': {'parent_wall_seconds': 20, 'cpu_seconds': CPU_SECONDS, 'address_space_bytes': ADDRESS_BYTES},
              'source_sha256_lf': {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths},
              'cases': [], 'resource_failures': [], 'harness_failures': []}
    lines = ['# Local turn resource study', '', report['limitations'], '',
             '| Workload | Status | Parent seconds | Whole CPU seconds | Peak virtual MiB | Converged |',
             '| --- | --- | --- | --- | --- | --- |']
    for fixture in workloads():
        result = run_probe(fixture['config'], fixture['iterations'])
        report['cases'].append(dict(fixture, result=result))
        status = result['status']
        if status == 'ERROR':
            report['harness_failures'].append(fixture['id'])
        if status not in ('COMPLETED', 'UNSUPPORTED') or result.get('within_observed_budgets') is False:
            report['resource_failures'].append(fixture['id'])
        memory = (result.get('linux_memory') or {}).get('VmPeak_bytes')
        row = (f'| {fixture["id"]} | {status} | {result["process_wall_seconds"]:.3f} | '
               f'{result.get("whole_process_cpu_seconds", "—")} | {memory/2**20 if memory else "—"} | '
               f'{result.get("convergence_gate_passed", "—")} |')
        lines.append(row)
        print(row, flush=True)
    if args.profile:
        case = workloads()[0]
        report['instrumented_profile'] = dict(case, result=run_probe(case['config'], case['iterations'], 'profile', 180))
        if report['instrumented_profile']['result']['status'] != 'COMPLETED':
            report['harness_failures'].append('instrumented_profile')
    lines += ['', '## Interpretation', '',
              'Resource failures remain recorded; a completed study does not mean all workloads fit the budgets.',
              'A resource fit without the convergence gate is not a usable solve. No MCP, OAuth or ChatGPT acceptance was attempted.',
              'Instrumented profile: separate unlimited execution; cumulative function times overlap and must not be summed.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['harness_failures'])


if __name__ == '__main__':
    raise SystemExit(main())
