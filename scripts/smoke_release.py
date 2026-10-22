"""Read-only exact-SHA smoke for a separately approved Poker Solver release.

No OAuth tokens, MCP calls, third-party provider requests or production writes.
"""
import argparse
from contextlib import nullcontext
import json
import re
from urllib.parse import urlsplit, urlunsplit

import httpx


class ReleaseSmokeError(ValueError):
    """A sanitized release verification failure; never include remote response data."""


def smoke_release(origin, expected_sha, client=None):
    if not isinstance(origin, str):
        raise ReleaseSmokeError('Specify an HTTPS service origin')
    try:
        parsed = urlsplit(origin)
        valid = (parsed.scheme == 'https' and parsed.hostname is not None
                 and not parsed.username and not parsed.password
                 and not parsed.path and not parsed.query and not parsed.fragment
                 and urlunsplit((parsed.scheme, parsed.netloc, '', '', '')) == origin)
    except ValueError:
        valid = False
    if not valid:
        raise ReleaseSmokeError('Specify an HTTPS origin without path, credentials, query or fragment')
    if not isinstance(expected_sha, str) or re.fullmatch(r'[0-9a-f]{40}', expected_sha) is None:
        raise ReleaseSmokeError('Expected commit must be a full lowercase 40-character SHA')

    owned = httpx.Client(timeout=60.0, follow_redirects=False) if client is None else nullcontext(client)
    with owned as session:
        def fetch(path):
            try:
                response = session.get(origin + path, follow_redirects=False,
                                       headers={'Accept': 'application/json'})
            except httpx.RequestError:
                raise ReleaseSmokeError('Release endpoint unavailable: ' + path) from None
            if response.is_redirect or len(response.content) > 16_384:
                raise ReleaseSmokeError('Unexpected redirect or oversized response: ' + path)
            return response

        health = fetch('/health')
        if health.status_code != 200:
            raise ReleaseSmokeError('Health endpoint not ready')
        try:
            status = health.json()
        except (ValueError, UnicodeDecodeError):
            raise ReleaseSmokeError('Health response is not JSON') from None
        if (not isinstance(status, dict) or status.get('status') != 'ok'
                or status.get('engine') != 'river-only'
                or status.get('auth_configured') is not True
                or not isinstance(status.get('deployment'), dict)
                or status['deployment'].get('commit') != expected_sha):
            raise ReleaseSmokeError('Health, authorization readiness, engine or deployed SHA mismatch')

        ready = fetch('/ready')
        if ready.status_code != 200:
            raise ReleaseSmokeError('Readiness endpoint not ready')
        try:
            ready_status = ready.json()
        except (ValueError, UnicodeDecodeError):
            raise ReleaseSmokeError('Readiness response is not JSON') from None
        if not isinstance(ready_status, dict) or ready_status.get('status') != 'ready':
            raise ReleaseSmokeError('Readiness response is not ready')

        unauth = fetch('/mcp')
        if (unauth.status_code != 401
                or 'resource_metadata=' not in unauth.headers.get('www-authenticate', '')):
            raise ReleaseSmokeError('Unauthenticated MCP authorization boundary changed')

    return {'commit': expected_sha, 'health': 200, 'ready': 200,
            'mcp_unauthenticated': 401, 'engine': 'river-only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origin', help='HTTPS service origin, without trailing slash')
    parser.add_argument('expected_sha', help='Full git commit SHA authorized for release')
    args = parser.parse_args()
    try:
        result = smoke_release(args.origin, args.expected_sha)
    except ReleaseSmokeError as exc:
        print('Release smoke failed: ' + str(exc))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
