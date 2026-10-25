"""Local Issue #25 exact equivalence, heuristic EV and target-policy experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from benchmarks.turn_feasibility import digest, full_record, identity, pack, sources, unpack
from benchmarks.turn_independent import (
    independent_train, install_reference_profile, product_profile, product_solver,
)
from benchmarks.turn_performance import peak_resident_memory
from benchmarks.turn_reference import IndependentTurnGame
from benchmarks.turn_resources import ADDRESS_BYTES, CPU_SECONDS
from benchmarks.turn_reuse import (
    NUMERIC, VERSION, bound_result, checkdown, equivalence_map, equivalent_key,
    evaluate, root_actions, same_mapped_game, similarity, transfer,
)
from poker_spot.core import DECK


def timed(operation):
    wall, cpu = time.perf_counter(), time.process_time()
    result = operation()
    return result, {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu}


def validate_independent(solver, game):
    policy = product_profile(game, solver)
    external = game.evaluate(policy)
    internal = evaluate(solver)
    error = max(abs(internal[k]-external[k]) for k in external)
    if error > NUMERIC:
        raise ValueError(f'Independent target-policy evaluation discrepancy {error}')
    return external, error


def root_difference(actual, expected, pot):
    if actual['actions'] != expected['actions'] or actual['hands'] != expected['hands']:
        raise ValueError('Root hand/action mapping differs')
    a, b = np.asarray(actual['ev']), np.asarray(expected['ev'])
    if not np.array_equal(np.isfinite(a), np.isfinite(b)):
        raise ValueError('Root conditional EV support differs')
    supported = np.isfinite(a).all(axis=1)
    changes = []
    for index in np.flatnonzero(supported):
        choice, reference = int(a[index].argmax()), int(b[index].argmax())
        # These compare one action + FIXED continuation, not optimal full deviations.
        if choice != reference:
            changes.append({'hand': actual['hands'][index], 'chosen': actual['actions'][choice],
                            'reference': expected['actions'][reference],
                            'reference_fixed_continuation_loss_pct_pot': float((b[index, reference]-b[index, choice])/pot*100)})
    return {'maximum_action_ev_error_pct_pot': float(np.max(abs(a-b), where=np.isfinite(a), initial=0)/pot*100),
            'fixed_continuation_action_changes': changes,
            'warning': 'Conditional fixed-policy action EVs are not certified by a root best-response gap'}


def gap_gate(evaluation, pot):
    if evaluation['nash_conv_chips'] > pot*.005 or evaluation['nash_conv_chips'] < -NUMERIC:
        raise ValueError('Fresh/reference solve fails unchanged 0.5%-pot convergence gate')


def online_probe(case, entry, raw_dir):
    command = [sys.executable, '-I', str(ROOT/'benchmarks/turn_reuse_worker.py')]
    if sys.platform != 'linux':
        command.append('--unlimited')
    request = {'case': case, 'entry': entry, 'raw_dir': str(raw_dir.resolve())}
    tick = time.perf_counter()
    process = subprocess.run(command, input=json.dumps(request), capture_output=True, text=True, timeout=20,
                             env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    if process.returncode:
        raise ValueError('Fresh online probe failed: '+process.stderr[-1500:])
    result = json.loads(process.stdout)
    result.update(parent_wall_including_startup_serialization_reap=time.perf_counter()-tick, parent_deadline_seconds=20)
    if sys.platform == 'linux':
        if (result['mode'] != 'linux_limits_not_hosted'
                or result['limits'] != {'cpu_seconds': [CPU_SECONDS]*2, 'address_space_bytes': [ADDRESS_BYTES]*2}
                or result['linux_memory']['VmPeak_bytes'] > ADDRESS_BYTES
                or result['cpu_through_snapshot_seconds'] > CPU_SECONDS
                or result['parent_wall_including_startup_serialization_reap'] > 20):
            raise ValueError('Fresh-process Linux resource receipt failed')
    return result


def compare_target(case, entry, raw_dir):
    config = case['config']
    components = {}
    source, components['source_construction'] = timed(lambda: product_solver(entry['config']))
    # Include real read/hash/decode/source reconstruction in per-target lookup costs.
    record, components['read_hash_decode_validate'] = timed(lambda: unpack((raw_dir/entry['file']).read_bytes(), entry['sha256'], source, 2000))
    target, components['target_construction'] = timed(lambda: product_solver(config))
    mapping = {c: case['card_mapping'].get(c, c) for c in DECK}
    strict = digest(identity(target, 2000)) == record['key']
    equivalent, components['equivalence_search'] = timed(lambda: equivalent_key(source)[0] == equivalent_key(target)[0])
    exact = strict or equivalent
    if exact:
        mapping = equivalence_map(source, target)
    _, components['policy_transfer'] = timed(lambda: transfer(record, source, target, mapping, exact=exact))
    evaluated, components['target_value_and_both_best_responses'] = timed(lambda: evaluate(target))
    return source, target, record, mapping, strict, equivalent, components, evaluated


def run(output):
    fixture_path = ROOT/'benchmarks/turn-reuse-fixtures.json'
    fixtures = json.loads(fixture_path.read_text())
    paths = ['benchmarks/turn_reuse.py', 'benchmarks/turn_reuse_worker.py', 'scripts/benchmark_turn_reuse.py', 'benchmarks/turn-reuse-fixtures.json',
             'benchmarks/turn_feasibility.py', 'benchmarks/turn_independent.py',
             'benchmarks/turn_reference.py', 'benchmarks/turn_reference_worker.py',
             'benchmarks/reference_worker.py', 'benchmarks/turn_resources.py', 'benchmarks/turn_performance.py',
             'poker_spot/core.py', 'poker_spot/turn.py']
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = output.parent/(output.name+'-policies')
    raw_dir.mkdir(exist_ok=True)
    report = {'version': VERSION, 'design': fixtures['design'], 'source_sha256_lf': sources(paths),
              'base_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform(),
                          'threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}},
              'measurement': 'Unlimited local in-process wall/CPU (imports excluded). Reference training isolated. Not hosted/Linux budget acceptance.',
              'sources': {}, 'targets': [], 'failures': []}
    raw = {}
    for name, config in fixtures['sources'].items():
        started = time.perf_counter()
        solver = product_solver(config)
        result, elapsed = timed(lambda: solver.solve(2000))
        independent = IndependentTurnGame(config)
        evaluated, delta = validate_independent(solver, independent)
        gap_gate(evaluated, solver.pot)
        record = full_record(solver, result)
        blob, packing = timed(lambda: pack(record))
        filename = name+'.json.gz'
        (raw_dir/filename).write_bytes(blob)
        report['sources'][name] = {'config': config, 'file': filename, 'sha256': hashlib.sha256(blob).hexdigest(),
                                  'compressed_bytes': len(blob), 'solve': elapsed, 'packing': packing,
                                  'offline_wall_including_independent_policy_check': time.perf_counter()-started,
                                  'evaluation': evaluated, 'same_policy_numeric_delta': delta}
        print(f'source {name}: gap={evaluated["nash_conv_chips"]:.6g}, {len(blob)} bytes', flush=True)
    for case in fixtures['targets']:
        row = {'id': case['id'], 'source': case['source'], 'kind': case['kind'], 'config': case['config'],
               'card_mapping': case['card_mapping']}
        report['targets'].append(row)
        try:
            data, row['online_lookup_transfer_evaluate'] = timed(lambda: compare_target(case, report['sources'][case['source']], raw_dir))
        except ValueError as error:
            row.update(status='unsupported', reason=str(error))
            if case['kind'] != 'unsupported':
                report['failures'].append(f'{case["id"]}: unexpected rejection: {error}')
            print(f'{case["id"]}: {row["status"]}: {error}', flush=True)
            continue
        source, target, record, mapping, strict, equivalent, components, evaluated = data
        row['online_components'] = components
        if case['kind'] == 'unsupported':
            report['failures'].append(f'{case["id"]}: expected unsupported case accepted')
        row.update(status='equivalent_and_verified' if equivalent else 'target_fixed_policy_evaluation',
                   strict_hit=strict, equivalence_hit=equivalent, policy_evaluation=evaluated,
                   root_value_bound=bound_result(evaluated, target.pot), similarity=similarity(source, target, mapping))
        row['same_mapped_strategic_game'] = same_mapped_game(source, target, mapping)
        if equivalent and case['kind'] not in ('exact', 'equivalent'):
            report['failures'].append(f'{case["id"]}: held-out approximation leaked equivalent game')
        if not equivalent and case['kind'] in ('exact', 'equivalent'):
            report['failures'].append(f'{case["id"]}: equivalence not recognized')
        game, row['independent_build'] = timed(lambda: IndependentTurnGame(case['config']))
        _, delta = validate_independent(target, game)
        exported, row['reference_training_parent'] = timed(lambda: independent_train(case['config'], 4000))
        reference = game.import_profile(exported['profile'])
        reference_eval = game.evaluate(reference)
        gap_gate(reference_eval, target.pot)
        row['independent_reference'] = reference_eval
        row['reference_profile_sha256'] = digest(exported['profile'])
        raw[case['id']] = {'reference': exported, 'transferred': game.export_profile(product_profile(game, target))}
        fresh, row['fresh_construction'] = timed(lambda: product_solver(case['config']))
        _, row['fresh_2000'] = timed(lambda: fresh.solve(2000))
        fresh_eval, fresh_delta = validate_independent(fresh, game)
        gap_gate(fresh_eval, target.pot)
        row['fresh_evaluation'] = fresh_eval
        short = product_solver(case['config'])
        short_result, row['fresh_200'] = timed(lambda: short.solve(200))
        row['short_checkpoints'] = short_result['checkpoints']
        short_eval, short_delta = validate_independent(short, game)
        row['short_evaluation'] = short_eval
        row['short_bound'] = bound_result(short_eval, target.pot)
        raw[case['id']]['fresh'] = game.export_profile(product_profile(game, fresh))
        # Independent profile -> product action EVs; independently check reverse evaluation.
        reference_solver = product_solver(case['config'])
        install_reference_profile(game, reference_solver, reference)
        _, reverse_delta = validate_independent(reference_solver, game)
        row['same_policy_numeric_delta'] = max(delta, fresh_delta, short_delta, reverse_delta)
        for label, values in (('transfer', evaluated), ('fresh', fresh_eval), ('short', short_eval)):
            if (values['oop_lower_bound'] > reference_eval['oop_upper_bound']+NUMERIC
                    or reference_eval['oop_lower_bound'] > values['oop_upper_bound']+NUMERIC):
                raise ValueError(f'{label}: independent best-response intervals are disjoint')
        if equivalent:
            scale = target.pot/source.pot
            original = record['diagnostics']
            row['scaled_source_value_delta'] = abs(evaluated['oop_ev']-original['oop_ev']*scale)
            if row['scaled_source_value_delta'] > NUMERIC:
                raise ValueError('Equivalent fixed-policy value changed')
        scaled = record['diagnostics']['oop_ev']*target.pot/source.pot
        adjusted = scaled+checkdown(target)-checkdown(source)*target.pot/source.pot
        row['estimates'] = {}
        for label, value in (('scaled_cached_ev', scaled), ('equity_adjusted_ev', adjusted),
                             ('target_fixed_policy_ev', evaluated['oop_ev']),
                             ('bound_midpoint', row['root_value_bound']['midpoint']),
                             ('short_fresh_ev', short_eval['oop_ev'])):
            error = abs(value-reference_eval['oop_ev'])/target.pot*100
            interval_error = max(reference_eval['oop_lower_bound']-value, value-reference_eval['oop_upper_bound'], 0)/target.pot*100
            row['estimates'][label] = {'oop_ev': value, 'absolute_error_pct_pot': error,
                                     'distance_outside_reference_interval_pct_pot': interval_error,
                                     'root_value_sign_error': value*reference_eval['oop_ev'] < 0}
        row['root_action_comparison'] = root_difference(root_actions(target), root_actions(reference_solver), target.pot)
        if case['id'] in ('exact_repeat', 'dry_bluff_weight_0.1', 'flush_loses_suit'):
            row['fresh_process_probe'] = online_probe(case, report['sources'][case['source']], raw_dir)
            for sample in row['fresh_process_probe']['samples']:
                if max(abs(sample['evaluation'][k]-evaluated[k]) for k in evaluated) > NUMERIC:
                    raise ValueError('Fresh-process policy replay differs')
        print(f'{case["id"]}: {row["status"]}, gap={evaluated["nash_conv_chips"]:.5g}, '
              f'{row["root_value_bound"]["status"]}, online={row["online_lookup_transfer_evaluate"]["wall_seconds"]:.4f}s', flush=True)
    changed = [r for r in report['targets'] if r['kind'] == 'approximate' and 'estimates' in r]
    approximate = [r for r in changed if not r['same_mapped_strategic_game']]
    report['summary'] = {'targets': len(report['targets']), 'strict_hits': sum(r.get('strict_hit', False) for r in report['targets']),
                         'equivalent_hits': sum(r.get('equivalence_hit', False) for r in report['targets']),
                         'unsupported': sum(r['status'] == 'unsupported' for r in report['targets']),
                         'changed_input_targets': len(changed),
                         'mapped_strategic_duplicates': sum(r['same_mapped_strategic_game'] for r in changed),
                         'approximate_targets': len(approximate),
                         'narrow_changed_input_bounds': sum(r['root_value_bound']['status'] == 'bounded_root_value' for r in changed),
                         'narrow_transfer_bounds': sum(r['root_value_bound']['status'] == 'bounded_root_value' for r in approximate),
                         'narrow_short_solve_bounds': sum(r['short_bound']['status'] == 'bounded_root_value' for r in approximate),
                         'compressed_catalog_bytes': sum(r['compressed_bytes'] for r in report['sources'].values()),
                         'errors': {name: {'median_pct_pot': statistics.median(r['estimates'][name]['absolute_error_pct_pot'] for r in approximate),
                                           'max_pct_pot': max(r['estimates'][name]['absolute_error_pct_pot'] for r in approximate)}
                                    for name in approximate[0]['estimates']} if approximate else {}}
    report['peak_resident_memory_whole_study'] = peak_resident_memory()
    report['summary']['approximation_speedups'] = {
        'median_fresh2000_over_lookup_transfer_br': statistics.median(
            (r['fresh_construction']['wall_seconds']+r['fresh_2000']['wall_seconds'])/r['online_lookup_transfer_evaluate']['wall_seconds'] for r in approximate),
        'median_fresh2000_over_fresh200': statistics.median(
            (r['fresh_construction']['wall_seconds']+r['fresh_2000']['wall_seconds'])/(r['fresh_construction']['wall_seconds']+r['fresh_200']['wall_seconds']) for r in approximate)}
    raw_bytes = (json.dumps(raw, allow_nan=False)+'\n').encode()
    raw_path = output.with_suffix('.profiles.json')
    raw_path.write_bytes(raw_bytes)
    report['profiles'] = {'file': raw_path.name, 'sha256': hashlib.sha256(raw_bytes).hexdigest()}
    report['catalog_directory'] = raw_dir.name
    output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# Local turn reuse experiment', '', report['design'], '', report['measurement'], '',
             '| Target | Classification | Error: scaled / adjusted / evaluated (% pot) | BR width (% pot) | Bound | Online wall |',
             '| --- | --- | ---: | ---: | --- | ---: |']
    for row in report['targets']:
        if 'estimates' not in row:
            lines.append(f'| {row["id"]} | {row["status"]}: {row.get("reason", "")} | — | — | — | — |')
            continue
        errors = ' / '.join(f'{row["estimates"][name]["absolute_error_pct_pot"]:.4f}'
                            for name in ('scaled_cached_ev', 'equity_adjusted_ev', 'target_fixed_policy_ev'))
        lines.append(f'| {row["id"]} | {row["status"]} | {errors} | '
                     f'{row["policy_evaluation"]["nash_conv_chips"]/row["config"]["pot"]*100:.4f} | '
                     f'{row["root_value_bound"]["status"]} | {row["online_lookup_transfer_evaluate"]["wall_seconds"]:.4f}s |')
    lines += ['', '## Summary', '', '```json', json.dumps(report['summary'], indent=2), '```', '',
              '## Integrity failures', '']
    lines += report['failures'] or ['None. Approximation errors and wide-bound abstentions are measured outcomes, not passing solutions.']
    output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-reuse'))
    args = parser.parse_args()
    return run(args.output)


if __name__ == '__main__':
    raise SystemExit(main())
