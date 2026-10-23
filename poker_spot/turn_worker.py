"""Direct isolated-script entry: kernel limits precede package/NumPy imports."""
import json
from pathlib import Path
import sys
import time


def main():
    started = time.monotonic()
    limits = None
    if sys.platform == 'linux':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (384*1024**2, 384*1024**2))
        limits = {'cpu_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
                  'address_space_bytes': list(resource.getrlimit(resource.RLIMIT_AS))}
    elif sys.platform != 'win32':
        print(json.dumps({'error': {'code': 'unsupported', 'message': 'Linux limits unavailable'}}))
        return
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from poker_spot.turn_pilot import MAX_RESULT_BYTES, calculate
        imported = time.monotonic()
        request = sys.stdin.buffer.read(16_385)
        if len(request) > 16_384:
            raise ValueError('Request exceeds body budget')
        arguments = json.loads(request)
        parsed = time.monotonic()
        result = calculate(arguments)
        solved = time.monotonic()
        # Include encoding cost in the measured path; final envelope is also capped.
        encoded = json.dumps(result, allow_nan=False)
        serialized = time.monotonic()
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError('Result exceeds worker output budget')
        measurement = {'platform': sys.platform, 'limits': limits,
                       'worker_wall_seconds': time.monotonic()-started,
                       'budget_enforced': limits is not None,
                       'stage_seconds': {'bootstrap_imports': imported-started, 'read_parse': parsed-imported,
                                         'validate_solve_br_project_receipt': solved-parsed,
                                         'result_serialization': serialized-solved}}
        if sys.platform == 'linux':
            usage = resource.getrusage(resource.RUSAGE_SELF)
            measurement['worker_cpu_seconds'] = usage.ru_utime+usage.ru_stime
            measurement['memory_bytes'] = {k: int(v.split()[0])*1024 for line in Path('/proc/self/status').read_text().splitlines()
                                           for k, _, v in [line.partition(':')] if k in ('VmPeak', 'VmHWM')}
        response = json.dumps({'result': result, 'measurement': measurement}, allow_nan=False)
        if len(response.encode()) > MAX_RESULT_BYTES+2048:
            raise ValueError('Response exceeds worker output budget')
        print(response)
    except MemoryError:
        print(json.dumps({'error': {'code': 'resource_limit', 'message': 'Worker address-space limit reached'}}))
    except (ValueError, TypeError, KeyError):
        print(json.dumps({'error': {'code': 'invalid_input', 'message': 'Invalid or unsupported turn pilot inputs'}}))


if __name__ == '__main__':
    main()
