"""Disposable local study worker. No MCP entry point or operator credentials."""
import json
import platform
import sys
import time


def peak_rss():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD),
                        *[(k, ctypes.c_size_t) for k in ('peak', 'working', 'pool_peak', 'pool', 'nonpool_peak', 'nonpool', 'page', 'page_peak')]]

        kernel, psapi = ctypes.WinDLL('kernel32'), ctypes.WinDLL('psapi')
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        count = Counters()
        count.cb = ctypes.sizeof(count)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(count), count.cb):
            raise OSError('Cannot measure peak resident memory')
        return {'bytes': count.peak, 'method': 'Windows PeakWorkingSetSize'}
    import resource
    return {'bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == 'darwin' else 1024),
            'method': 'getrusage ru_maxrss, platform units converted'}


def run(config):
    started, cpu = time.perf_counter(), time.process_time()
    limits = {'wall_seconds': 60, 'cpu_seconds': None, 'address_space_bytes': None}
    if sys.platform == 'linux':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (384*1024**2,)*2)
        limits.update(cpu_seconds=60, address_space_bytes=384*1024**2)
    from .raises import RaiseRiverSolver

    if not isinstance(config, dict) or config.get('context') != 'post_session':
        raise ValueError('Explicit context: post_session is required')
    config = config.copy()
    config.pop('context')
    solve_args = {k: config.pop(k) for k in ('iterations', 'oop_hand', 'ip_hand') if k in config}
    solver = RaiseRiverSolver(**config)
    initialized = time.perf_counter()
    result = solver.solve(**solve_args)
    encoded = json.dumps(result, allow_nan=False).encode()
    return {'status': 'computed', 'result': result,
            'metrics': {'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu,
                        'initialization_seconds': initialized-started, 'peak_resident_memory': peak_rss(),
                        'output_bytes': len(encoded), 'nodes': len(solver.nodes), 'limits': limits,
                        'platform': platform.platform(), 'python': platform.python_version()}}


if __name__ == '__main__':
    try:
        text = sys.stdin.read(65537)
        if len(text) > 65536:
            raise ValueError('Local request exceeds 65,536 characters')
        response = run(json.loads(text))
    except (ValueError, TypeError, KeyError) as error:
        response = {'status': 'not_run', 'error': {'code': 'INVALID_INPUT', 'message': str(error)}}
    print(json.dumps(response, allow_nan=False))
