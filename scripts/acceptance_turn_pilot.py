"""Authenticated hosted SDK acceptance; this is NOT a ChatGPT invocation.

Use an OAuth access token in POKER_ACCEPTANCE_TOKEN, never a command argument.
The receipt is a consistency check, not signed execution attestation. Full SDK
results and requests are retained; credentials and exception text are not.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from time import monotonic
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from poker_spot.turn_pilot import (MAX_GAP_PCT, MAX_RESULT_BYTES, NAME, SOURCE_FILES,
                                   VERSION, _cent_tree, digest, prepare, validated_solver)

ROOT = Path(__file__).resolve().parents[1]
MAX_SDK_BYTES = 65_536  # Engineering bound, not a published ChatGPT byte limit.
ALGORITHM = 'Alternating CFR+, linear own-reach averaging, exact river enumeration'
TOOLS = {'solve_river', 'evaluate_river_call', NAME}


class ReceiptError(ValueError):
    """Controlled diagnostic; never include a remote response or credential."""


def require(condition, message):
    if not condition:
        raise ReceiptError(message)


def source_hashes(root=ROOT):
    return {name: hashlib.sha256((root/'poker_spot'/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in SOURCE_FILES}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_turn_result(request, result, *, expected_sources, is_error, sdk_bytes=None):
    """Validate a raw structured result, including a future ChatGPT capture.

    Expected sources must come from the pinned release checkout. Python/NumPy
    are disclosed and hashed as reported, never assumed equal across platforms.
    """
    try:
        args = prepare(request)
        tree = validated_solver(args)
        game = {k: v for k, v in args.items() if k != 'views'}
        require(result['schema_version'] == VERSION and result['source'] == 'computed_on_demand',
                'Unexpected computation identity')
        require(result['game'] == game and result['request_sha256'] == digest(args), 'Request receipt mismatch')
        identity = result['provenance']
        require(identity['schema'] == VERSION and identity['game'] == game
                and identity['sources_sha256_lf'] == expected_sources
                and identity['algorithm'] == ALGORITHM
                and all(isinstance(identity[k], str) and identity[k] for k in ('python', 'numpy')),
                'Source or runtime provenance mismatch')
        require(result['game_identity_sha256'] == digest(identity), 'Game identity digest mismatch')
        solution = {k: v for k, v in result.items() if k not in ('result_sha256', 'execution')}
        require(result['result_sha256'] == digest(solution), 'Result digest mismatch')
        require(len(json.dumps({**solution, 'result_sha256': result['result_sha256']},
                               allow_nan=False).encode()) <= MAX_RESULT_BYTES, 'Solution exceeds bound')
        if sdk_bytes is not None:
            require(type(sdk_bytes) is int and 0 < sdk_bytes <= MAX_SDK_BYTES, 'SDK output exceeds bound')
        require(result['chance'] == {'enumerated_public_rivers': 48, 'legal_rivers_per_compatible_deal': 44},
                'Chance model mismatch')
        expected_bets = {path: [c/100 for c in amounts] for path, amounts in _cent_tree(args).items()}
        require(result['effective_bets_by_public_history'] == expected_bets, 'Exact-cent tree mismatch')
        require(result['ev_baseline'] == 'Half of the initial turn pot; cumulative turn and river contributions included',
                'EV baseline mismatch')
        d = result['diagnostics']
        require(d['iterations'] == 2000 and result['checkpoints'][-1] == d, 'Iteration/checkpoint mismatch')
        require(all(finite(v) for row in result['checkpoints'] for v in row.values()), 'Nonfinite diagnostics')
        gap = d['raw_nash_conv_chips']
        require(abs(d['zero_sum_residual'] - (d['oop_ev']+d['ip_ev'])) <= 1e-8
                and math.isclose(d['nash_conv_pct_pot'], max(0, gap)/(args['pot_cents']/100)*100,
                                 rel_tol=1e-12, abs_tol=1e-12), 'Inconsistent convergence diagnostics')
        bounds = result['best_response_bounds']
        require(all(finite(v) for v in bounds.values())
                and abs(bounds['raw_nash_conv_chips']-gap) <= 1e-8
                and abs(bounds['oop_best_response_ev']+bounds['ip_best_response_ev']-gap) <= 1e-8,
                'Best-response receipt mismatch')
        converged = abs(d['zero_sum_residual']) <= 1e-8 and gap >= -1e-8 and d['nash_conv_pct_pot'] <= MAX_GAP_PCT
        require(result['status'] == ('computed' if converged else 'insufficient_convergence')
                and is_error is (not converged), 'Convergence/error boundary mismatch')
        rows = result['views']
        require(len(rows) == (len(args['views']) if converged else 0), 'Unexpected strategy disclosure')
        for view, row in zip(args['views'], rows):
            require(all(row[k] == v for k, v in view.items()), 'View identity mismatch')
            freq, ev = row['frequency'], row['action_ev_relative_to_half_turn_pot']
            require(set(freq) == set(ev) == set(tree.nodes[view['node']].actions)
                    and all(finite(v) and 0 <= v <= 1 for v in freq.values())
                    and abs(sum(freq.values())-1) <= 1e-8, 'Invalid strategy frequencies')
            require(all(finite(row[k]) and row[k] >= 0 for k in
                        ('own_reach_given_hand', 'compatible_opponent_reach', 'chance_reach', 'reach_probability_given_hand')),
                    'Invalid reach receipt')
            require(all((v is None if row['compatible_opponent_reach'] == 0 else finite(v)) for v in ev.values()),
                    'Conditional action EV/reach mismatch')
        m = result['execution']
        require(m['platform'] == 'linux' and m['budget_enforced'] is True
                and m['limits'] == {'cpu_seconds': [20, 20], 'address_space_bytes': [384*1024**2]*2},
                'Hosted Linux limits not established')
        require(all(finite(m[k]) and 0 <= m[k] <= 20 for k in
                    ('parent_wall_seconds', 'worker_wall_seconds', 'worker_cpu_seconds'))
                and all(type(m['memory_bytes'][k]) is int and 0 < m['memory_bytes'][k] <= 384*1024**2
                        for k in ('VmPeak', 'VmHWM')), 'Hosted resource budget exceeded')
        require(set(m['stage_seconds']) == {'bootstrap_imports', 'read_parse', 'validate_solve_br_project_receipt',
                                          'result_serialization'}
                and all(finite(v) and v >= 0 for v in m['stage_seconds'].values())
                and sum(m['stage_seconds'].values()) <= m['worker_wall_seconds']+1e-6
                and m['worker_wall_seconds'] <= m['parent_wall_seconds']
                and m['memory_bytes']['VmHWM'] <= m['memory_bytes']['VmPeak'], 'Inconsistent stage/resource timings')
        return {'status': result['status'], 'request_sha256': result['request_sha256'],
                'result_sha256': result['result_sha256'], 'game_identity_sha256': result['game_identity_sha256'],
                'observed_headroom': m['parent_wall_seconds'] <= 10 and m['worker_cpu_seconds'] <= 10
                    and m['memory_bytes']['VmPeak'] <= 192*1024**2}
    except (KeyError, TypeError, IndexError, ValueError, OverflowError) as error:
        if isinstance(error, ReceiptError):
            raise
        raise ReceiptError('Malformed receipt or request') from None


async def collect(session, request, expected_sources, repeats=2):
    """Session injection keeps acceptance logic testable without live network/auth."""
    report = {'mode': 'hosted SDK, not ChatGPT', 'cases': [], 'failures': [],
              'limitations': ['Repeated calls do not independently establish a cold idle wakeup.',
                              'No refresh/revocation/second-account or actual ChatGPT acceptance.',
                              'No admitted 2000-iteration nonconvergence or timeout is fabricated.']}
    try:
        listed = await session.list_tools()
        tools = [tool.model_dump(mode='json', by_alias=True) for tool in listed.tools]
        report['tools'] = tools
        require({tool['name'] for tool in tools} == TOOLS and len(tools) == len(TOOLS), 'Unexpected tool list')
        schemes = [{'type': 'oauth2', 'scopes': ['poker:solve']}]
        require(all(tool.get('securitySchemes') == schemes and
                    tool.get('_meta', {}).get('securitySchemes') == schemes for tool in tools),
                'Tool permissions changed')
    except Exception:
        report['failures'].append('Tool discovery or permission check failed')
        return report

    async def call(label, name, arguments):
        row = {'id': label, 'tool': name, 'request': deepcopy(arguments)}
        report['cases'].append(row)
        try:
            started = monotonic()
            response = await session.call_tool(name, arguments)
            row.update(client_wall_seconds=monotonic()-started,
                       raw_sdk_result=response.model_dump(mode='json', by_alias=True),
                       sdk_result_bytes=len(response.model_dump_json(by_alias=True).encode()))
            require(row['sdk_result_bytes'] <= MAX_SDK_BYTES, 'SDK output exceeds bound')
            return response, row
        except Exception:
            row['failure'] = 'SDK call failed; exception details suppressed'
            report['failures'].append(label+': SDK call failed')
            return None, row

    for repeat in range(repeats):
        response, row = await call('turn_example_'+str(repeat+1), NAME, request)
        if response is not None:
            try:
                require(len(response.content) == 1 and response.content[0].type == 'text'
                        and json.loads(response.content[0].text) == response.structuredContent,
                        'Text/structured result mismatch')
                row['receipt'] = validate_turn_result(request, response.structuredContent,
                    expected_sources=expected_sources, is_error=response.isError, sdk_bytes=row['sdk_result_bytes'])
                require(row['receipt']['status'] == 'computed' and row['receipt']['observed_headroom'],
                        'Example convergence or conservative headroom failed')
            except ReceiptError as error:
                # ReceiptError messages are our fixed diagnostics, never remote text.
                row['receipt_failure'] = str(error)
                report['failures'].append(row['id']+': '+str(error))
            except (ValueError, TypeError, AttributeError):
                report['failures'].append(row['id']+': malformed SDK result')
    bad = dict(request, iterations=1999)
    response, _ = await call('unsupported_iterations', NAME, bad)
    if response is not None and not (response.isError and isinstance(response.structuredContent, dict)
                                    and response.structuredContent.get('error', {}).get('code') == 'invalid_input'):
        report['failures'].append('Unsupported request was not rejected as invalid_input')
    legacy = [
        ('river_call', 'evaluate_river_call', {'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd',
            'villain_betting_range': 'AsJs,AsJh:0.5', 'pot': 100, 'bet': 100}),
        ('river_solve', 'solve_river', {'board': '2c,3d,4h,8s,9c', 'oop_range': 'KhKd',
            'ip_range': 'AsAd,QhJd', 'pot': 100, 'stack': 100, 'bet_sizes': [1.0], 'iterations': 1500,
            'ip_hand': 'QhJd', 'oop_hand': 'KhKd'})]
    for label, name, arguments in legacy:
        response, _ = await call(label, name, arguments)
        if response is not None:
            data = response.structuredContent or {}
            passed = (data.get('best_action_given_range') == 'indifferent' if label == 'river_call'
                      else finite(data.get('nash_conv_pct_pot')) and data['nash_conv_pct_pot'] < 0.5)
            if response.isError or not passed:
                report['failures'].append(label+': legacy smoke regression failed')
    return report


async def hosted(url, token, expected_sha, request, expected_sources):
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and parsed.path == '/mcp'
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            'Use a plain HTTPS /mcp endpoint')
    require(bool(re.fullmatch('[0-9a-f]{40}', expected_sha)), 'A full expected deployed SHA is required')
    async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
        base = url.rsplit('/mcp', 1)[0]
        health = await client.get(base+'/health')
        ready = await client.get(base+'/ready')
        require(health.status_code == ready.status_code == 200, 'Public release probes failed')
        require(health.json().get('deployment', {}).get('commit') == expected_sha
                and health.json().get('engine') == 'turn-pilot-v1'
                and health.json().get('auth_configured') is True
                and ready.json().get('status') == 'ready', 'Deployed release identity mismatch')
        client.headers['Authorization'] = 'Bearer '+token
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                report = await collect(session, request, expected_sources)
                report.update(expected_deployed_sha=expected_sha, public_health=health.json(),
                              public_ready=ready.json(), initialized=initialized.model_dump(mode='json', by_alias=True))
                return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT, help='Pinned release checkout for LF source hashes')
    parser.add_argument('--request', type=Path, default=ROOT/'examples/turn-pilot.json')
    parser.add_argument('--output', type=Path, default=ROOT/'.artifacts/turn-pilot-hosted-sdk.json')
    args = parser.parse_args()
    token = os.environ.get('POKER_ACCEPTANCE_TOKEN', '')
    try:
        require(bool(token) and token.strip() == token, 'Set POKER_ACCEPTANCE_TOKEN to an OAuth access token')
        report = asyncio.run(hosted(args.url, token, args.expected_sha,
            json.loads(args.request.read_text(encoding='utf-8')), source_hashes(args.source_root)))
        encoded = json.dumps(report, indent=2, allow_nan=False)+'\n'
        require(token not in encoded, 'Credential-like response discarded')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    except ReceiptError as error:
        print('Hosted SDK acceptance failed: '+str(error)+'. No receipt written.')
        return 1
    except Exception:
        print('Hosted SDK acceptance failed; response/exception details suppressed. No receipt written.')
        return 1
    print(f"Hosted SDK, not ChatGPT: {len(report['cases'])} calls; {len(report['failures'])} failures. Receipt: {args.output}")
    return int(bool(report['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
