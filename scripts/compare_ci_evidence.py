"""Compare every retained CI JSON leaf; isolate measured metadata from semantics.

Input directories contain the eleven downloaded artifact ZIPs named by artifact.
Manifests are the public Actions artifacts arrays (id/name/digest). No extraction,
external solver invocation, tolerance adjustment or baseline rewriting occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS = {'pid', 'elapsed_seconds', 'seconds', 'cpu_seconds', 'wall_seconds', 'initialization_seconds',
                'parent_wall_seconds', 'process_wall_seconds', 'product_seconds', 'product_wall_seconds',
                'serialization_seconds', 'solve_and_query_seconds', 'total_seconds', 'whole_process_cpu_seconds',
                'worker_wall_seconds', 'python_peak_bytes', 'output_bytes', 'runtime',
                'VmHWM_bytes', 'VmPeak_bytes', 'VmRSS_bytes', 'VmSize_bytes', 'self_seconds', 'cumulative_seconds'}
RAW_HASHES = {'raw_profiles_sha256', 'raw_profile_sha256', 'raw_report_sha256'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def verify_tree(value, files, receipts, revision):
    if isinstance(value, list):
        for child in value:
            verify_tree(child, files, receipts, revision)
    elif isinstance(value, dict):
        if 'source_sha256_lf' in value:
            for name, expected in value['source_sha256_lf'].items():
                # The original hand reviewer records package-relative basenames.
                path = ROOT/('poker_spot/'+name if '/' not in name else name)
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError('Source path escapes repository')
                source = (subprocess.check_output(['git', 'show', revision+':'+path.relative_to(ROOT).as_posix()], cwd=ROOT)
                          if revision else path.read_bytes())
                if sha(source.replace(b'\r\n', b'\n')) != expected:
                    raise ValueError('Source mismatch: '+name)
                receipts['source_hashes'] += 1
        if 'raw_report_sha256' in value:
            if sha(files[Path(value['path']).name]) != value['raw_report_sha256']:
                raise ValueError('Raw range report digest mismatch')
            receipts['raw_hashes'] += 1
        for key in ('raw_profiles', 'raw_reference_evidence'):
            if isinstance(value.get(key), dict) and 'sha256' in value[key]:
                if sha(files[Path(value[key]['path']).name]) != value[key]['sha256']:
                    raise ValueError('Raw evidence digest mismatch')
                receipts['raw_hashes'] += 1
        if 'receipt' in value and 'accepted_configuration' in value:
            receipt = value['receipt']
            if (receipt['configuration'] != value['accepted_configuration']
                    or receipt['configuration_sha256'] != digest(receipt['configuration'])
                    or receipt['result_sha256'] != digest(value['result'])):
                raise ValueError('Accepted worker receipt mismatch')
            receipts['worker_receipts'] += 1
        if 'result_sha256' in value and 'result' in value:
            if value['result_sha256'] != digest(value['result']):
                raise ValueError('Result digest mismatch')
            receipts['result_hashes'] += 1
        for child in value.values():
            verify_tree(child, files, receipts, revision)


def load_artifacts(directory, manifest, revision=None):
    expected = {a['with']['name'] for a in json.loads((ROOT/'tests/fixtures/ci-gates.json').read_text())['artifacts']}
    if {a['name'] for a in manifest} != expected or len(manifest) != len(expected):
        raise ValueError('Expected all eleven artifact groups, exactly once')
    groups, receipts = {}, {'zip_hashes': 0, 'source_hashes': 0, 'raw_hashes': 0, 'worker_receipts': 0, 'result_hashes': 0}
    for item in manifest:
        raw = (directory/(item['name']+'.zip')).read_bytes()
        if item['digest'] != 'sha256:'+sha(raw):
            raise ValueError('Artifact ZIP digest mismatch: '+item['name'])
        receipts['zip_hashes'] += 1
        with zipfile.ZipFile(directory/(item['name']+'.zip')) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate archive entries')
            files = {name: archive.read(name) for name in names}
        groups[item['name']] = files
        for name, data in files.items():
            if not name.endswith('.json'):
                continue
            value = json.loads(data)
            verify_tree(value, files, receipts, revision)
            # These raw profiles contain runtime/PID fields and therefore change hashes.
            for key in ('raw_profile_sha256', 'raw_profiles_sha256'):
                if isinstance(value, dict) and key in value:
                    profile_name = name[:-5]+'.profiles.json'
                    if sha(files[profile_name]) != value[key]:
                        raise ValueError('Raw profile digest mismatch: '+name)
                    receipts['raw_hashes'] += 1
    return groups, receipts


def differences(left, right, path=()):
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                yield {'path': list(path+(key,)), 'baseline': left.get(key, '<missing>'), 'candidate': right.get(key, '<missing>')}
            else:
                yield from differences(left[key], right[key], path+(key,))
    elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        for i, (a, b) in enumerate(zip(left, right, strict=True)):
            yield from differences(a, b, path+(str(i),))
    elif left != right:
        yield {'path': list(path), 'baseline': left, 'candidate': right}


def measured_metadata(path):
    # Limits/gates and all strategies/EVs remain strict; no numeric tolerance here.
    if any(key in path for key in ('limits', 'budgets', 'gates')):
        return False
    if 'hotspots' in path:
        return True  # cProfile ranking/call counts are observations, not strategy evidence.
    if path[-1] in MEASUREMENTS | RAW_HASHES:
        return True
    if path[-1] == 'reference_workers':
        return True  # Explicit execution metadata; every independent game/profile is still compared.
    if len(path) > 1 and path[-2] == 'source_sha256_lf' and path[-1] in (
            'benchmarks/turn_decomposition.py', 'scripts/benchmark_turn_decomposition.py'):
        return True  # The two declared scheduling changes, verified against each revision above.
    if path[-1] == 'bytes' and 'peak_resident_memory' in path:
        return True
    return path[-1] == 'sha256' and path[-2] in ('raw_profiles', 'raw_reference_evidence')


def compare(baseline, candidate):
    rows, material = [], []
    if set(baseline) != set(candidate):
        raise ValueError('Artifact group set differs')
    for group in baseline:
        a, b = baseline[group], candidate[group]
        if set(a) != set(b):
            raise ValueError('Artifact file set differs: '+group)
        row = {'artifact': group, 'files': [], 'metadata_changes': 0, 'material_changes': 0}
        for name in a:
            item = {'name': name, 'byte_identical': a[name] == b[name]}
            if name.endswith('.json'):
                changed = list(differences(json.loads(a[name]), json.loads(b[name])))
                metadata = [d for d in changed if measured_metadata(tuple(d['path']))]
                failures = [d for d in changed if not measured_metadata(tuple(d['path']))]
                item.update(metadata_changes=len(metadata), material_changes=len(failures))
                row['metadata_changes'] += len(metadata)
                row['material_changes'] += len(failures)
                material += [dict(d, artifact=group, file=name) for d in failures]
                item['metadata_paths'] = [d['path'] for d in metadata]
            else:
                item['comparison'] = 'Readable rendition; authoritative JSON compared exhaustively'
            row['files'].append(item)
        rows.append(row)
    return {'groups': rows, 'material_differences': material,
            'comparison': 'Every JSON leaf checked exactly; only enumerated timing/memory/PID/profile-hash metadata separated'}


def audit_turn_policies(baseline, candidate):
    """Replay different saved policies in identical models, without new training.

    Frequency equality is not an existing general equilibrium gate. Keep the
    strict diff above; this diagnoses whether changed policies still meet the
    original same-policy, convergence and cross-play security requirements.
    """
    import numpy as np
    from benchmarks.turn_reference import IndependentTurnGame
    from benchmarks.turn_independent import product_solver, install_reference_profile, product_evaluation, history_location

    group = 'turn-independent-reference'
    left = json.loads(baseline[group]['turn-independent.profiles.json'])
    right = json.loads(candidate[group]['turn-independent.profiles.json'])
    cases = json.loads(baseline[group]['turn-independent.json'])['cases']
    other = {c['id']: c for c in json.loads(candidate[group]['turn-independent.json'])['cases']}
    if set(left) != set(right) or set(left) != set(other) or len(cases) != len(other):
        raise ValueError('Policy audit fixture sets differ')
    rows = []
    for case in cases:
        identity, config, gate = case['id'], case['config'], case['gates']
        if config != other[identity]['config'] or gate != other[identity]['gates']:
            raise ValueError('Policy audit configuration/gates differ')
        game = IndependentTurnGame(config)
        policies = {name: game.import_profile(raw[identity]['product_profile'])
                    for name, raw in (('baseline', left), ('candidate', right))}
        delta = np.abs(policies['baseline']-policies['candidate'])
        info = game.infos[np.unravel_index(delta.argmax(), delta.shape)[0]]
        row = {'id': identity, 'diagnostics': {}, 'max_probability_delta': float(delta.max()),
               'largest_difference': info, 'conditional_rows': {}}
        for name, policy in policies.items():
            evaluated = game.evaluate(policy)
            solver = product_solver(config)
            install_reference_profile(game, solver, policy)
            product = product_evaluation(solver)
            mismatch = max(abs(product[k]-evaluated[k]) for k in
                           ('oop_ev', 'ip_ev', 'nash_conv_chips', 'oop_lower_bound', 'oop_upper_bound'))
            if mismatch > gate['same_policy_numeric_chips'] or evaluated['nash_conv_chips'] > gate['convergence_chips']:
                raise ValueError('Saved policy violates original numeric/convergence gate')
            row['diagnostics'][name] = dict(evaluated, same_policy_numeric_delta=mismatch)
            collected = {}
            solver._walk(solver.root, *solver.weights, collect=collected)
            location, river = history_location(info['history'])
            node = solver.nodes[location]
            hand = next(i for i, h in enumerate(solver.hands[node.player]) if set(h) == set(info['hand']))
            ix = (hand,) if river is None else (solver.rivers.index(river), hand)
            values = collected[location]
            row['conditional_rows'][name] = {
                'actions': list(node.actions), 'frequency': node.average()[ix].tolist(),
                'action_evs': [float(v) if np.isfinite(v) else None for v in values['ev'][ix]],
                'own_strategic_reach_given_hand': float(values['own'][ix]/solver.weights[node.player][hand]),
                'opponent_reach_mass': float(values['opponent'][ix]), 'chance_reach': values['chance_reach']}
        a, b = row['diagnostics']['baseline'], row['diagnostics']['candidate']
        cross, reverse = policies['baseline'].copy(), policies['baseline'].copy()
        cross[game.info_player == 1] = policies['candidate'][game.info_player == 1]
        reverse[game.info_player == 0] = policies['candidate'][game.info_player == 0]
        x, y = game.evaluate(cross)['oop_ev'], game.evaluate(reverse)['oop_ev']
        tol = gate['same_policy_numeric_chips']
        if not (a['oop_lower_bound']-tol <= x <= b['oop_upper_bound']+tol
                and b['oop_lower_bound']-tol <= y <= a['oop_upper_bound']+tol
                and abs(a['oop_ev']-b['oop_ev']) <= a['nash_conv_chips']+b['nash_conv_chips']+tol):
            raise ValueError('Saved policies violate original security/combined-gap bounds')
        row.update(cross_play_oop_ev=x, reverse_cross_play_oop_ev=y, root_ev_delta=abs(a['oop_ev']-b['oop_ev']))
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate'):
        parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--'+name+'-manifest', type=Path, required=True)
        parser.add_argument('--'+name+'-revision', help='Git revision for source receipts; default current files')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit-turn-policies', action='store_true', help='Replay both saved policies in identical models; no training')
    args = parser.parse_args()
    baseline, a = load_artifacts(args.baseline, json.loads(args.baseline_manifest.read_text()), args.baseline_revision)
    candidate, b = load_artifacts(args.candidate, json.loads(args.candidate_manifest.read_text()), args.candidate_revision)
    report = dict(compare(baseline, candidate), verified_baseline=a, verified_candidate=b)
    if args.audit_turn_policies:
        sys.path.insert(0, str(ROOT))
        report['turn_policy_audit'] = audit_turn_policies(baseline, candidate)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(f'{len(report["groups"])} artifact groups; {len(report["material_differences"])} material differences')
    return bool(report['material_differences'])


if __name__ == '__main__':
    raise SystemExit(main())
