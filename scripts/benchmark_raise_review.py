"""One exact-size local review and independently trained matching river tree."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.raises import compare
from poker_spot.history import parse_history, reconstruct
from poker_spot.raise_review import run_raise_review
from poker_spot.review import digest


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/raise-review'))
    args = parser.parse_args()
    hand = parse_history((ROOT/'examples/hand-review-raises.txt').read_text())['hand']
    scenarios = json.loads((ROOT/'examples/hand-review-raise-scenarios.json').read_text())
    report = {'scope': 'Actual local exact-size review and independent same-tree training; no locks or hosted acceptance',
              'failures': [], 'accounting': reconstruct(hand),
              'review': run_raise_review(hand, scenarios, 2000, river_through=1, raise_to_cents=[12000, 27500])}
    profiles = {}
    if report['review']['status'] != 'computed':
        report['failures'].append('Actual local review did not complete')
    else:
        query = report['review']['queries'][0]
        config = {k: v for k, v in query['arguments'].items()
                  if k not in ('context', 'iterations', 'oop_hand', 'ip_hand')}
        compared = compare(config, 2000, 4000)
        profiles = {k: compared.pop(k) for k in ('reference_export', 'product_profile', 'product_output')}
        if query['result'] != profiles['product_output']:
            report['failures'].append('Disposable worker result differs from fresh independent-comparison product run')
        report['comparison'] = compared
        report['failures'] += compared['failures']
    sources = ['poker_spot/raises.py', 'poker_spot/raise_worker.py', 'poker_spot/raise_review.py',
               'poker_spot/history.py', 'poker_spot/review.py', 'poker_spot/core.py',
               'scripts/review_hand.py', 'scripts/solve_river_raises.py', 'scripts/benchmark_raise_review.py',
               'benchmarks/raises.py', 'benchmarks/raise_reference_worker.py',
               'examples/hand-review-raises.txt', 'examples/hand-review-raise-scenarios.json']
    report['source_sha256_lf'] = {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sources}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(profiles, indent=2, allow_nan=False)+'\n').encode()
    args.output.with_suffix('.profiles.json').write_bytes(raw)
    report['raw_profiles_sha256'] = hashlib.sha256(raw).hexdigest()
    report['reference_profile_sha256'] = digest(profiles.get('reference_export', {}).get('players'))
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# Exact-size local raise review', '', report['scope'], '',
             'Accounting pots: '+str([s['pot_end'] for s in report['accounting']['streets']])+'.',
             'Observed check/bet branch: `c/b4000`; raises total-to 12000/27500 cents. Not locked.']
    if 'comparison' in report:
        c = report['comparison']
        lines += [f'Product/reference root EV: {c["product_root_ev"]} / {c["reference_root_ev"]}.',
                  f'Product/reference NashConv: {c["product_nashconv"]} / {c["reference_nashconv"]}.',
                  f'Maximum same-policy discrepancy: {c["same_policy_max_delta"]}; unchanged gate 1e-8 chips.']
    lines += ['Failures: '+str(report['failures'])]
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines))
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
