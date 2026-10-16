"""Run pinned offline same-tree river benchmarks and write JSON + Markdown reports."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.harness import REFERENCE_COMMIT, compare_fixture, tree_sensitivity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='.artifacts/benchmark')
    parser.add_argument('--reference-iterations', type=int, default=4000)
    parser.add_argument('--iterations', type=int, default=1500)
    parser.add_argument('--sensitivity', action='store_true')
    args = parser.parse_args()
    if not 20 <= args.iterations <= 10000 or not 20 <= args.reference_iterations <= 100000:
        parser.error('Iterations outside bounded benchmark budgets')
    fixture_file = Path('benchmarks/fixtures.json')
    fixtures = json.loads(fixture_file.read_text())
    report = {'reference': {'repository': 'https://github.com/noambrown/poker_solver',
                            'commit': REFERENCE_COMMIT, 'algorithm': 'VectorCFRTrainer CFR+, alternating, linear averaging, upstream naive showdown evaluator',
                            'license': 'MIT', 'chip_units_per_currency_unit': 100},
              'python': platform.python_version(),
              'input_sha256_lf': {str(p).replace('\\', '/'): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                  for p in (fixture_file, Path('poker_spot/core.py'), Path('benchmarks/harness.py'))},
              'cases': [], 'failures': []}
    lines = ['# Independent river benchmark', '',
             '| Fixture | Root EV delta / pot | Local NashConv | Reference NashConv | Status |',
             '| --- | --- | --- | --- | --- |']
    for fixture in fixtures:
        try:
            result = compare_fixture(fixture, args.iterations, args.reference_iterations)
            report['cases'].append(result)
            for failure in result['failures']:
                report['failures'].append({'id': fixture['id'], 'failure': failure})
            lines.append(f'| {fixture["id"]} | {result["root_ev_delta_pot"]:.8f} | '
                         f'{result["local_nashconv"]:.6f} | {result["reference_nashconv"]:.6f} | '
                         f'{"FAIL" if result["failures"] else "PASS"} |')
            print(lines[-1], flush=True)
        except Exception as exc:
            report['failures'].append({'id': fixture['id'], 'failure': f'{type(exc).__name__}: {exc}'})
            print(f'{fixture["id"]}: FAILED: {exc}', flush=True)
    if args.sensitivity:
        try:
            report['tree_sensitivity'] = tree_sensitivity(fixtures[2], args.reference_iterations)
        except Exception as exc:
            report['failures'].append({'id': 'tree_sensitivity', 'failure': f'{type(exc).__name__}: {exc}'})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
