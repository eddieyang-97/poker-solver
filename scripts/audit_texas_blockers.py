"""Report the separate weighted-blocker diagnostic; exit nonzero on any failed run."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.texas_blockers import analyze, capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--binary', type=Path)
    source.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/texas-blockers'))
    args = parser.parse_args()
    execution = capture(args.binary) if args.binary else json.loads(args.evidence.read_text())['execution']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.execution.json').write_text(json.dumps(execution, indent=2)+'\n', encoding='utf-8')
    report = {'mode': 'actual external execution' if args.binary else 'offline replay; no Texas executable run',
              'execution': execution, 'analysis': analyze(execution)}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# Weighted-blocker reference discrepancy', '',
             '| Maximum iterations | OOP EV | Independent NashConv | Gate | Status |',
             '| --- | --- | --- | --- | --- |']
    for row in report['analysis']['runs']:
        lines.append(f'| {row["maximum_iterations"]} | {row["oop_root_ev"]:.8f} | '
                     f'{row["independently_evaluated_nashconv"]:.8f} | '
                     f'{row["convergence_gate_chips"]:.2f} | {row["status"]} |')
    lines.extend(['', 'FAIL remains FAIL. This diagnostic is excluded from the passing benchmark corpus.'])
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines))
    return bool(report['analysis']['failed_runs'] or report['analysis']['independent_failures'])


if __name__ == '__main__':
    raise SystemExit(main())
