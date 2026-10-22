"""Local post-session action-model sensitivity, with a disposable 60-second worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_json(path):
    with path.open('rb') as stream:
        data = stream.read(256*1024+1)
    if len(data) > 256*1024:
        raise ValueError('Each input file is limited to 256 KiB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON object key: '+key)
            result[key] = value
        return result
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique)


def execute(hand, models, timeout=60):
    request = json.dumps({'hand': hand, 'models': models}, allow_nan=False)
    if len(request.encode()) > 512*1024:
        raise ValueError('Combined worker request exceeds 512 KiB')
    env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'VIRTUAL_ENV'}}
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    started = time.perf_counter()
    try:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'], input=request,
                               capture_output=True, text=True, timeout=timeout, cwd=ROOT, env=env)
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'solver_execution': 'not_run', 'error': {'code': 'TIMEOUT', 'message': 'Range conditioning exceeded local wall deadline'}}
    if child.returncode:
        return {'status': 'failed', 'solver_execution': 'not_run', 'error': {'code': 'WORKER_FAILED', 'message': 'Local range worker failed'}}
    try:
        result = json.loads(child.stdout)
    except ValueError:
        return {'status': 'failed', 'solver_execution': 'not_run', 'error': {'code': 'INVALID_OUTPUT', 'message': 'Invalid worker JSON'}}
    result['parent_wall_seconds'] = time.perf_counter()-started
    return result


def worker():
    from poker_spot.range_explorer import explore

    try:
        request = sys.stdin.read(512*1024+1)
        if len(request.encode()) > 512*1024:
            raise ValueError('Worker input exceeds 512 KiB')
        data = json.loads(request)
        if not isinstance(data, dict) or set(data) != {'hand', 'models'}:
            raise ValueError('Worker requires hand and models')
        started, cpu = time.perf_counter(), time.process_time()
        result = explore(data['hand'], data['models'])
        sources = ['poker_spot/range_explorer.py', 'poker_spot/history.py', 'poker_spot/core.py', 'poker_spot/review.py', 'scripts/explore_ranges.py']
        result['source_sha256_lf'] = {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sources}
        result['worker_metrics'] = {'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu,
                                    'wall_deadline_seconds': 60, 'python': sys.version, 'platform': platform.platform()}
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        result = {'status': 'not_run', 'solver_execution': 'not_run', 'error': {'code': 'INVALID_INPUT', 'message': str(error)}}
    print(json.dumps(result, allow_nan=False))


def main():
    from poker_spot.history import revise_hand
    from poker_spot.range_explorer import render_markdown

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hand', type=Path)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--set', action='append', default=[], metavar='POINTER=JSON', help='Edit an existing model-document field')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        hand, models = read_json(args.hand), read_json(args.models)
        for change in args.set:
            pointer, separator, value = change.partition('=')
            if not separator:
                raise ValueError('Correction requires POINTER=JSON')
            models = revise_hand(models, pointer, json.loads(value))
        result = execute(hand, models)
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        result = {'status': 'not_run', 'solver_execution': 'not_run', 'error': {'code': 'INVALID_INPUT', 'message': str(error)}}
    encoded = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.json').write_text(encoded, encoding='utf-8')
        notes = render_markdown(result) if 'profiles' in result else (
            '# Post-session range exploration\n\nStatus: '+result['status']+'. Solver execution: not run.\n\n'+
            result.get('error', {}).get('message', '')+'\n')
        args.output.with_suffix('.md').write_text(notes, encoding='utf-8')
    else:
        print(encoded, end='')
    return 0 if result['status'] == 'computed' else 2 if result['status'] in ('not_run', 'impossible_observation') else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['--worker']:
        worker()
    else:
        raise SystemExit(main())
