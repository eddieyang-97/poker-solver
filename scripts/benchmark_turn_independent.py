"""Train and cross-evaluate an independent full turn/river development reference."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.turn_independent import compare_fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--reference-iterations', type=int, default=4000)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-independent'))
    args = parser.parse_args()
    if not 20 <= args.iterations <= 2000 or not 20 <= args.reference_iterations <= 10000:
        parser.error('Product/reference iterations outside development bounds')
    root = Path(__file__).resolve().parents[1]
    paths = ['benchmarks/turn-independent-fixtures.json', 'benchmarks/turn_reference.py',
             'benchmarks/turn_reference_worker.py', 'benchmarks/turn_independent.py',
             'scripts/benchmark_turn_independent.py', 'poker_spot/turn.py', 'poker_spot/core.py']
    report = {'mode': 'Actual independently constructed/trained full-state turn reference',
              'limitation': 'In-repository development reference, not an externally audited solver or gold standard',
              'python': platform.python_version(), 'cases': [], 'failures': [],
              'source_sha256_lf': {p: hashlib.sha256((root/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths}}
    raw = {}
    lines = ['# Independently trained small turn/river games', '', report['limitation'], '',
             '| Fixture | Product EV | Reference EV | Product gap | Reference gap | Same-policy max delta | Status |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for fixture in json.loads((root/paths[0]).read_text()):
        try:
            result = compare_fixture(fixture, args.iterations, args.reference_iterations)
            exported, product = result.pop('reference_export'), result.pop('product_profile')
            raw[fixture['id']] = {'reference': exported, 'product_profile': product}
            profile_bytes = json.dumps(exported['profile'], sort_keys=True, separators=(',', ':')).encode()
            result['reference_profile_sha256'] = hashlib.sha256(profile_bytes).hexdigest()
            result['reference_metadata'] = {key: value for key, value in exported.items() if key != 'profile'}
            result['turn_policies'] = {name: [row for row in profile if not any(token.startswith('R:') for token in row['history'])]
                                       for name, profile in (('product', product), ('reference', exported['profile']))}
            report['cases'].append(result)
            report['failures'].extend(f'{fixture["id"]}: {failure}' for failure in result['failures'])
            a, b = result['product_policy_in_reference'], result['reference_policy_in_reference']
            line = (f'| {fixture["id"]} | {a["oop_ev"]:.8f} | {b["oop_ev"]:.8f} | {a["nash_conv_chips"]:.8f} | '
                    f'{b["nash_conv_chips"]:.8f} | {result["same_policy_numeric_delta"]:.3g} | {"FAIL" if result["failures"] else "PASS"} |')
            lines.append(line)
            print(line, flush=True)
        except Exception as error:
            failure = f'{fixture["id"]}: {type(error).__name__}: {error}'
            report['failures'].append(failure)
            print(failure, flush=True)
    lines += ['', '## Discrepancies', '']+[f'- {f}' for f in report['failures']]
    if not report['failures']:
        lines.append('No declared gate failed. General full-game GTO and hosted turn acceptance are not established.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_path = args.output.with_suffix('.profiles.json')
    raw_bytes = (json.dumps(raw, indent=2, allow_nan=False)+'\n').encode()
    raw_path.write_bytes(raw_bytes)
    report['raw_profiles'] = {'path': raw_path.as_posix(), 'sha256': hashlib.sha256(raw_bytes).hexdigest()}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
