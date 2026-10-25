"""Fresh-process local reuse probe; reuse #21's pre-import Linux limits."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.turn_resources import install_limits, linux_memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unlimited', action='store_true')
    args = parser.parse_args()
    started = time.perf_counter()
    if not args.unlimited and sys.platform != 'linux':
        raise RuntimeError('Linux limits unavailable; select explicit --unlimited')
    limits = None if args.unlimited else install_limits()
    request = json.load(sys.stdin)
    from scripts.benchmark_turn_reuse import compare_target, timed
    from benchmarks.turn_performance import peak_resident_memory
    imported = time.perf_counter()-started
    samples = []
    for _ in range(3):
        data, elapsed = timed(lambda: compare_target(request['case'], request['entry'], Path(request['raw_dir'])))
        samples.append(dict(elapsed, evaluation=data[-1]))
    result = {'mode': 'unlimited_local' if args.unlimited else 'linux_limits_not_hosted',
              'limits': limits, 'imports_parse_seconds': imported, 'samples': samples,
              'worker_wall_through_snapshot_seconds': time.perf_counter()-started,
              'cpu_through_snapshot_seconds': time.process_time(), 'linux_memory': linux_memory(),
              'peak_resident_memory': peak_resident_memory()}
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
