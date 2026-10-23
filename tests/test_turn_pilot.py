import asyncio
from copy import deepcopy
from decimal import localcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import httpx
import jwt
import numpy as np
from cryptography.hazmat.primitives.asymmetric import ec
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from poker_spot.auth import Settings
from poker_spot.execution import CalculationError, Runner
from poker_spot.http_server import MAX_BODY_BYTES, create_app
from poker_spot.turn import Chance, Terminal, TurnSolver
from poker_spot.turn_pilot import (MAX_RESULT_BYTES, NAME, TOOL, calculate, digest, prepare,
                                   project, solver_config, validated_solver, _canonicalize_tree)

ROOT = Path(__file__).resolve().parents[1]
REQUEST = {
    'board': '2c,3d,4h,8s', 'oop_range': [{'hand': 'KhKd', 'weight': 1.0}],
    'ip_range': [{'hand': 'AsAd', 'weight': 1.0}, {'hand': 'QhJd', 'weight': 0.7}],
    'pot_cents': 10000, 'stack_cents': 20000, 'turn_bet_sizes': [0.5], 'river_bet_sizes': [0.5],
    'views': [{'player': 'oop', 'hand': 'KhKd', 'node': 'turn'},
              {'player': 'ip', 'hand': 'QhJd', 'node': 'turn/check'},
              {'player': 'oop', 'hand': 'KhKd', 'node': 'turn/check/check/river', 'river_card': '9c'}],
}
CALL = {'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd',
        'villain_betting_range': 'AsJh', 'pot': 505, 'bet': 450}


class ContractTests(unittest.TestCase):
    def test_explicit_input_bounds_and_no_silent_range_changes(self):
        self.assertEqual(TOOL['name'], 'solve_turn_v1')
        valid = prepare(REQUEST)
        self.assertEqual(valid['iterations'], 2000)
        bad = [dict(board='2c,3d,4h,8s,9c'), dict(pot_cents=True), dict(pot_cents=100.0),
               dict(stack_cents=1_000_001), dict(iterations=1999), dict(iterations=2001),
               dict(turn_bet_sizes=[0.5, 1.0]), dict(river_bet_sizes=[True]),
               dict(oop_range='KK'), dict(views=REQUEST['views']*2), dict(rake=0), dict(cache_key='other'),
               dict(oop_range=[{'hand': '2cKd', 'weight': 1}]),
               dict(oop_range=[{'hand': 'KhKd', 'weight': 1}, {'hand': 'KdKh', 'weight': 0.5}]),
               dict(oop_range=[{'hand': 'KhKd', 'weight': 1e-7}]),
               dict(oop_range=[{'hand': 'KhKd', 'weight': 1}, {'hand': 'QhQd', 'weight': 1},
                               {'hand': 'JsJd', 'weight': 1}]),
               dict(ip_range=[{'hand': 'KhQc', 'weight': 1}])]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                prepare(dict(REQUEST, **changes))

    def test_exact_cents_and_private_context(self):
        config = dict(REQUEST, pot_cents=101, turn_bet_sizes=[0.5])
        for precision in (2, 28, 80):
            with localcontext() as context:
                context.prec = precision
                with self.assertRaisesRegex(ValueError, 'exact integer cents'):
                    prepare(config)
                self.assertEqual(prepare(REQUEST)['pot_cents'], 10000)
        # A specified oversized fraction is capped, disclosed, with no additional jam.
        solver = validated_solver(prepare(dict(REQUEST, stack_cents=1000,
                                                views=[], turn_bet_sizes=[3.0])))
        self.assertEqual(solver.effective_bets['turn'], [10.0])
        self.assertEqual(solver.nodes['turn'].actions, ('check', 'bet_10'))

    def test_views_reject_wrong_actor_hand_history_and_blockers(self):
        for view in [dict(player='ip', hand='QhJd', node='turn'),
                     dict(player='oop', hand='KhKd', node='turn/raise_100'),
                     dict(player='oop', hand='AsAd', node='turn'),
                     dict(player='oop', hand='KhKd', node='turn', river_card='9c'),
                     dict(player='oop', hand='KhKd', node='turn/check/check/river'),
                     dict(player='oop', hand='KhKd', node='turn/check/check/river', river_card='Kh'),
                     dict(player='oop', hand='KhKd', node='turn/check/check/river', river_card='2c')]:
            with self.subTest(view=view), self.assertRaises(ValueError):
                validated_solver(prepare(dict(REQUEST, views=[view])))

    def test_cent_canonical_called_river_history_preserves_numerical_game(self):
        river_root = 'turn/bet_30.1/call/river'
        view = dict(player='oop', hand='KhKd', node=river_root+'/check/bet_45.15', river_card='9c')
        request = dict(REQUEST, pot_cents=3010, turn_bet_sizes=[1.0], river_bet_sizes=[0.5],
                       views=[view, dict(player='ip', hand='QhJd', node=river_root+'/check', river_card='9c')])
        args = prepare(request)
        original = TurnSolver(**solver_config(args))
        raw_path = river_root+'/check/bet_45.150000000000006'
        self.assertIn(raw_path, original.nodes)  # Actual float repr reproducer, not a fabricated tree.
        solver = validated_solver(args)
        self.assertIn(view['node'], solver.nodes)
        self.assertNotIn(raw_path, solver.nodes)
        self.assertEqual(solver.nodes[view['node']].player, 0)
        self.assertEqual(solver.nodes[river_root+'/check'].actions, ('check', 'bet_45.15'))
        self.assertEqual(solver.effective_bets[river_root], [45.15])
        self.assertEqual(solver.effective_bets['turn/check/bet_30.1/call/river'], [45.15])
        self.assertEqual(solver.effective_bets['turn/check/check/river'], [15.05])
        self.assertEqual(solver.effective_bets['turn'], [30.1])

        def ledger(node):
            if isinstance(node, Terminal):
                return (node.kind, node.contrib, node.street, node.winner)
            if isinstance(node, Chance):
                return ('chance', ledger(node.child))
            return (node.player, node.street, tuple(ledger(child) for child in node.children))

        self.assertEqual(ledger(solver.root), ledger(original.root))
        expected = original.solve(2000, oop_hand='KhKd', ip_hand='QhJd', river_card='9c')
        actual = solver.solve(2000)
        self.assertEqual(actual['diagnostics'], expected['diagnostics'])
        self.assertEqual(actual['effective_bets_by_public_history'][river_root], [45.15])
        # Relabeling preserves order, all training tensors and every fixed-policy EV/reach row.
        old_rows, new_rows = {}, {}
        original._walk(original.root, *original.weights, collect=old_rows)
        solver._walk(solver.root, *solver.weights, collect=new_rows)
        for before, after in zip(original.nodes.values(), solver.nodes.values(), strict=True):
            for field in ('regret', 'strategy_sum', 'strategy'):
                np.testing.assert_array_equal(getattr(before, field), getattr(after, field))
            for field in ('ev', 'own', 'opponent'):
                np.testing.assert_array_equal(old_rows[before.name][field], new_rows[after.name][field])
        rows = project(solver, args['views'])
        for row in rows:
            key = row['node'].replace('/bet_45.15', '/bet_45.150000000000006')+'@9c'
            baseline = expected['hands'][row['player']]['node_strategy'][key]
            self.assertEqual(row['reach_probability_given_hand'], baseline['reach_probability_given_hand'])
            for field in ('frequency', 'action_ev_relative_to_half_turn_pot'):
                self.assertEqual(list(row[field].values()), list(baseline[field].values()))
                self.assertNotIn('bet_45.150000000000006', row[field])
        self.assertEqual(rows[0]['node'], view['node'])
        self.assertEqual(set(rows[1]['frequency']), {'check', 'bet_45.15'})
        # Future views are projections of the same trained policy, with unchanged root diagnostics.
        other = project(solver, [dict(args['views'][0], river_card='9d')])[0]
        self.assertEqual(other['node'], view['node'])
        self.assertEqual(solver.diagnostics(), actual['diagnostics'])
        for precision in (2, 28, 80):
            with localcontext() as context:
                context.prec = precision
                self.assertEqual(validated_solver(prepare(request)).effective_bets, solver.effective_bets)
        with self.assertRaises(ValueError):
            validated_solver(prepare(dict(request, views=[dict(view, node=raw_path)])))
        with self.assertRaisesRegex(ValueError, 'exact integer cents'):
            prepare(dict(request, pot_cents=3011))

    def test_cent_mapping_rejects_collisions_and_topology_changes(self):
        args = prepare(dict(REQUEST, views=[]))
        solver = TurnSolver(**solver_config(args))
        keys = list(solver.nodes)
        # A float-spelling alias must never overwrite a different public node.
        alias = 'turn/bet_50.0'
        solver.nodes[alias] = deepcopy(solver.nodes['turn/bet_50'])
        solver.nodes[alias].name = alias
        solver.nodes['turn'].actions = ('check', 'bet_50', 'bet_50.0')
        solver.effective_bets['turn'] = [50.0, 50.0]
        with patch('poker_spot.turn_pilot._cent_tree', return_value={**solver.effective_bets, 'turn': [5000, 5000]}):
            with self.assertRaisesRegex(ValueError, 'collide'):
                _canonicalize_tree(solver, args)
        self.assertEqual(list(solver.nodes), keys+[alias])  # No partial relabeling after failure.
        # Exact all-in versus binary64 residual: reject a spurious extra river, never create bet_0.
        args = prepare(dict(REQUEST, pot_cents=1000, stack_cents=1130, turn_bet_sizes=[1.13], views=[]))
        with self.assertRaisesRegex(ValueError, 'exact-cent histories'):
            validated_solver(args)
        for turn_sizes, river_sizes in (([], []), ([], [0.5]), ([1.0], [])):
            validated_solver(prepare(dict(REQUEST, turn_bet_sizes=turn_sizes, river_bet_sizes=river_sizes, views=[])))

    def test_zero_opponent_river_support_keeps_null_evs(self):
        args = prepare(dict(REQUEST, ip_range=[{'hand': 'AsAd', 'weight': 1}],
                            views=[dict(player='oop', hand='KhKd',
                                        node='turn/check/check/river', river_card='As')]))
        solver = validated_solver(args)
        row = project(solver, args['views'])[0]
        self.assertEqual(row['compatible_opponent_reach'], 0)
        self.assertEqual(row['reach_probability_given_hand'], 0)
        self.assertTrue(all(value is None for value in row['action_ev_relative_to_half_turn_pot'].values()))

    def test_bounded_projection_matches_direct_solve_and_receipts(self):
        result = calculate(REQUEST)
        direct = TurnSolver(**solver_config(prepare(REQUEST))).solve(
            2000, oop_hand='KhKd', ip_hand='QhJd', river_card='9c')
        self.assertEqual(result['diagnostics'], direct['diagnostics'])
        self.assertEqual(result['status'], 'computed')
        self.assertEqual(result['source'], 'computed_on_demand')
        self.assertAlmostEqual(result['best_response_bounds']['raw_nash_conv_chips'],
                               result['diagnostics']['raw_nash_conv_chips'], delta=1e-8)
        for side in ('oop', 'ip'):
            self.assertGreaterEqual(result['best_response_bounds'][side+'_best_response_ev']+1e-8,
                                    result['diagnostics'][side+'_ev'])
        for row in result['views']:
            key = row['node']+('@'+row['river_card'] if row['river_card'] else '')
            expected = direct['hands'][row['player']]['node_strategy'][key]
            for field in ('frequency', 'action_ev_relative_to_half_turn_pot', 'reach_probability_given_hand'):
                self.assertEqual(row[field], expected[field])
        checksum = result.pop('result_sha256')
        self.assertEqual(digest(result), checksum)
        self.assertLess(len(json.dumps(result).encode()), MAX_RESULT_BYTES)
        # Output views cannot alter solved-game identity, EV or policy.
        summary = calculate(dict(REQUEST, views=[]))
        self.assertEqual(summary['game_identity_sha256'], result['game_identity_sha256'])
        self.assertEqual(summary['diagnostics'], result['diagnostics'])
        self.assertNotEqual(summary['request_sha256'], result['request_sha256'])

    def test_nonconvergence_never_returns_strategy(self):
        original = TurnSolver.solve

        def unconverged(solver, iterations):
            output = original(solver, 20)
            output['diagnostics']['nash_conv_pct_pot'] = 0.500001
            return output

        with patch.object(TurnSolver, 'solve', unconverged), patch('poker_spot.turn_pilot.project') as projection:
            result = calculate(REQUEST)
        self.assertEqual(result['status'], 'insufficient_convergence')
        self.assertEqual(result['source'], 'computed_on_demand')
        self.assertEqual(result['views'], [])
        projection.assert_not_called()

    def test_default_surface_and_render_guard(self):
        with patch.dict(os.environ, {'RENDER': 'true'}), self.assertRaisesRegex(ValueError, 'local only'):
            create_app(Settings(), turn_pilot=True)
        with self.assertRaisesRegex(ValueError, 'must agree'):
            create_app(Settings(), Runner(turn_pilot=True))
        token = 'isolated-local-test-token-at-least-32'
        with TestClient(create_app(Settings(local_token=token))) as client:
            reply = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                                headers={'Authorization': f'Bearer {token}',
                                         'Accept': 'application/json, text/event-stream'})
            self.assertEqual({t['name'] for t in reply.json()['result']['tools']},
                             {'solve_river', 'evaluate_river_call'})

    @unittest.skipUnless(sys.platform == 'linux', 'Actual Linux pre-import address-space enforcement')
    def test_worker_limits_precede_numpy_and_actual_allocation_fails(self):
        code = '''import resource, runpy, sys, types
original = resource.setrlimit
def checked(*args):
    assert 'numpy' not in sys.modules and 'poker_spot' not in sys.modules
    return original(*args)
resource.setrlimit = checked
sys.modules['poker_spot.turn_pilot'] = types.SimpleNamespace(
    MAX_RESULT_BYTES=24576, calculate=lambda args: bytes(384*1024**2))
runpy.run_path(sys.argv[1], run_name='__main__')
'''
        # Fake module is not the package; checks above confirm no actual package/NumPy imports.
        outcome = subprocess.run([sys.executable, '-I', '-c', code, str(ROOT/'poker_spot/turn_worker.py')],
                                 input='{}', capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(outcome.stdout)['error']['code'], 'resource_limit')


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_oversize_and_failed_workers_release_shared_slot(self):
        original = asyncio.create_subprocess_exec
        for code, expected in (("import sys; sys.stdout.write('x'*27000)", 'output_limit'),
                               ('raise SystemExit(9)', 'worker_failed')):
            captured = []

            async def child(*command, **kwargs):
                captured.append((command, kwargs['env']))
                return await original(sys.executable, '-I', '-c', code, **kwargs)

            runner = Runner(turn_pilot=True)
            with patch.dict(os.environ, {'POKER_MCP_TOKEN': 'private-canary', 'PYTHONPATH': 'private-path'}), \
                    patch('poker_spot.execution.asyncio.create_subprocess_exec', side_effect=child):
                with self.assertRaises(CalculationError) as error:
                    await runner.run(NAME, REQUEST)
            self.assertEqual(error.exception.code, expected)
            self.assertFalse(runner.busy)
            self.assertNotIn('POKER_MCP_TOKEN', captured[0][1])
            self.assertNotIn('PYTHONPATH', captured[0][1])
            self.assertEqual(captured[0][0][1], '-I')
            self.assertEqual((await runner.run('evaluate_river_call', CALL))['ev_call_minus_fold'], 955)

    async def test_opt_in_timeout_recovery_shared_slot_and_rate(self):
        with self.assertRaises(CalculationError) as error:
            await Runner().run(NAME, REQUEST)
        self.assertEqual(error.exception.code, 'invalid_input')
        runner = Runner(timeout=0.001, turn_pilot=True)
        with self.assertRaises(CalculationError) as error:
            await runner.run(NAME, REQUEST)
        self.assertEqual(error.exception.code, 'timeout')
        self.assertFalse(runner.busy)
        runner.timeout = 20
        task = asyncio.create_task(runner.run(NAME, REQUEST))
        await asyncio.sleep(0)
        with self.assertRaises(CalculationError) as error:
            await runner.run('evaluate_river_call', CALL)
        self.assertEqual(error.exception.code, 'busy')
        result = await task
        self.assertEqual(result['status'], 'computed')
        self.assertEqual(result['execution']['budget_enforced'], sys.platform == 'linux')
        self.assertFalse(runner.busy)
        self.assertEqual((await runner.run('evaluate_river_call', CALL))['ev_call_minus_fold'], 955)
        runner.rate = len(runner.starts)
        with self.assertRaises(CalculationError) as error:
            await runner.run(NAME, REQUEST)
        self.assertEqual(error.exception.code, 'rate_limited')

    async def test_cancelled_turn_is_reaped_and_releases_slot(self):
        runner = Runner(turn_pilot=True)
        task = asyncio.create_task(runner.run(NAME, REQUEST))
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(runner.busy)
        self.assertEqual((await runner.run('evaluate_river_call', CALL))['ev_call_minus_fold'], 955)

    async def test_sdk_oauth_and_unchanged_existing_tools(self):
        key = ec.generate_private_key(ec.SECP256R1())
        settings = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                            jwks_url='https://identity.example/keys', subjects=frozenset({'owner'}))
        app = create_app(settings, turn_pilot=True)
        app.state.verifier.keys = {'test': jwt.PyJWK.from_json(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))}
        app.state.verifier.fetched = time.monotonic()
        payload = {'sub': 'owner', 'iss': settings.issuer, 'aud': settings.resource,
                   'iat': int(time.time()), 'exp': int(time.time())+120, 'scope': 'poker:solve'}

        def signed(changes=None, private=key):
            return jwt.encode(dict(payload, **(changes or {})), private, algorithm='ES256', headers={'kid': 'test'})

        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            for method in ('GET', 'DELETE'):
                self.assertEqual((await client.request(method, settings.resource)).status_code, 401)
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': NAME, 'arguments': REQUEST}}
            for changes in ({'sub': 'other'}, {'aud': 'https://travel.example/mcp'},
                            {'iss': 'https://evil.example/'}, {'scope': 'travel:read'}, {'exp': 1}):
                response = await client.post(settings.resource, json=request,
                    headers={'Authorization': 'Bearer '+signed(changes), 'Accept': 'application/json, text/event-stream'})
                self.assertEqual(response.status_code, 401)
                self.assertFalse(app.state.runner.starts)
            for token in ('', signed(private=ec.generate_private_key(ec.SECP256R1()))):
                self.assertEqual((await client.post(settings.resource, json=request,
                    headers={'Authorization': 'Bearer '+token})).status_code, 401)
            client.headers.update({'Authorization': 'Bearer '+signed()})
            self.assertEqual((await client.post(settings.resource, content=b'x'*(MAX_BODY_BYTES+1),
                headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})).status_code, 413)
            async with streamable_http_client(settings.resource, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual({t.name for t in tools}, {NAME, 'solve_river', 'evaluate_river_call'})
                    self.assertTrue(all(t.model_extra['securitySchemes'][0]['scopes'] == ['poker:solve'] for t in tools))
                    cent_path = 'turn/bet_30.1/call/river/check/bet_45.15'
                    cent_request = dict(REQUEST, pot_cents=3010, turn_bet_sizes=[1.0],
                                        views=[dict(player='oop', hand='KhKd', node=cent_path, river_card='9c')])
                    result = await session.call_tool(NAME, cent_request)
                    self.assertFalse(result.isError, result)
                    self.assertEqual(result.structuredContent['status'], 'computed')
                    self.assertEqual(result.structuredContent['views'][0]['node'], cent_path)
                    self.assertEqual(set(result.structuredContent['views'][0]['frequency']), {'fold', 'call'})
                    self.assertEqual(result.structuredContent['effective_bets_by_public_history'][
                        'turn/bet_30.1/call/river'], [45.15])
                    self.assertLess(len(result.model_dump_json().encode()), 65_536)
                    with patch.object(app.state.runner, 'run', return_value={
                            'source': 'computed_on_demand', 'status': 'insufficient_convergence', 'views': []}):
                        insufficient = await session.call_tool(NAME, REQUEST)
                    self.assertTrue(insufficient.isError)
                    self.assertEqual(insufficient.structuredContent['views'], [])
                    bad = deepcopy(REQUEST)
                    bad['views'][0]['node'] = 'turn/raise_100'
                    self.assertTrue((await session.call_tool(NAME, bad)).isError)
                    call = await session.call_tool('evaluate_river_call', CALL)
                    self.assertFalse(call.isError)
                    self.assertEqual(call.structuredContent['ev_call_minus_fold'], 955)
                    river = await session.call_tool('solve_river', {'board': '2c,3d,4h,8s,9c',
                        'oop_range': 'AsAd', 'ip_range': 'KhQd', 'pot': 100, 'stack': 100,
                        'bet_sizes': [1.0], 'iterations': 100})
                    self.assertFalse(river.isError)


if __name__ == '__main__':
    unittest.main()
