"""Development-only before/after training comparison; not hosted acceptance.

The baseline is actual turn.py from the deployed PR #32 merge, hash checked
before loading. Both variants run in this runtime with the same core evaluator.
Timings include construction/training/checkpoints/projection, exclude imports
and transport, and impose no kernel limits. Use benchmark_turn_pilot.py for
fresh bounded workers. No timing threshold replaces a numerical/release gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from poker_spot.turn import TurnSolver
from poker_spot.turn_pilot import _canonicalize_tree, prepare, project, solver_config
from scripts.benchmark_turn_pilot import scenarios

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '3f3aeb093c75c62dbb2665122f8d1fbe58c5a0e4'
TURN_HASH = 'fb546353b2875dec377b2966a9c09282bb6a65617505760b1b731e0d66a7e572'
CORE_HASH = 'cb65e1c88ff65ea2580c67a2dbd26937326d2abc50c4a0e8be686aa290158fc9'


def sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def baseline_class():
    source = subprocess.check_output(['git', 'show', BASELINE+':poker_spot/turn.py'], cwd=ROOT)
    if sha(source) != TURN_HASH or sha((ROOT/'poker_spot/core.py').read_bytes()) != CORE_HASH:
        raise ValueError('Pinned baseline or shared evaluator differs; comparison rejected')
    module = types.ModuleType('poker_spot._training_baseline')
    sys.modules[module.__name__] = module
    exec(compile(source, BASELINE+':poker_spot/turn.py', 'exec'), module.__dict__)
    return module.TurnSolver


def run(cls, request):
    args = prepare(request)
    start, cpu = time.perf_counter(), time.process_time()
    solver = cls(**solver_config(args))
    _canonicalize_tree(solver, args)
    result = solver.solve(args['iterations'])
    rows = {}
    solver._walk(solver.root, *solver.weights, collect=rows)
    views = project(solver, args['views'])
    elapsed = {'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu}
    return solver, result, rows, views, elapsed


def compare(before, after):
    a, output_a, rows_a, views_a, _ = before
    b, output_b, rows_b, views_b, _ = after
    if output_a != output_b or views_a != views_b or list(a.nodes) != list(b.nodes):
        raise AssertionError('Output, checkpoints, projected views or node identity changed')
    for name in a.nodes:
        for field in ('regret', 'strategy_sum', 'strategy'):
            np.testing.assert_array_equal(getattr(a.nodes[name], field), getattr(b.nodes[name], field))
        np.testing.assert_array_equal(a.nodes[name].average(), b.nodes[name].average())
        for field in rows_a[name]:
            np.testing.assert_array_equal(rows_a[name][field], rows_b[name][field])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-training.json'))
    args = parser.parse_args()
    baseline = baseline_class()
    cases = [{'id': 'pinned_example', 'request': json.loads((ROOT/'examples/turn-pilot.json').read_text())}, *scenarios()]
    report = {'baseline_commit': BASELINE, 'baseline_turn_sha256_lf': TURN_HASH,
              'shared_core_sha256_lf': CORE_HASH, 'platform': platform.platform(),
              'python': platform.python_version(), 'numpy': np.__version__,
              'mode': 'Local sequential same-runtime training comparison, no kernel limits or hosted acceptance',
              'timing_scope': 'Build/train/checkpoints/all-node evaluation/projection; excludes imports and transport',
              'candidate_sources_sha256_lf': {path: sha((ROOT/path).read_bytes()) for path in
                  ('poker_spot/turn.py', 'poker_spot/turn_pilot.py', 'scripts/benchmark_turn_training.py')},
              'cases': []}
    for case in cases:
        row = dict(case, samples=[])
        for repeat in range(args.repeats):
            # Alternate order so systematic warmup does not always favor one variant.
            if repeat % 2:
                after, before = run(TurnSolver, case['request']), run(baseline, case['request'])
            else:
                before, after = run(baseline, case['request']), run(TurnSolver, case['request'])
            compare(before, after)
            row['samples'].append({'baseline': before[-1], 'candidate': after[-1], 'exact_parity': True,
                                   'diagnostics': after[1]['diagnostics']})
        row['median_wall_seconds'] = {key: statistics.median(s[key]['wall_seconds'] for s in row['samples'])
                                      for key in ('baseline', 'candidate')}
        report['cases'].append(row)
        print(case['id'], row['median_wall_seconds'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
