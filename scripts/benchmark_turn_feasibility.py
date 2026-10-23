"""Local-only turn feasibility: full-policy limits, exact reuse and honest misses."""
import argparse
import copy
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.turn_feasibility import digest, games, identity, sources, unpack
from benchmarks.turn_resources import ADDRESS_BYTES, CPU_SECONDS


def probe(request, *, unlimited=False, lookup=False, wall=20):
    if not 0 < wall <= 20:
        raise ValueError('Parent deadline cannot exceed 20 seconds')
    command = [sys.executable, '-I', str(ROOT/'benchmarks/turn_feasibility_worker.py')]
    command += ['--unlimited'] if unlimited else []
    command += ['--lookup'] if lookup else []
    started = time.perf_counter()
    try:
        process = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True, timeout=wall,
                                 env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    except subprocess.TimeoutExpired as error:
        progress = error.stderr or b''
        if isinstance(progress, bytes):
            progress = progress.decode(errors='replace')
        return {'status': 'WALL_TIMEOUT', 'parent_wall_seconds': time.perf_counter()-started,
                'deadline_seconds': wall, 'progress': progress[-4000:], 'killed_and_reaped': True}
    elapsed = time.perf_counter()-started
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {'status': 'SIGNAL' if process.returncode < 0 else 'ERROR', 'returncode': process.returncode,
                'parent_wall_seconds': elapsed, 'progress': process.stderr[-4000:]}
    result.update(parent_wall_seconds=elapsed, returncode=process.returncode, deadline_seconds=wall)
    if process.returncode:
        result['status'] = 'ERROR'
    if result['status'] == 'COMPLETED' and not unlimited:
        if result['limits'] != {'cpu_seconds': [CPU_SECONDS]*2, 'address_space_bytes': [ADDRESS_BYTES]*2}:
            raise ValueError('Unexpected Linux limits')
        result['budget_fit'] = (elapsed <= wall and result['worker_cpu_through_snapshot_seconds'] <= CPU_SECONDS
                                and result['linux_memory']['VmPeak_bytes'] <= ADDRESS_BYTES)
        result['headroom_fit'] = (elapsed <= 10 and result['worker_cpu_through_snapshot_seconds'] <= 10
                                  and result['linux_memory']['VmPeak_bytes'] <= ADDRESS_BYTES/2)
    if result['status'] == 'COMPLETED':
        result['converged'] = result['diagnostics']['nash_conv_pct_pot'] <= 0.5
    return result


def audit_record(record, config, iterations, fixture_id):
    """Replay the stored complete policy in separately constructed reference tree."""
    import numpy as np
    from benchmarks.turn_independent import product_evaluation, product_profile
    from benchmarks.turn_reference import IndependentTurnGame
    from poker_spot.turn import TurnSolver
    solver = TurnSolver(**config)
    fixture = next(f for f in json.loads((ROOT/'benchmarks/turn-independent-fixtures.json').read_text())
                   if f['id'] == fixture_id)
    for name, node in solver.nodes.items():
        node.strategy_sum[...] = record['nodes'][name]['frequency']
    solver.iterations = iterations
    game = IndependentTurnGame(fixture['config'])
    profile = product_profile(game, solver)
    actual, expected = product_evaluation(solver), game.evaluate(profile)
    metrics = ('oop_ev', 'ip_ev', 'nash_conv_chips', 'oop_lower_bound', 'oop_upper_bound')
    numeric = max(abs(actual[k]-expected[k]) for k in metrics)
    diagnostic_delta = max(abs(actual[k]-record['diagnostics'][k])
                           for k in ('oop_ev', 'ip_ev', 'raw_nash_conv_chips'))
    collected = {}
    solver._walk(solver.root, *solver.weights, collect=collected)
    ev_delta = 0.0
    for name, data in collected.items():
        previous = np.asarray(record['nodes'][name]['ev'], dtype=float)
        if not np.array_equal(np.isfinite(previous), np.isfinite(data['ev'])):
            raise ValueError('Stored action EV support differs on replay')
        finite = np.isfinite(previous)
        if finite.any():
            ev_delta = max(ev_delta, float(np.abs(previous[finite]-data['ev'][finite]).max()))
    if max(numeric, diagnostic_delta, ev_delta) > 1e-8:
        raise ValueError(f'Unchanged fixed-policy gate failed: {numeric}, {diagnostic_delta}, {ev_delta}')
    return {'same_policy_independent_max_delta': numeric, 'stored_diagnostics_max_delta': diagnostic_delta,
            'stored_action_ev_max_delta': ev_delta, 'gate_chips': 1e-8,
            'scope': 'Independent tree fixed-policy replay; separate training remains the ten-game CI gate'}


def coverage(cases, catalog):
    """Declared synthetic workload: repeated views plus adversarial different games."""
    from poker_spot.turn import TurnSolver
    queries = []
    for case in cases:
        for purpose in ('initial study', 'other hero hand', 'river output filter'):
            # These views do not change the game; no new training is requested.
            queries.append({'id': case['id']+'/'+purpose, 'config': copy.deepcopy(case['config']),
                            'iterations': case['iterations'], 'kind': 'repeated_game_view'})
    base = cases[0]
    for kind in ('board', 'weight', 'pot', 'stack', 'turn_size', 'river_size', 'iterations', 'missing_combo'):
        row = {'id': 'held_out/'+kind, 'config': copy.deepcopy(base['config']),
               'iterations': base['iterations'], 'kind': 'held_out_changed_game'}
        config = row['config']
        if kind == 'board':
            config['board'] = config['board'].replace('8s', '7s')
        elif kind == 'weight':
            first, *rest = config['oop_range'].split(',')
            config['oop_range'] = ','.join([first.split(':')[0]+':0.123', *rest])
        elif kind in ('pot', 'stack'):
            config[kind] += 1
        elif kind.endswith('size'):
            config[kind.replace('_size', '_bet_sizes')] = [0.75]
        elif kind == 'iterations':
            row['iterations'] = 1000
        else:
            config['oop_range'] = config['oop_range'].split(',', 1)[1]
        queries.append(row)
    for row in queries:
        key = digest(identity(TurnSolver(**row['config']), row['iterations']))
        row.update(key=key, status='exact_hit' if key in catalog else 'not_found',
                   miss_cost='No fallback executed; new independent validation/offline training or bounded live admission needed')
    repeated = [q for q in queries if q['kind'] == 'repeated_game_view']
    held = [q for q in queries if q['kind'] == 'held_out_changed_game']
    return {'queries': queries, 'synthetic_hits': sum(q['status'] == 'exact_hit' for q in queries),
            'total': len(queries), 'repeated_view_hits': sum(q['status'] == 'exact_hit' for q in repeated),
            'held_out_hits': sum(q['status'] == 'exact_hit' for q in held),
            'warning': 'Constructed reuse sensitivity, not measured user demand or population exact-hit coverage'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unlimited', action='store_true', help='Explicit local-only timings, never Linux acceptance')
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=2)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-feasibility'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = args.output.parent/(args.output.name+'-policies')
    artifacts.mkdir(exist_ok=True)
    paths = ['benchmarks/turn_feasibility.py', 'benchmarks/turn_feasibility_worker.py',
             'scripts/benchmark_turn_feasibility.py', 'benchmarks/turn-independent-fixtures.json',
             'benchmarks/turn_resources.py', 'benchmarks/turn_reference.py', 'benchmarks/turn_independent.py',
             'poker_spot/turn.py', 'poker_spot/core.py']
    report = {'mode': 'unlimited_local' if args.unlimited else 'linux_limits', 'cases': [], 'failures': [],
              'source_sha256_lf': sources(paths), 'python': platform.python_version(), 'platform': platform.platform(),
              'budgets': {'wall_seconds': 20, 'cpu_seconds': 20, 'address_space_bytes': ADDRESS_BYTES},
              'provisional_headroom': {'wall_seconds': 10, 'cpu_seconds': 10, 'address_space_bytes': ADDRESS_BYTES//2},
              'cold_warm_definition': 'New disposable process each solve/lookup; repeated OS-cache samples, not Render cold starts',
              'limitations': 'No production code, hosted integration, database or operational cache; no universal performance bound.'}
    catalog = set()
    catalog_bytes, catalog_json_bytes = 0, 0
    from poker_spot.turn import TurnSolver
    for case in games():
        row = dict(case, runs=[], audits=[])
        try:
            for repeat in range(args.repeats):
                path = (artifacts/f'{case["id"]}-{repeat}.json.gz').resolve()
                request = dict(config=case['config'], iterations=case['iterations'], artifact=str(path))
                result = probe(request, unlimited=args.unlimited)
                row['runs'].append(result)
                if result['status'] == 'ERROR':
                    report['failures'].append(f'{case["id"]}: {result}')
                if result['status'] != 'COMPLETED':
                    continue
                solver = TurnSolver(**case['config'])
                if not result['converged']:
                    continue  # Never admit unconverged records to the experiment catalog.
                record = unpack(path.read_bytes(), result['artifact_sha256'], solver, case['iterations'])
                row['audits'].append(audit_record(record, case['config'], case['iterations'], case['id']))
                views = [{'side': side, 'hand': ''.join(hand)} for side in (0, 1) for hand in solver.hands[side]]
                lookup = probe(dict(request, sha256=result['artifact_sha256'], views=views),
                               unlimited=args.unlimited, lookup=True)
                result['lookup'] = lookup
                if lookup['status'] not in ('COMPLETED', 'UNSUPPORTED', 'WALL_TIMEOUT', 'MEMORY_ERROR', 'SIGNAL'):
                    report['failures'].append(f'{case["id"]}: lookup {lookup}')
                if record['key'] not in catalog:
                    catalog_bytes += result['artifact_bytes']
                    catalog_json_bytes += result['full_json_bytes']
                catalog.add(record['key'])
            row['observed_candidate'] = (not args.unlimited and args.repeats >= 2
                and len(row['audits']) == args.repeats
                and all(r.get('candidate_input') and r.get('headroom_fit') and r.get('converged') for r in row['runs']))
        except Exception as error:
            report['failures'].append(f'{case["id"]}: {type(error).__name__}: {error}')
        report['cases'].append(row)
        print(f'{case["id"]}: {[r["status"] for r in row["runs"]]}, candidate={row.get("observed_candidate", False)}', flush=True)
    report['coverage'] = coverage(games(), catalog)
    # Real timeout then recovery, without touching production; original six probes remain separate CI gates.
    request = dict(config=games()[0]['config'], iterations=2000, artifact=str((artifacts/'timeout.json.gz').resolve()))
    report['negative_timeout'] = probe(request, unlimited=args.unlimited, wall=0.001)
    if report['negative_timeout']['status'] != 'WALL_TIMEOUT':
        report['failures'].append('Tight actual timeout did not fire')
    # Lower training is a convergence counterexample, not an optimization or candidate.
    recovery = dict(config=games()[-1]['config'], iterations=20,
                    artifact=str((artifacts/'short-training.json.gz').resolve()))
    report['short_training_recovery'] = probe(recovery, unlimited=args.unlimited)
    if report['short_training_recovery']['status'] == 'ERROR':
        report['failures'].append('Recovery worker failed')
    report['storage_bytes'] = sum(p.stat().st_size for p in artifacts.glob('*.json.gz'))
    report['catalog_storage_bytes'] = catalog_bytes
    report['catalog_full_json_bytes'] = catalog_json_bytes
    report['catalog_games'] = len(catalog)
    report['decision'] = {'bounded_live': 'candidate_for_separate_Render_validation' if any(c.get('observed_candidate') for c in report['cases']) else 'not_established',
                          'general_turn': 'no_go', 'library': 'defer: no demonstrated organic exact-repeat coverage',
                          'next': 'No hosted release. Consider only the measured small subset in #26; #25 needs independent demand evidence.'}
    lines = ['# Local turn feasibility', '', report['limitations'], '',
             '| Game | Solve status | Parent wall seconds | Gap % pot | Compressed bytes | Candidate |',
             '| --- | --- | --- | --- | --- | --- |']
    for case in report['cases']:
        for run in case['runs']:
            lines.append(f'| {case["id"]} | {run["status"]} | {run["parent_wall_seconds"]:.3f} | '
                         f'{run.get("diagnostics", {}).get("nash_conv_pct_pot", "—")} | '
                         f'{run.get("artifact_bytes", "—")} | {case.get("observed_candidate", False)} |')
    lines += ['', '## Decision', '', json.dumps(report['decision'], indent=2), '', report['coverage']['warning'],
              '', f'Scripted exact hits: {report["coverage"]["synthetic_hits"]}/{report["coverage"]["total"]}; '
              f'held-out changed games: {report["coverage"]["held_out_hits"]}/8.', '', '## Harness failures', '']
    lines += report['failures'] or ['None. Study success does not establish resource or hosted acceptance.']
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
