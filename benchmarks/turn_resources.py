"""Development-only Linux limit probe or separately labelled instrumented profile.

Set limits before importing NumPy or product code. Never imported by the product.
"""
import argparse
import cProfile
import json
import os
from pathlib import Path
import platform
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CPU_SECONDS = 20
ADDRESS_BYTES = 384*1024**2


def install_limits():
    if sys.platform != 'linux':
        raise RuntimeError('Linux RLIMIT_CPU/RLIMIT_AS required; no equivalent claim on this platform')
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_BYTES, ADDRESS_BYTES))
    return {'cpu_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'address_space_bytes': list(resource.getrlimit(resource.RLIMIT_AS))}


def linux_memory():
    if sys.platform != 'linux':
        return None
    fields = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        name, _, value = line.partition(':')
        if name in ('VmPeak', 'VmSize', 'VmHWM', 'VmRSS'):
            amount, unit = value.split()
            if unit != 'kB':
                raise ValueError('Unexpected /proc memory unit')
            fields[name+'_bytes'] = int(amount)*1024
    return {'method': '/proc/self/status; kB converted to bytes', **fields}


def hotspot_rows(profiler):
    rows = []
    for (filename, line, name), (primitive, calls, own, cumulative, _) in pstats.Stats(profiler).stats.items():
        path = Path(filename)
        label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        rows.append({'function': f'{label}:{line}:{name}', 'primitive_calls': primitive,
                     'total_calls': calls, 'self_seconds': own, 'cumulative_seconds': cumulative})
    return {key: sorted(rows, key=lambda row: row[key], reverse=True)[:20]
            for key in ('self_seconds', 'cumulative_seconds')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('limits', 'profile'), required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    stage = 'startup'

    def progress(value):
        nonlocal stage
        stage = value
        print(json.dumps({'stage': stage, 'worker_seconds': time.perf_counter()-started}), file=sys.stderr, flush=True)

    report = {'mode': args.mode, 'pid': os.getpid(), 'platform': platform.platform(),
              'python': platform.python_version(), 'limits': None}
    if args.mode == 'limits' and sys.platform != 'linux':
        print(json.dumps(dict(report, status='UNSUPPORTED', failure='Exact Linux resource limits unavailable')))
        return 0
    try:
        if args.mode == 'limits':
            report['limits'] = install_limits()
        progress('limits_installed' if args.mode == 'limits' else 'unlimited_instrumented_profile')
        request = json.load(sys.stdin)
        if type(request['iterations']) is not int or not 20 <= request['iterations'] <= 2000:
            raise ValueError('Development iterations must be in [20,2000]')
        sys.path.insert(0, str(ROOT))
        profiler = cProfile.Profile() if args.mode == 'profile' else None
        if profiler:
            profiler.enable()
        from benchmarks.turn_performance import measure
        progress('imports_complete')
        result = measure(request['config'], request['iterations'])
        if profiler:
            profiler.disable()
            report['hotspots'] = hotspot_rows(profiler)
        progress('calculation_complete')
        if sys.platform == 'linux':
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            report['whole_process_cpu_seconds'] = usage.ru_utime+usage.ru_stime
        report.update(status='COMPLETED', measurement=result, linux_memory=linux_memory(),
                      worker_wall_seconds=time.perf_counter()-started)
    except MemoryError:
        report.update(status='MEMORY_ERROR', failure='MemoryError; see recorded mode and limits', stage=stage)
    except Exception as error:
        report.update(status='ERROR', failure=f'{type(error).__name__}: {error}', stage=stage)
    print(json.dumps(report, allow_nan=False))
    return int(report['status'] == 'ERROR')


if __name__ == '__main__':
    raise SystemExit(main())
