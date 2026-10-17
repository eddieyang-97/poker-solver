"""Standalone local performance worker; never imported by product code."""
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from poker_spot.turn import TurnSolver


def peak_resident_memory():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in (
                            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'bytes': counters.PeakWorkingSetSize, 'method': 'Windows PeakWorkingSetSize'}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'bytes': value*(1 if sys.platform == 'darwin' else 1024),
            'method': 'getrusage(RUSAGE_SELF).ru_maxrss; platform units converted to bytes'}


def measure(config, iterations):
    started, cpu_started = time.perf_counter(), time.process_time()
    solver = TurnSolver(**config)
    initialization_seconds = time.perf_counter()-started
    trained = time.perf_counter()
    # Include the largest supported output context: both hands and all rivers.
    result = solver.solve(iterations, ''.join(solver.hands[0][0]), ''.join(solver.hands[1][0]))
    solve_seconds = time.perf_counter()-trained
    rendered = time.perf_counter()
    output_bytes = len(json.dumps(result, allow_nan=False).encode('utf-8'))
    serialization_seconds = time.perf_counter()-rendered
    return {'iterations': iterations, 'range_combos': result['range_combos'],
            'decision_node_templates': len(solver.nodes),
            'river_decision_templates': sum(node.street == 1 for node in solver.nodes.values()),
            'public_rivers': len(solver.rivers), 'effective_bets': solver.effective_bets,
            'initialization_seconds': initialization_seconds, 'solve_and_query_seconds': solve_seconds,
            'serialization_seconds': serialization_seconds, 'total_seconds': time.perf_counter()-started,
            'cpu_seconds': time.process_time()-cpu_started, 'peak_resident_memory': peak_resident_memory(),
            'output_bytes': output_bytes, 'diagnostics': result['diagnostics'],
            'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform(),
            'processor': platform.processor(), 'pid': os.getpid(),
            'blas_threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}}


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(measure(request['config'], request['iterations']), allow_nan=False))
