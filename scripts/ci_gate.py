"""Fail-closed aggregate for the existing required GitHub Actions `test` check."""
import json
import os
import sys

REQUIRED_JOBS = ('river', 'turn', 'decomposition', 'resources')


def require_success(needs):
    if not isinstance(needs, dict) or set(needs) != set(REQUIRED_JOBS):
        raise ValueError('Required job set is missing or unexpected')
    failed = [name for name in REQUIRED_JOBS
              if not isinstance(needs[name], dict) or needs[name].get('result') != 'success']
    if failed:
        raise ValueError('Required jobs did not succeed: '+', '.join(failed))


def main():
    try:
        require_success(json.loads(os.environ.get('NEEDS_JSON', 'null')))
    except (ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print('All required solver, resource, replay and artifact gates succeeded.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
