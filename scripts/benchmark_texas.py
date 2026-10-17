"""Run an opt-in TexasSolver pilot, or replay saved evidence without its binary."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.texas import analyze, load_fixture, run_external


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--binary', type=Path)
    source.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/texas'))
    args = parser.parse_args()
    evidence = (run_external(args.binary, load_fixture()) if args.binary
                else json.loads(args.evidence.read_text())['execution'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve external output even if validation reveals an incompatibility.
    args.output.with_suffix('.execution.json').write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    report = {'mode': 'actual external execution' if args.binary else 'offline evidence replay; no Texas binary executed',
              'execution': evidence}
    try:
        report['analysis'] = analyze(evidence)
    except Exception as exc:
        report['analysis'] = {'failures': [f'{type(exc).__name__}: {exc}']}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    result = report['analysis']
    print(json.dumps({k: v for k, v in result.items() if k not in ('comparison', 'texas_nodes')}, indent=2))
    return bool(result['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
