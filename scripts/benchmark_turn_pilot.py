"""Issue #26 Stage A: actual shared-runner probes; no network or production writes."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.types import CallToolResult, TextContent

from poker_spot.core import DECK
from poker_spot.execution import CalculationError, Runner
from poker_spot.turn_pilot import NAME, digest

ROOT = Path(__file__).resolve().parents[1]


def scenarios():
    """Existing independently checked games; no fabricated organic demand claim."""
    questions = {
        'singleton_minimax': 'Inspect a flush draw versus a known overpair in a toy game',
        'weighted_dry': 'Compare value and missed-high-card continuations under supplied weights',
        'weighted_collision': 'Inspect blocker-sensitive turn betting and one future river view',
        'turn_allin': 'Inspect a terminal turn shove versus a two-combo arrival hypothesis',
    }
    cases = []
    for fixture in json.loads((ROOT/'benchmarks/turn-independent-fixtures.json').read_text()):
        if fixture['id'] not in questions:
            continue
        c = fixture['config']
        dead = set(c['board']) | set(c['oop'][0]['hand'][i:i+2] for i in (0, 2))
        river = next(card for card in DECK if card not in dead)
        views = [dict(player='oop', hand=c['oop'][0]['hand'], node='turn'),
                 dict(player='ip', hand=c['ip'][0]['hand'], node='turn/check'),
                 dict(player='oop', hand=c['oop'][0]['hand'], node='turn/check/check/river', river_card=river)]
        cases.append({'id': fixture['id'], 'question': questions[fixture['id']], 'request': {
            'board': ','.join(c['board']), 'oop_range': c['oop'], 'ip_range': c['ip'],
            'pot_cents': int(c['pot']*100), 'stack_cents': int(c['stack']*100),
            'turn_bet_sizes': c['turn_bet_sizes'], 'river_bet_sizes': c['river_bet_sizes'],
            'iterations': 2000, 'views': views}})
    return cases


async def study(repeats):
    report = {'mode': 'Local opt-in SDK-compatible runner; NOT Render/ChatGPT acceptance',
              'platform': platform.platform(), 'python': platform.python_version(),
              'linux_limits_expected': sys.platform == 'linux', 'architecture': 'live_only',
              'cache_hit_miss': 'not_applicable; no cache or fallback',
              'coverage': 'Four predeclared synthetic small-game questions, not organic usage or full-width ranges',
              'cases': [], 'negatives': [], 'failures': []}
    cases = scenarios()
    for case in cases:
        row = dict(case, samples=[])
        for _ in range(repeats):
            try:
                # Each sample starts an actual new isolated worker; no training reuse.
                result = await Runner(turn_pilot=True).run(NAME, case['request'])
                receipt = {k: v for k, v in result.items() if k not in ('execution', 'result_sha256')}
                if digest(receipt) != result['result_sha256']:
                    raise ValueError('Result receipt mismatch')
                envelope = CallToolResult(content=[TextContent(type='text', text=json.dumps(result))],
                                          structuredContent=result, isError=False)
                sample = {'result': result, 'sdk_result_bytes': len(envelope.model_dump_json().encode())}
                m = result['execution']
                sample['observed_headroom'] = (m['budget_enforced'] is True
                    and m['parent_wall_seconds'] <= 10 and m['worker_cpu_seconds'] <= 10
                    and m['memory_bytes']['VmPeak'] <= 192*1024**2)
                if result['status'] != 'computed' or sample['sdk_result_bytes'] > 65_536:
                    report['failures'].append(case['id']+': convergence or bounded output gate failed')
                if sys.platform == 'linux' and not sample['observed_headroom']:
                    report['failures'].append(case['id']+': observed conservative headroom failed')
                row['samples'].append(sample)
            except (CalculationError, ValueError) as error:
                row['samples'].append({'status': getattr(error, 'code', 'receipt_failed'), 'message': str(error)})
                report['failures'].append(case['id']+': '+str(error))
        report['cases'].append(row)
        print(f"{case['id']}: {len(row['samples'])} fresh worker samples", flush=True)
    request = cases[0]['request']
    bad = [('third_combo', dict(request, oop_range=[*request['oop_range'],
            {'hand': 'AhAd', 'weight': 1}, {'hand': 'KhKd', 'weight': 1}])),
           ('two_sizes', dict(request, river_bet_sizes=[0.5, 1.0])),
           ('fractional_cent', dict(request, pot_cents=101)),
           ('too_few_iterations', dict(request, iterations=20))]
    bad_view = deepcopy(request)
    bad_view['views'][0]['node'] = 'turn/raise_1'
    bad.append(('invalid_view', bad_view))
    for name, args in bad:
        try:
            await Runner(turn_pilot=True).run(NAME, args)
            report['failures'].append(name+': invalid request accepted')
        except CalculationError as error:
            report['negatives'].append({'id': name, 'status': error.code})
            if error.code != 'invalid_input':
                report['failures'].append(name+': unexpected classification')
    runner = Runner(timeout=0.001, turn_pilot=True)
    try:
        await runner.run(NAME, request)
        report['failures'].append('Tight actual timeout did not terminate the worker')
    except CalculationError as error:
        report['negatives'].append({'id': 'real_timeout', 'status': error.code, 'slot_released': not runner.busy})
        if error.code != 'timeout' or runner.busy:
            report['failures'].append('Actual timeout/reap failure')
    runner.timeout = 20
    try:
        result = await runner.run(NAME, request)
        report['negatives'].append({'id': 'recovery_after_timeout', 'status': result['status'], 'result': result})
        if result['status'] != 'computed':
            report['failures'].append('Post-timeout recovery did not compute')
    except CalculationError as error:
        report['failures'].append('Post-timeout recovery: '+str(error))
    report['insufficient_convergence'] = ('Boundary rejection covered by injected regression; '
        'actual 20-iteration nonconvergence retained in Issue #21; no failing 2000-iteration sample claimed')
    paths = ['poker_spot/'+p for p in ('core.py', 'turn.py', 'turn_pilot.py', 'turn_worker.py',
                                      'execution.py', 'http_server.py', 'auth.py')]
    paths += ['scripts/benchmark_turn_pilot.py', 'tests/test_turn_pilot.py']
    report['sources_sha256_lf'] = {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/turn-pilot'))
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    report = asyncio.run(study(args.repeats))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# Local turn MCP pilot probes', '', report['mode'], '',
             '| Synthetic question | Repeat | Status | Parent wall s | CPU s | AS MiB | SDK bytes |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for case in report['cases']:
        for i, sample in enumerate(case['samples']):
            result = sample.get('result', {})
            m = result.get('execution', {})
            cpu = m.get('worker_cpu_seconds', 'unmeasured')
            memory = m.get('memory_bytes', {}).get('VmPeak')
            lines.append(f"| {case['id']} | {i+1} | {result.get('status', sample.get('status'))} | "
                         f"{m.get('parent_wall_seconds')} | {cpu} | {memory/1024**2 if memory else 'unmeasured'} | "
                         f"{sample.get('sdk_result_bytes')} |")
    lines += ['', 'Windows samples do not enforce Linux budgets. Synthetic coverage is not demand evidence.',
              'No cache, Render deployment, external OAuth lifecycle or real ChatGPT turn acceptance.',
              '', '## Failures', '', *(report['failures'] or ['None observed in the declared local study.'])]
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return int(bool(report['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
