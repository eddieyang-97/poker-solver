"""Local-only post-session raise solver, with a disposable 60-second worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def execute(config, timeout=60):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'VIRTUAL_ENV'}}
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    try:
        child = subprocess.run([sys.executable, '-m', 'poker_spot.raise_worker'], cwd=ROOT,
                               input=json.dumps(config), text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'error': {'code': 'TIMEOUT', 'message': 'Local worker wall deadline exceeded'}}
    if child.returncode:
        return {'status': 'failed', 'error': {'code': 'WORKER_FAILED', 'message': 'Local worker resource limit or internal error'}}
    try:
        return json.loads(child.stdout)
    except ValueError:
        return {'status': 'failed', 'error': {'code': 'INVALID_OUTPUT', 'message': 'Worker returned no valid JSON'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        text = args.scenario.read_text(encoding='utf-8-sig')
        if len(text) > 65536:
            raise ValueError('Local input exceeds 65,536 characters')
        result = execute(json.loads(text))
    except (ValueError, OSError) as error:
        result = {'status': 'not_run', 'error': {'code': 'INVALID_INPUT', 'message': str(error)}}
    encoded = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    else:
        print(encoded, end='')
    return 0 if result['status'] == 'computed' else 2 if result['status'] == 'not_run' else 1


if __name__ == '__main__':
    raise SystemExit(main())
