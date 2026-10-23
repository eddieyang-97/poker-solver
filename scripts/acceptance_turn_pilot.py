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
from itertools import product
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
MAX_WARM_CLIENT_SECONDS = 15.0  # 10s server headroom + 5s transport/SDK allowance.
RIVER_FREQUENCY_TOLERANCE = 0.04  # Existing independently checked polarized-fixture gate.
RIVER_ROUNDING = 0.00005  # River output rounds EVs/frequencies to four decimals.
LEGACY_BASELINE = ROOT/'docs/turn-pilot-stage-b-baseline.json'


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


def legacy_baselines():
    """Exact recorded requests, not the earlier unrecorded indifference request."""
    rows = json.loads(LEGACY_BASELINE.read_text(encoding='utf-8'))['legacy_chatgpt_connector_calls']
    require(len(rows) == 2 and {r['tool'] for r in rows} == {'solve_river', 'evaluate_river_call'},
            'Legacy baseline fixture mismatch')
    return rows


def _river_schema(actual, expected):
    """Require the complete pinned response shape and finite numeric leaves."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), 'Legacy response schema mismatch')
        for key in expected:
            _river_schema(actual[key], expected[key])
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), 'Legacy response list mismatch')
        for value, baseline in zip(actual, expected):
            _river_schema(value, baseline)
    elif finite(expected):
        require(finite(actual), 'Legacy response contains a nonfinite or nonnumeric quantity')
    else:
        require(type(actual) is type(expected) and actual == expected, 'Legacy response identity mismatch')


def validate_legacy_result(name, request, data):
    """Pinned singleton-KK / equal AA,QJ game; not a generic conditional-EV gate.

    Complete schemas/identities are fixed. Call quantities are deterministic.
    River frequencies retain the existing analytical 0.04 gate; value comparisons
    use root gap bounds, while conditional EVs use rounded-policy chip accounting.
    """
    baseline = next(row for row in legacy_baselines() if row['tool'] == name)
    require(request == baseline['request'], 'Legacy request is not comparable to the pinned baseline')
    expected = baseline['response']['structuredContent']
    _river_schema(data, expected)
    if name == 'evaluate_river_call':
        require(data == expected, 'Deterministic river call quantities changed')
        return
    for key in ('pot', 'stack', 'bet_sizes', 'iterations', 'range_combos', 'effective_bet_amounts'):
        require(data[key] == expected[key], 'River game or tree identity changed')
    pot, bet = data['pot'], data['effective_bet_amounts'][0]
    gap = data['nash_conv_chips']
    eps, unit = 1e-9, RIVER_ROUNDING
    require(gap >= 0 and 0 <= data['nash_conv_pct_pot'] < 0.5
            and abs(data['nash_conv_pct_pot']-gap/pot*100) <= 0.0005+unit/pot*100+eps,
            'River convergence quantities disagree')
    value = data['root_ev_oop_relative_to_split_pot']
    require(abs(value-expected['root_ev_oop_relative_to_split_pot'])
            <= gap+expected['nash_conv_chips']+2*unit+eps
            and abs(value+pot/4) <= gap+unit+eps, 'River root EV disagrees with baseline/analytical bound')
    for side in ('oop', 'ip'):
        for node, row in data['hands'][side]['node_strategy'].items():
            old = expected['hands'][side]['node_strategy'][node]
            frequencies = row['frequency']
            require(all(0 <= v <= 1 and abs(v-old['frequency'][a]) <= RIVER_FREQUENCY_TOLERANCE+eps
                        for a, v in frequencies.items())
                    and abs(sum(frequencies.values())-1) <= 2*unit+eps,
                    'River strategy frequencies changed materially')
            require(0 <= row['own_reach_probability'] <= 1, 'Invalid river own reach')
    oop = data['hands']['oop']['node_strategy']
    ip = data['hands']['ip']['node_strategy']
    root, response = oop['oop_first'], oop['oop_facing_ip_bet_1']
    after, facing = ip['ip_after_oop_check'], ip['ip_facing_oop_bet_1']
    q = root['action_ev_relative_to_half_pot']
    require(root['own_reach_probability'] == after['own_reach_probability'] == facing['own_reach_probability'] == 1
            and abs(response['own_reach_probability']-root['frequency']['check']) <= 2*unit+eps,
            'River own-reach semantics changed')
    # Folding loses half the starting pot; QJ's sole opponent is KK.
    for row in (response, facing):
        require(abs(row['action_ev_relative_to_half_pot']['fold']+pot/2) <= unit+eps,
                'River fold EV baseline changed')
    require(abs(after['action_ev_relative_to_half_pot']['check']+pot/2) <= unit+eps
            and abs(facing['action_ev_relative_to_half_pot']['call']+pot/2+bet) <= unit+eps,
            'River terminal showdown EV changed')
    call = response['frequency']['call']
    require(abs(after['action_ev_relative_to_half_pot']['bet_1pot']-(pot/2-(pot+bet)*call))
            <= (pot+bet)*unit+unit+eps, 'River bluff EV disagrees with returned calling policy')
    # Rounded root average and best response must agree with the reported value/gap.
    rounding = 2*(pot/2+bet)*unit+2*unit+eps
    require(abs(sum(root['frequency'][a]*v for a, v in q.items())-value) <= rounding
            and max(q.values())-value <= gap+rounding, 'River root action EVs disagree with value/gap')
    qj_call = facing['frequency']['call']
    require(-bet/2+bet*qj_call/2-bet*unit/2-unit-eps <= q['bet_1pot']
            <= pot/2+bet*qj_call/2+bet*unit/2+unit+eps, 'River opening-bet EV violates chip accounting')
    # The unqueried AA betting frequency is inferred as an INTERVAL from the
    # checked EV and rounded QJ/KK policies. Do not assume AA always bets or use
    # root NashConv as a conditional-action precision certificate.
    bluff = after['frequency']['bet_1pot']
    possible_aa = [(-checked-pot*b/2+(pot+bet)*b*c/2)/(bet*c/2)
                   for checked, b, c in product((q['check']-unit, q['check']+unit),
                                               (bluff-unit, bluff+unit), (call-unit, call+unit))]
    lo, hi = max(0, min(possible_aa)-eps), min(1, max(possible_aa)+eps)
    require(lo <= hi, 'River checked EV implies an impossible value betting policy')
    possible_ev = [(pot/2+bet)*(b-a)/(a+b)
                   for a, b in product((lo, hi), (bluff-unit, bluff+unit))]
    require(min(possible_ev)-unit-eps <= response['action_ev_relative_to_half_pot']['call']
            <= max(possible_ev)+unit+eps, 'River calling EV disagrees with checked continuation accounting')


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


async def collect(session, request, expected_sources, repeats=2, *, clock=monotonic):
    """Session injection keeps acceptance logic testable without live network/auth."""
    report = {'mode': 'hosted SDK, not ChatGPT', 'cases': [], 'failures': [],
              'warm_latency_gate': {'maximum_client_seconds': MAX_WARM_CLIENT_SECONDS,
                  'basis': '10s worker headroom plus 5s transport/SDK allowance; engineering target, not a verified ChatGPT deadline',
                  'scope': 'Every admitted example after public probes, initialization and tool discovery; no idle cold-start claim'},
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
            started = clock()
            response = await session.call_tool(name, arguments)
            row.update(client_wall_seconds=clock()-started,
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
            row['latency_class'] = 'warm_after_discovery'
            elapsed = row['client_wall_seconds']
            if not (finite(elapsed) and 0 <= elapsed <= MAX_WARM_CLIENT_SECONDS):
                row['latency_failure'] = 'Warm client latency exceeds 15s acceptance target or clock is invalid'
                report['failures'].append(row['id']+': '+row['latency_failure'])
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
    report['legacy_baseline_sha256_lf'] = hashlib.sha256(LEGACY_BASELINE.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    for baseline in legacy_baselines():
        name, arguments = baseline['tool'], baseline['request']
        label = 'river_call' if name == 'evaluate_river_call' else 'river_solve'
        response, row = await call(label, name, arguments)
        if response is not None:
            try:
                require(not response.isError and len(response.content) == 1 and response.content[0].type == 'text'
                        and json.loads(response.content[0].text) == response.structuredContent,
                        'Legacy SDK response is an error or disagrees with structured result')
                validate_legacy_result(name, arguments, response.structuredContent)
            except ReceiptError as error:
                row['legacy_failure'] = str(error)
                report['failures'].append(label+': '+str(error))
            except (ValueError, TypeError, AttributeError, KeyError):
                report['failures'].append(label+': malformed legacy SDK result')
    return report


async def hosted(url, token, expected_sha, request, expected_sources):
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and parsed.path == '/mcp'
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            'Use a plain HTTPS /mcp endpoint')
    require(bool(re.fullmatch('[0-9a-f]{40}', expected_sha)), 'A full expected deployed SHA is required')
    async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
        base = url.rsplit('/mcp', 1)[0]
        first_probe = monotonic()
        health = await client.get(base+'/health')
        first_probe_seconds = monotonic()-first_probe
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
                              public_ready=ready.json(), initialized=initialized.model_dump(mode='json', by_alias=True),
                              first_public_probe={'wall_seconds': first_probe_seconds,
                                  'classification': 'unclassified priming request; no independently verified idle interval'})
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
