"""Disposable development probe, Linux limits precede numerical/product imports."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.turn_resources import install_limits, linux_memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unlimited', action='store_true', help='Explicit local experiment; never budget acceptance')
    parser.add_argument('--lookup', action='store_true', help='Read a trusted local experiment artifact, without training')
    args = parser.parse_args()
    started = time.perf_counter()
    stages = {}

    def mark(name):
        stages[name] = time.perf_counter()-started
        print(json.dumps({'stage': name, 'worker_seconds': stages[name]}), file=sys.stderr, flush=True)

    report = {'status': 'ERROR', 'limits': None, 'stages': stages, 'platform': platform.platform(),
              'python': platform.python_version(), 'mode': 'unlimited' if args.unlimited else 'linux_limits'}
    if not args.unlimited and sys.platform != 'linux':
        print(json.dumps(dict(report, status='UNSUPPORTED')))
        return 0
    try:
        if not args.unlimited:
            report['limits'] = install_limits()
        mark('limits_installed')
        request = json.load(sys.stdin)
        mark('parsed')
        from poker_spot.turn import TurnSolver
        from benchmarks.turn_performance import peak_resident_memory
        from benchmarks.turn_feasibility import candidate_input, digest, full_record, pack, unpack, view
        mark('imports_complete')
        solver = TurnSolver(**request['config'])
        report['candidate_input'] = candidate_input(solver, request['iterations'])
        mark('constructed')
        if args.lookup:
            samples = []
            for _ in range(3):
                tick = time.perf_counter()
                record = unpack(Path(request['artifact']).read_bytes(), request['sha256'], solver, request['iterations'])
                decoded = time.perf_counter()
                views = [view(record, solver, **query) for query in request['views']]
                payload = json.dumps(views, allow_nan=False).encode()
                samples.append({'read_verify_decode_seconds': decoded-tick,
                                'projection_and_json_seconds': time.perf_counter()-decoded,
                                'view_bytes': len(payload), 'view_sha256': digest(views)})
            report.update(status='COMPLETED', lookups=samples, key=record['key'], diagnostics=record['diagnostics'])
            mark('lookups_complete')
            report['linux_memory'] = linux_memory()
            report['peak_resident_memory'] = peak_resident_memory()
            report['worker_cpu_through_snapshot_seconds'] = time.process_time()
            print(json.dumps(report, allow_nan=False))
            return 0
        result = solver.solve(request['iterations'])
        mark('trained_and_diagnosed')
        record = full_record(solver, result)
        mark('full_policy_and_evs_collected')
        blob = pack(record)
        destination = Path(request['artifact'])
        destination.write_bytes(blob)
        report.update(status='COMPLETED', artifact_sha256=hashlib.sha256(blob).hexdigest(),
                      artifact_bytes=len(blob), full_json_bytes=len(json.dumps(record).encode()),
                      key=record['key'], diagnostics=record['diagnostics'])
        mark('serialized_compressed_written')
        report['linux_memory'] = linux_memory()
        report['peak_resident_memory'] = peak_resident_memory()
        report['worker_cpu_through_snapshot_seconds'] = time.process_time()
        # CPU covers startup through this snapshot; parent wall also includes final output/reap.
    except MemoryError:
        report.update(status='MEMORY_ERROR', failure='MemoryError under recorded mode/limits')
    except Exception as error:
        report.update(status='ERROR', failure=f'{type(error).__name__}: {error}')
    print(json.dumps(report, allow_nan=False))
    return int(report['status'] == 'ERROR')


if __name__ == '__main__':
    raise SystemExit(main())
