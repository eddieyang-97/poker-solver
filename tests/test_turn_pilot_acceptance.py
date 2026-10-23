"""Isolated acceptance-harness checks; synthetic receipts are not hosted evidence."""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from mcp.types import CallToolResult, TextContent, Tool

from poker_spot.turn_pilot import calculate, digest
from scripts import acceptance_turn_pilot as acceptance


def envelope(data, error=False):
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(data))],
                          structuredContent=data, isError=error)


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = json.loads((acceptance.ROOT/'examples/turn-pilot.json').read_text())
        # Real product calculation, with explicitly synthetic Linux measurements.
        # No network or claim that this test exercised Linux resource limits.
        cls.result = calculate(cls.request)
        cls.result['execution'] = {'platform': 'linux', 'budget_enforced': True,
            'limits': {'cpu_seconds': [20, 20], 'address_space_bytes': [384*1024**2]*2},
            'parent_wall_seconds': 3.0, 'worker_wall_seconds': 2.9, 'worker_cpu_seconds': 2.8,
            'memory_bytes': {'VmPeak': 120*1024**2, 'VmHWM': 90*1024**2},
            'stage_seconds': {'bootstrap_imports': 0.1, 'read_parse': 0.01,
                              'validate_solve_br_project_receipt': 2.7, 'result_serialization': 0.01}}
        cls.sources = acceptance.source_hashes()

    def validate(self, result=None, **kwargs):
        return acceptance.validate_turn_result(self.request, result or self.result,
            expected_sources=self.sources, is_error=kwargs.pop('is_error', False), **kwargs)

    def test_exact_receipt_and_platform_independent_runtime_identity(self):
        summary = self.validate(sdk_bytes=len(envelope(self.result).model_dump_json().encode()))
        self.assertEqual(summary['status'], 'computed')
        result = deepcopy(self.result)
        result['provenance'].update(python='3.99.0', numpy='99.0')
        result['game_identity_sha256'] = digest(result['provenance'])
        result['result_sha256'] = digest({k: v for k, v in result.items() if k not in ('execution', 'result_sha256')})
        self.assertEqual(self.validate(result)['status'], 'computed')
        self.assertNotEqual(result['game_identity_sha256'], self.result['game_identity_sha256'])

    def test_receipt_tampering_rejected_even_with_recomputed_outer_hash(self):
        mutations = [lambda r: r.update(request_sha256='0'*64),
                     lambda r: r['provenance']['sources_sha256_lf'].update({'turn.py': '0'*64}),
                     lambda r: r.update(game_identity_sha256='0'*64),
                     lambda r: r['chance'].update(legal_rivers_per_compatible_deal=48),
                     lambda r: r['diagnostics'].update(iterations=1999),
                     lambda r: r.update(views=[])]
        for mutation in mutations:
            result = deepcopy(self.result)
            mutation(result)
            result['result_sha256'] = digest({k: v for k, v in result.items() if k not in ('execution', 'result_sha256')})
            with self.subTest(mutation=mutation), self.assertRaises(acceptance.ReceiptError):
                self.validate(result)
        result = deepcopy(self.result)
        result['result_sha256'] = '0'*64
        with self.assertRaises(acceptance.ReceiptError):
            self.validate(result)

    def test_linux_budget_and_bounded_sdk_output_are_mandatory(self):
        mutations = [lambda m: m.update(platform='win32', budget_enforced=False, limits=None),
                     lambda m: m['limits'].update(cpu_seconds=[21, 21]),
                     lambda m: m['limits'].update(address_space_bytes=[512*1024**2]*2),
                     lambda m: m.update(parent_wall_seconds=20.01),
                     lambda m: m.update(worker_cpu_seconds=float('inf')),
                     lambda m: m['memory_bytes'].update(VmPeak=384*1024**2+1),
                     lambda m: m['stage_seconds'].pop('result_serialization')]
        for mutation in mutations:
            result = deepcopy(self.result)
            mutation(result['execution'])
            with self.subTest(mutation=mutation), self.assertRaises(acceptance.ReceiptError):
                self.validate(result)
        with self.assertRaises(acceptance.ReceiptError):
            self.validate(sdk_bytes=acceptance.MAX_SDK_BYTES+1)

    def test_insufficient_convergence_has_no_views_and_is_an_error(self):
        result = deepcopy(self.result)
        result.update(status='insufficient_convergence', views=[])
        d = result['diagnostics']
        gap = self.request['pot_cents']/100*0.01
        d.update(raw_nash_conv_chips=gap, nash_conv_chips=gap, nash_conv_pct_pot=1.0)
        result['checkpoints'][-1] = deepcopy(d)
        result['best_response_bounds'].update(raw_nash_conv_chips=gap,
                                              oop_best_response_ev=gap, ip_best_response_ev=0)
        result['result_sha256'] = digest({k: v for k, v in result.items() if k not in ('execution', 'result_sha256')})
        self.assertEqual(self.validate(result, is_error=True)['status'], 'insufficient_convergence')
        with self.assertRaises(acceptance.ReceiptError):
            self.validate(result, is_error=False)
        result['views'] = deepcopy(self.result['views'])
        result['result_sha256'] = digest({k: v for k, v in result.items() if k not in ('execution', 'result_sha256')})
        with self.assertRaises(acceptance.ReceiptError):
            self.validate(result, is_error=True)

    def session(self):
        schemes = [{'type': 'oauth2', 'scopes': ['poker:solve']}]
        tools = [Tool(name=name, inputSchema={'type': 'object'}, securitySchemes=schemes,
                      _meta={'securitySchemes': schemes}) for name in acceptance.TOOLS]
        async def call(name, request):
            if name == 'solve_turn_v1':
                return (envelope({'error': {'code': 'invalid_input'}}, True) if request['iterations'] == 1999
                        else envelope(deepcopy(self.result)))
            return envelope({'best_action_given_range': 'indifferent'} if name == 'evaluate_river_call'
                            else {'nash_conv_pct_pot': 0.01})
        return SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=tools)),
                               call_tool=AsyncMock(side_effect=call))

    def test_injected_sdk_records_exact_requests_raw_results_and_legacy_checks(self):
        session = self.session()
        report = asyncio.run(acceptance.collect(session, self.request, self.sources))
        self.assertEqual(report['mode'], 'hosted SDK, not ChatGPT')
        self.assertEqual(report['failures'], [])
        self.assertEqual(len(report['cases']), 5)
        self.assertEqual(report['cases'][0]['request'], self.request)
        self.assertEqual(report['cases'][0]['raw_sdk_result']['structuredContent'], self.result)
        self.assertEqual(session.call_tool.await_count, 5)

    def test_permission_mismatch_stops_calls_and_errors_are_sanitized(self):
        session = self.session()
        session.list_tools.return_value.tools[0].securitySchemes = []
        report = asyncio.run(acceptance.collect(session, self.request, self.sources))
        self.assertTrue(report['failures'])
        session.call_tool.assert_not_awaited()
        session = self.session()
        session.call_tool.side_effect = RuntimeError('never-print-this-token')
        report = asyncio.run(acceptance.collect(session, self.request, self.sources, repeats=1))
        self.assertTrue(report['failures'])
        self.assertNotIn('never-print-this-token', json.dumps(report))

    def test_cli_discards_token_echo_without_writing_or_printing_secret(self):
        token = 'acceptance-test-token-do-not-print'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'receipt.json'
            argv = ['acceptance_turn_pilot.py', '--url', 'https://example.invalid/mcp',
                    '--expected-sha', 'a'*40, '--output', str(output)]
            with patch.object(acceptance, 'hosted', AsyncMock(return_value={'echo': token})), \
                    patch.object(os, 'environ', dict(os.environ, POKER_ACCEPTANCE_TOKEN=token)), \
                    patch('sys.argv', argv), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(acceptance.main(), 1)
            self.assertFalse(output.exists())
            self.assertNotIn(token, stream.getvalue())

    def test_release_identity_is_checked_before_token_or_sdk_use(self):
        seen = []
        def handle(request):
            seen.append((request.url.path, request.headers.get('authorization')))
            return httpx.Response(200, json=({'deployment': {'commit': 'b'*40},
                'engine': 'turn-pilot-v1', 'auth_configured': True} if request.url.path == '/health'
                else {'status': 'ready'}))
        client_class = httpx.AsyncClient
        def client(**kwargs):
            return client_class(transport=httpx.MockTransport(handle), **kwargs)
        with patch.object(acceptance.httpx, 'AsyncClient', side_effect=client), \
                patch.object(acceptance, 'streamable_http_client') as sdk:
            with self.assertRaises(acceptance.ReceiptError):
                asyncio.run(acceptance.hosted('https://example.invalid/mcp', 'secret', 'a'*40,
                                             self.request, self.sources))
            sdk.assert_not_called()
        self.assertEqual(seen, [('/health', None), ('/ready', None)])
        with patch.object(acceptance.httpx, 'AsyncClient') as client:
            for url in ('http://example.invalid/mcp', 'https://secret@example.invalid/mcp',
                        'https://example.invalid/mcp?token=secret'):
                with self.subTest(url=url), self.assertRaises(acceptance.ReceiptError):
                    asyncio.run(acceptance.hosted(url, 'secret', 'a'*40, self.request, self.sources))
            client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
