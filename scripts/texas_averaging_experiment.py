"""Prepare/run the isolated reference experiment, never the production service."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.texas_experiment import prepare, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.source, args.prepared)
    else:
        if not args.build or not args.output:
            parser.error('run requires --build and --output')
        run(args.source, args.prepared, args.build, args.output)


if __name__ == '__main__':
    main()
