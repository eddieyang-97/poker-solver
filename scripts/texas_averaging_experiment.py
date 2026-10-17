"""Prepare/run the isolated reference experiment, never the production service."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.texas_experiment import analyze, markdown, prepare, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'replay'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'replay':
        if not args.evidence or not args.output:
            parser.error('replay requires --evidence and --output')
        report = json.loads(args.evidence.read_text(encoding='utf-8'))
        report['analysis'] = analyze(report['execution'])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        args.output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
        print(json.dumps(report['analysis'], indent=2))
        return
    if not args.source or not args.prepared:
        parser.error('prepare/run requires --source and --prepared')
    if args.mode == 'prepare':
        prepare(args.source, args.prepared)
    else:
        if not args.build or not args.output:
            parser.error('run requires --build and --output')
        run(args.source, args.prepared, args.build, args.output)


if __name__ == '__main__':
    main()
