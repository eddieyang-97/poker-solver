import asyncio
import json
import os
import time
import unittest
from unittest.mock import patch

import jwt
import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from poker_spot.auth import Settings, Verifier
from poker_spot.execution import CalculationError, Runner
from poker_spot.http_server import MAX_BODY_BYTES, create_app

TOKEN = 'local-test-token-with-at-least-32-characters'
CALL = {'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd',
        'villain_betting_range': 'AsJh', 'pot': 505, 'bet': 450}


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(local_token=TOKEN))
        self.client = self.enterContext(TestClient(self.app))

    def send(self, message, **extra):
        headers = {'Authorization': f'Bearer {TOKEN}',
                   'Accept': 'application/json, text/event-stream', **extra}
        return self.client.post('/mcp', json=message, headers=headers)

    def call(self, args, name='evaluate_river_call'):
        return self.send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                          'params': {'name': name, 'arguments': args}}).json()['result']

    def test_health_and_fail_closed_readiness(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/ready').status_code, 200)
        with TestClient(create_app(Settings())) as client:
            self.assertEqual(client.get('/ready').status_code, 503)
            self.assertEqual(client.post('/mcp').status_code, 503)
        pending = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                           jwks_url='https://identity.example/keys')
        with TestClient(create_app(pending)) as client:
            self.assertEqual(client.get('/ready').status_code, 503)
            self.assertEqual(client.post('/mcp').status_code, 401)
            self.assertIn('resource_metadata=', client.post('/mcp').headers['WWW-Authenticate'])

    def test_auth_all_methods_and_origin_host_protection(self):
        for method in ('get', 'post', 'delete'):
            r = getattr(self.client, method)('/mcp')
            self.assertEqual(r.status_code, 401)
            self.assertIn('WWW-Authenticate', r.headers)
        req = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        self.assertEqual(self.send(req, Origin='https://evil.example').status_code, 403)
        self.assertEqual(self.send(req, Host='evil.example').status_code, 421)
        self.assertEqual(self.send(req, Origin='https://chatgpt.com').status_code, 200)

    def test_protocol(self):
        r = self.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                       'params': {'protocolVersion': '2099-01-01', 'capabilities': {},
                                  'clientInfo': {'name': 'test', 'version': '1'}}})
        result = r.json()['result']
        self.assertNotEqual(result['protocolVersion'], '2099-01-01')
        self.assertEqual(result['serverInfo']['name'], 'poker-spot-study')
        self.assertNotIn('mcp-session-id', r.headers)
        r = self.send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        tools = r.json()['result']['tools']
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]['inputSchema']['properties']['iterations']['maximum'], 1500)
        self.assertEqual(tools[0]['securitySchemes'][0]['scopes'], ['poker:solve'])
        self.assertEqual(self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'}).status_code, 202)
        r = self.send({'jsonrpc': '2.0', 'id': 4, 'method': 'unknown'})
        self.assertIn(r.json()['error']['code'], (-32601, -32602))
        self.assertEqual(self.send({'jsonrpc': '2.0', 'id': 4, 'method': 'ping'},
                                   **{'MCP-Protocol-Version': '2099-01-01'}).status_code, 400)

    def test_invalid_protocol_and_body_limit(self):
        headers = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream'}
        for body in ('not-json', '[]', '{"jsonrpc":"wrong","id":1,"method":"ping"}'):
            r = self.client.post('/mcp', content=body, headers=headers)
            self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post('/mcp', content='x'*(MAX_BODY_BYTES+1), headers=headers).status_code, 413)
        chunks = (b'x'*1024 for _ in range(20))
        self.assertEqual(self.client.post('/mcp', content=chunks, headers=headers).status_code, 413)

    def test_actual_worker_call_and_solve(self):
        out = self.call(CALL)
        self.assertFalse(out['isError'])
        self.assertEqual(out['structuredContent']['ev_call_minus_fold'], 955)
        result = self.call({'board': '2c,3d,4h,8s,9c', 'oop_range': 'AsAd',
                            'ip_range': 'KhQd', 'pot': 100, 'stack': 100,
                            'iterations': 100, 'bet_sizes': [1.0], 'oop_hand': 'AsAd'}, 'solve_river')
        self.assertFalse(result['isError'], result)
        self.assertLess(result['structuredContent']['nash_conv_pct_pot'], 1)

    def test_strict_arguments_and_hosted_limits(self):
        for args in ({**CALL, 'pot': True}, {**CALL, 'pot': '505'},
                     {**CALL, 'surprise': 1}, {**CALL, 'board': 'bad'},
                     {**CALL, 'villain_betting_range': 'AsJh:NaN'}):
            self.assertTrue(self.call(args)['isError'])
        args = {'board': '2c,3d,4h,8s,9c', 'oop_range': 'AA', 'ip_range': 'KK',
                'pot': 100, 'stack': 100, 'iterations': 1501}
        self.assertTrue(self.call(args, 'solve_river')['isError'])
        args.update(iterations=100, oop_range='AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,AK,AQ,AJ,AT,KQ,KJ,KT,QJ,QT')
        self.assertTrue(self.call(args, 'solve_river')['isError'])


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_kills_worker_and_releases_slot(self):
        runner = Runner(timeout=0.001)
        with self.assertRaises(CalculationError) as error:
            await runner.run('evaluate_river_call', CALL)
        self.assertEqual(error.exception.code, 'timeout')
        self.assertFalse(runner.busy)
        runner.timeout = 10
        self.assertEqual((await runner.run('evaluate_river_call', CALL))['ev_call_minus_fold'], 955)

    async def test_concurrent_admission_and_rate(self):
        runner = Runner(rate=1)
        task = asyncio.create_task(runner.run('evaluate_river_call', CALL))
        await asyncio.sleep(0)
        with self.assertRaises(CalculationError) as error:
            await runner.run('evaluate_river_call', CALL)
        self.assertIn(error.exception.code, ('busy', 'rate_limited'))
        await task
        with self.assertRaises(CalculationError) as error:
            await runner.run('evaluate_river_call', CALL)
        self.assertEqual(error.exception.code, 'rate_limited')


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.settings = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                                 jwks_url='https://identity.example/.well-known/jwks.json',
                                 subjects=frozenset({'owner'}))
        self.app = create_app(self.settings)
        jwk = jwt.PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key()))
        self.app.state.verifier.keys = {'test': jwk}
        self.app.state.verifier.fetched = time.monotonic()
        self.client = self.enterContext(TestClient(self.app, base_url='https://poker.example'))

    def token(self, **changes):
        payload = {'sub': 'owner', 'iss': self.settings.issuer, 'aud': self.settings.resource,
                   'iat': int(time.time()), 'exp': int(time.time())+120, 'scope': 'poker:solve'}
        payload.update(changes)
        return jwt.encode(payload, self.private, algorithm='RS256', headers={'kid': 'test'})

    def send(self, token):
        return self.client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                                headers={'Authorization': f'Bearer {token}',
                                         'Accept': 'application/json, text/event-stream'})

    def test_resource_metadata_and_challenge(self):
        doc = self.client.get('/.well-known/oauth-protected-resource').json()
        self.assertEqual(doc['resource'], self.settings.resource)
        self.assertEqual(doc['authorization_servers'], [self.settings.issuer])
        r = self.send('bad')
        self.assertEqual(r.status_code, 401)
        self.assertIn('resource_metadata=', r.headers['WWW-Authenticate'])

    def test_signed_token_boundaries(self):
        self.assertEqual(self.send(self.token()).status_code, 200)
        self.assertEqual(self.send(self.token(iat=int(time.time())+2)).status_code, 200)
        for change in ({'aud': 'https://trip.example/mcp'}, {'iss': 'https://evil.example'},
                       {'sub': 'other-user'}, {'scope': 'travel:read'}, {'exp': 1},
                       {'iat': int(time.time())+600}):
            with self.subTest(change=change):
                self.assertEqual(self.send(self.token(**change)).status_code, 401)
        forged = jwt.encode({'sub': 'owner'}, 'wrong-key-that-is-at-least-32-characters', algorithm='HS256', headers={'kid': 'test'})
        self.assertEqual(self.send(forged).status_code, 401)
        unsigned = jwt.encode({'sub': 'owner'}, '', algorithm='none')
        self.assertEqual(self.send(unsigned).status_code, 401)

    def test_environment_fails_closed_and_render_forbids_static_token(self):
        with patch.dict(os.environ, {'POKER_MODE': 'local', 'POKER_MCP_TOKEN': TOKEN}, clear=True):
            self.assertTrue(Settings.from_env().configured)
            with patch.dict(os.environ, {'RENDER': 'true'}):
                self.assertFalse(Settings.from_env().configured)
        for issuer in ('http://identity.example', 'https://name:password@identity.example',
                       'https://identity.example/#fragment'):
            with patch.dict(os.environ, {'POKER_RESOURCE': 'https://poker.example/mcp',
                                        'POKER_OAUTH_ISSUER': issuer,
                                        'POKER_OAUTH_JWKS_URL': 'https://identity.example/keys'}, clear=True):
                with self.assertRaises(ValueError):
                    Settings.from_env()


class JWKSIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_rotation_throttling_and_provider_failure(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
        settings = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                            jwks_url='https://identity.example/keys', subjects=frozenset({'owner'}))
        verifier = Verifier(settings)
        fetched = []
        kid = ['first']
        status = [200]

        def jwks(request):
            fetched.append(str(request.url))
            return httpx.Response(status[0], json={'keys': [{**public, 'kid': kid[0]}]})

        real_client = httpx.AsyncClient

        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(jwks), **kwargs)

        def token(key_id):
            return 'Bearer '+jwt.encode({'sub': 'owner', 'iss': settings.issuer, 'aud': settings.resource,
                                         'iat': int(time.time()), 'exp': int(time.time())+60,
                                         'scope': 'poker:solve'}, private, algorithm='RS256', headers={'kid': key_id})

        with patch('poker_spot.auth.httpx.AsyncClient', side_effect=client):
            self.assertTrue(await verifier.verify(token('first')))
            self.assertTrue(await verifier.verify(token('first')))
            self.assertFalse(await verifier.verify(token('attacker-key')))
            self.assertEqual(fetched, [settings.jwks_url])
            kid[0] = 'rotated'
            verifier.fetched -= 61
            self.assertTrue(await verifier.verify(token('rotated')))
            self.assertFalse(await verifier.verify(token('first')))
            self.assertEqual(len(fetched), 2)
            status[0] = 500
            verifier.fetched -= 301
            self.assertFalse(await verifier.verify(token('rotated')))
            self.assertFalse(await verifier.verify(token('rotated')))
            self.assertEqual(len(fetched), 3)


if __name__ == '__main__':
    unittest.main()
