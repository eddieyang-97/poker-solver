"""Check turn-disabled solving against separately trained independent river games."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.harness import REFERENCE_COMMIT
from benchmarks.turn_decomposition import compare_decomposition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--reference-iterations', type=int, default=4000)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-decomposition'))
    args = parser.parse_args()
    if not 20 <= args.iterations <= 2000 or not 20 <= args.reference_iterations <= 100000:
        parser.error('Iterations outside local/reference bounds')
    root = Path(__file__).resolve().parents[1]
    paths = ['benchmarks/turn-decomposition-fixtures.json', 'benchmarks/turn_decomposition.py',
             'benchmarks/harness.py', 'benchmarks/reference_worker.py', 'poker_spot/turn.py',
             'poker_spot/core.py', 'scripts/benchmark_turn_decomposition.py']
    report = {'mode': 'Turn betting disabled; independent river CFR+ training and policy evaluation',
              'limitation': 'A decomposable special case, not general two-street external training',
              'python': platform.python_version(), 'reference_commit': REFERENCE_COMMIT,
              'source_sha256_lf': {p: hashlib.sha256((root/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                   for p in paths}, 'cases': [], 'failures': []}
    lines = ['# Turn-disabled independent river decomposition', '',
             'All public runouts enumerated; zero-mass cards skipped explicitly. Reference is independently trained.', '',
             '| Case | Rivers solved | EV delta | Combined gap bound | Same-policy EV / gap delta | Status |',
             '| --- | --- | --- | --- | --- | --- |']
    raw_exports = {}
    for fixture in json.loads((root/paths[0]).read_text()):
        started = time.perf_counter()

        def progress(number, row):
            if number % 12 == 0:
                print(f'{fixture["id"]}: {number}/48 public cards evaluated', flush=True)

        try:
            result = compare_decomposition(fixture, args.iterations, args.reference_iterations, progress)
            result['elapsed_seconds'] = time.perf_counter()-started
            raw_exports[fixture['id']] = {}
            for row in result['runouts']:
                if 'reference_export' not in row:
                    continue
                exported = row.pop('reference_export')
                raw_exports[fixture['id']][row['card']] = exported
                profile = {key: exported[key] for key in ('config', 'players', 'iterations', 'reference_commit')}
                row['reference_profile_sha256'] = hashlib.sha256(
                    json.dumps(profile, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                row['reference_final_raw_exploitability'] = exported['checkpoints'][-1]['raw_exploitability']
                row['reference_product_modules_loaded'] = exported['product_modules_loaded']
            report['cases'].append(result)
            report['failures'].extend(f'{fixture["id"]}: {error}' for error in result['failures'])
            count = sum(row['mass'] > 0 for row in result['runouts'])
            lines.append(f'| {fixture["id"]} | {count}/48 | {result["independent_ev_delta"]:.8g} | '
                         f'{result["combined_gap_bound"]:.8g} | {result["same_policy_ev_delta"]:.3g} / '
                         f'{result["same_policy_gap_delta"]:.3g} | {"FAIL" if result["failures"] else "PASS"} |')
            print(lines[-1], flush=True)
        except Exception as error:
            failure = f'{fixture["id"]}: {type(error).__name__}: {error}'
            report['failures'].append(failure)
            print(failure, flush=True)
    lines += ['', '## Discrepancies', '']+[f'- {f}' for f in report['failures']]
    if not report['failures']:
        lines.append('No declared gate failed. This does not validate a general turn betting game.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_path = args.output.with_suffix('.reference.json')
    raw_bytes = (json.dumps(raw_exports, indent=2, allow_nan=False)+'\n').encode('utf-8')
    raw_path.write_bytes(raw_bytes)
    report['raw_reference_evidence'] = {'path': raw_path.as_posix(), 'sha256': hashlib.sha256(raw_bytes).hexdigest(),
                                      'description': 'Full independent worker exports; retained locally/CI as a separate artifact'}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
