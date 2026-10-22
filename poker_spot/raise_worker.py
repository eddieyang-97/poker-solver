"""Disposable local study worker. No MCP entry point or operator credentials."""
import json
import hashlib
import platform
import sys
import time


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def accepted_configuration(solver, iterations=2000, oop_hand=None, ip_hand=None):
    """Receipt from the instantiated game and solve arguments, not request text.

    Ordered combos and binary64 hex weights preserve the actual trainer inputs,
    including pre-normalization arrival weights and card removal. No policy or
    execution authenticity is implied by this deterministic integrity receipt.
    """
    from .core import cards, combo_key

    ranges = {}
    for side, hands, raw, weights in (('oop', solver.h0, solver.r0, solver.w0),
                                      ('ip', solver.h1, solver.r1, solver.w1)):
        ranges[side] = [{'combo': list(h), 'arrival_weight_hex': float(raw[h]).hex(),
                         'training_weight_hex': float(w).hex()} for h, w in zip(hands, weights, strict=True)]
    return {'version': 1, 'context': 'post_session', 'board': list(solver.board),
            'pot_cents': solver.pot_cents, 'stack_cents': solver.stack_cents,
            'minimum_bet_cents': solver.minimum_cents, 'ranges': ranges, 'iterations': iterations,
            'query_hands': {side: list(combo_key(*cards(hand, 2))) if hand is not None else None
                            for side, hand in (('oop', oop_hand), ('ip', ip_hand))},
            'sizing_mode': 'exact_integer_cents' if solver.exact_sizing else 'fractional',
            'bet_amounts_cents': list(solver.bet_cents),
            'bet_sizes': None if solver.exact_sizing else list(solver.sizes),
            'raise_to_cents': list(solver.raise_to_cents) if solver.exact_sizing else None,
            'raise_sizes': solver.raise_sizes}


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
    accepted = accepted_configuration(solver, **solve_args)
    encoded = json.dumps(result, allow_nan=False).encode()
    return {'status': 'computed', 'result': result,
            'receipt': {'configuration': accepted, 'configuration_sha256': canonical_digest(accepted),
                        'result_sha256': canonical_digest(result)},
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
