"""One calculation per disposable process. No network or credentials required."""
import json
import sys

from .validation import calculate


def main():
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
    try:
        request = json.load(sys.stdin)
        result = calculate(request['name'], request['arguments'])
        json.dump({'result': result}, sys.stdout, allow_nan=False)
    except (ValueError, TypeError, KeyError):
        json.dump({'error': 'Invalid or inconsistent river inputs'}, sys.stdout)


if __name__ == '__main__':
    main()
