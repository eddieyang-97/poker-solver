"""Fresh local turn solves checked by a scalar policy/BR oracle, not a second trainer."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.turn_policy import TurnPolicyOracle
from benchmarks.harness import REFERENCE_COMMIT
from poker_spot.turn import TurnSolver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-benchmark'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture_path = root / 'benchmarks/turn-fixtures.json'
    fixtures = json.loads(fixture_path.read_text())
    report = {'mode': 'Fresh product solves plus scalar policy/BR evaluation',
              'limitation': 'Oracle reads product public tree; no separately trained external turn engine',
              'oracle_ranker': {'repository': 'https://github.com/noambrown/poker_solver',
                                'commit': REFERENCE_COMMIT, 'function': 'games.river_holdem.evaluate_7'},
              'python': platform.python_version(), 'iterations': args.iterations,
              'input_sha256_lf': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                  for p in (fixture_path, root / 'poker_spot/turn.py', root / 'benchmarks/turn_policy.py')},
              'gates': {'same_policy_numeric_chips': 1e-8, 'nashconv_pct_pot': 0.5}, 'cases': [], 'failures': []}
    lines = ['# Experimental local turn/river validation', '',
             'Fresh CFR+ solves; scalar oracle reads the product tree and policy. No external turn trainer comparison.', '',
             '| Fixture | OOP EV | NashConv | Oracle max delta | Seconds | Status |',
             '| --- | --- | --- | --- | --- | --- |']
    for fixture in fixtures:
        started = time.perf_counter()
        try:
            solver = TurnSolver(**fixture['config'])
            result = solver.solve(args.iterations, ''.join(solver.hands[0][0]), ''.join(solver.hands[1][0]), '9c')
            oracle = TurnPolicyOracle(solver).evaluate()
        except Exception as error:
            failure = {'id': fixture['id'], 'failure': f'{type(error).__name__}: {error}'}
            report['failures'].append(failure)
            row = f'| {fixture["id"]} | — | — | — | — | ERROR: {type(error).__name__} |'
            lines.append(row)
            print(row, flush=True)
            continue
        numeric = max(abs(result['diagnostics'][key]-oracle[key]) for key in oracle)
        failures = []
        if numeric > report['gates']['same_policy_numeric_chips']:
            failures.append('Scalar policy/BR evaluation differs')
        if result['diagnostics']['nash_conv_pct_pot'] > report['gates']['nashconv_pct_pot']:
            failures.append('Restricted-game convergence gap exceeds 0.5% of initial pot')
        if abs(result['diagnostics']['zero_sum_residual']) > 1e-8:
            failures.append('Zero-sum payoff identity fails')
        if fixture['id'] == 'checkdown_known_outs' and abs(result['diagnostics']['oop_ev']-100/44) > 1e-9:
            failures.append('Known two-outs / always-win checkdown value differs')
        seconds = time.perf_counter()-started
        case = {'id': fixture['id'], 'config': fixture['config'], 'result': result, 'oracle': oracle,
                'max_numeric_delta': numeric, 'elapsed_seconds': seconds, 'failures': failures}
        report['cases'].append(case)
        report['failures'].extend({'id': fixture['id'], 'failure': f} for f in failures)
        row = f'| {fixture["id"]} | {oracle["oop_ev"]:.8f} | {oracle["nash_conv_chips"]:.8f} | {numeric:.3g} | {seconds:.3f} | {"FAIL" if failures else "PASS"} |'
        lines.append(row)
        print(row, flush=True)
    lines += ['', '## Discrepancies', '']
    lines += [f'- {f["id"]}: {f["failure"]}' for f in report['failures']] or ['No stated gate failed.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
