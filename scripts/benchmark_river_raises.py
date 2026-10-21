"""Independent local river raise validation; no hosted dependencies or acceptance."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.raises import compare, policy_delta, product_profile, reference_game
from poker_spot.core import DECK
from poker_spot.raises import RaiseRiverSolver
from scripts.solve_river_raises import execute

ROOT = Path(__file__).resolve().parents[1]


def random_policy_checks(config, seed, count=6):
    solver = RaiseRiverSolver(**config)
    game, _ = reference_game(config)
    rng = np.random.default_rng(seed)
    largest = 0
    for _ in range(count):
        for node in solver.nodes.values():
            node.avg_sum = rng.random(node.avg_sum.shape)+0.1
        delta, _, _ = policy_delta(solver, game, product_profile(solver, game))
        largest = max(largest, float(delta))
    return {'seed': seed, 'policies': count, 'maximum_delta': largest}


def performance_cases():
    rows = []
    for board in ('2c,3d,4h,8s,9c', 'Ks,9s,5h,Td,Ts'):
        deck = [c for c in DECK if c not in board.split(',')]
        hands = list(itertools.combinations(deck, 2))
        ranges = [','.join(''.join(hands[(i*37+side*17) % len(hands)])+':'+str(0.3+(i % 8)/10)
                           for i in range(24)) for side in (0, 1)]
        config = {'context': 'post_session', 'board': board, 'oop_range': ranges[0], 'ip_range': ranges[1],
                  'pot': 100, 'stack': 600, 'minimum_bet': 2, 'bet_sizes': [0.5, 1],
                  'raise_sizes': [0.5, 1], 'iterations': 5000}
        solver = RaiseRiverSolver(**{k: v for k, v in config.items() if k not in ('context', 'iterations')})
        config.update(oop_hand=''.join(solver.h0[0]), ip_hand=''.join(solver.h1[0]))
        started = time.perf_counter()
        result = execute(config)
        result['parent_wall_seconds'] = time.perf_counter()-started
        result['input'] = config
        rows.append(result)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--reference-iterations', type=int, default=4000)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/river-raises'))
    parser.add_argument('--performance', action='store_true', help='Measure actual maximum local workloads in disposable workers')
    args = parser.parse_args()
    if not 20 <= args.iterations <= 5000 or not 20 <= args.reference_iterations <= 10000:
        parser.error('Iteration limits exceeded')
    paths = ['benchmarks/raise-fixtures.json', 'benchmarks/raises.py', 'benchmarks/raise_reference_worker.py',
             'benchmarks/harness.py', 'benchmarks/reference_worker.py', 'poker_spot/core.py', 'poker_spot/raises.py',
             'poker_spot/raise_worker.py', 'scripts/solve_river_raises.py', 'scripts/benchmark_river_raises.py']
    report = {'scope': 'Actual independent finite-tree river raise validation, local only; not full-game GTO or hosted acceptance',
              'cases': [], 'failures': [], 'performance': [],
              'source_sha256_lf': {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths}}
    profiles = {}
    lines = ['# Local river raises: independent validation', '', report['scope'], '',
             '| Fixture | Product EV | Reference EV | Product gap | Reference gap | Max same-policy delta | Status |',
             '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for i, fixture in enumerate(json.loads((ROOT/paths[0]).read_text())):
        try:
            row = compare(fixture['config'], args.iterations, args.reference_iterations)
            profiles[fixture['id']] = {'reference': row.pop('reference_export'), 'product': row.pop('product_profile'),
                                       'product_output': row.pop('product_output')}
            row.update(id=fixture['id'], description=fixture['description'])
            row['random_policy_checks'] = random_policy_checks(fixture['config'], 1300+i)
            if row['random_policy_checks']['maximum_delta'] > 1e-8:
                row['failures'].append('Mixed-policy evaluation disagrees')
            if 'analytical_root_ev' in fixture:
                row['analytical_root_ev'] = fixture['analytical_root_ev']
                for side in ('product', 'reference'):
                    if abs(row[side+'_root_ev']-fixture['analytical_root_ev']) > row[side+'_nashconv']+1e-8:
                        row['failures'].append(side+' analytical EV disagrees')
            report['cases'].append(row)
            report['failures'] += [fixture['id']+': '+f for f in row['failures']]
            line = (f'| {fixture["id"]} | {row["product_root_ev"]:.8f} | {row["reference_root_ev"]:.8f} | '
                    f'{row["product_nashconv"]:.6f} | {row["reference_nashconv"]:.6f} | '
                    f'{row["same_policy_max_delta"]:.3g} | {"FAIL" if row["failures"] else "PASS"} |')
            print(line, flush=True)
            lines.append(line)
        except Exception as error:
            failure = fixture['id']+': '+type(error).__name__+': '+str(error)
            report['failures'].append(failure)
            print(failure, flush=True)
    if args.performance:
        report['performance'] = performance_cases()
        lines += ['', '## Measured maximum local workloads', '']
        for p in report['performance']:
            if p['status'] != 'computed':
                report['failures'].append('Maximum workload failed: '+str(p.get('error')))
                lines.append('- FAIL: '+str(p.get('error')))
                continue
            if p['result']['nash_conv_chips'] > p['input']['pot']*0.005:
                report['failures'].append('Maximum workload convergence gate failed')
            m = p['metrics']
            lines.append(f'- {p["input"]["board"]}: {p["parent_wall_seconds"]:.3f}s parent wall, '
                         f'{m["cpu_seconds"]:.3f}s CPU, {m["peak_resident_memory"]["bytes"]/1024**2:.2f} MiB peak resident; '
                         f'{m["output_bytes"]} output bytes; NashConv {p["result"]["nash_conv_chips"]}.')
        lines += ['', 'These are measured samples, not universal bounds or hosted acceptance.']
    lines += ['', '## Discrepancies', '']+[f'- {f}' for f in report['failures']]
    if not report['failures']:
        lines.append('No declared gate failed. Input ranges and omitted actions remain model assumptions.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(profiles, indent=2, allow_nan=False)+'\n').encode()
    args.output.with_suffix('.profiles.json').write_bytes(raw)
    report['raw_profile_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
