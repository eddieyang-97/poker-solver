"""Explicit Stage B startup and auth boundary; no production calls or credentials."""
import os
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.testclient import TestClient

from poker_spot.auth import Settings
from poker_spot.http_server import create_app, create_hosted_turn_pilot_app


SETTINGS = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                    jwks_url='https://identity.example/keys', subjects=frozenset({'owner'}))
HOSTED_ENV = {'RENDER': 'true', 'POKER_MODE': 'hosted'}
HEADERS = {'Accept': 'application/json, text/event-stream'}
LIST = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}


class HostedTurnTests(unittest.TestCase):
    def factory(self, settings=SETTINGS, env=HOSTED_ENV, platform='linux'):
        with patch.dict(os.environ, env, clear=True), \
                patch('poker_spot.http_server.sys.platform', platform), \
                patch.object(Settings, 'from_env', return_value=settings):
            return create_hosted_turn_pilot_app()

    def test_factory_fails_closed_outside_approved_hosted_configuration(self):
        for params in ({'env': {}}, {'env': {'RENDER': 'false', 'POKER_MODE': 'hosted'}},
                       {'env': {'RENDER': 'true', 'POKER_MODE': 'local'}},
                       {'platform': 'win32'}, {'platform': 'darwin'},
                       {'settings': Settings()},
                       {'settings': Settings(local_token='local-canary-token-at-least-32-characters')}):
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, 'Render Linux'):
                self.factory(**params)
        app = self.factory()
        self.assertEqual(app.state.runner.timeout, 20)
        self.assertEqual(app.state.runner.rate, 30)
        self.assertTrue(app.state.runner.turn_pilot)
        self.assertEqual(app.state.verifier.settings, SETTINGS)

    def test_default_and_local_entry_points_remain_separate_on_render(self):
        with patch.dict(os.environ, HOSTED_ENV), \
                patch.object(Settings, 'from_env', return_value=SETTINGS):
            with self.assertRaisesRegex(ValueError, 'local only'):
                create_app(turn_pilot=True)
            app = create_app()
        self.assertFalse(app.state.runner.turn_pilot)
        with TestClient(app, base_url='https://poker.example') as client:
            self.assertEqual(client.get('/health').json()['engine'], 'river-only')

    def test_hosted_factory_uses_same_scope_allowlist_and_verifier_before_admission(self):
        app = self.factory()
        key = ec.generate_private_key(ec.SECP256R1())
        app.state.verifier.keys = {'test': jwt.PyJWK.from_json(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))}
        app.state.verifier.fetched = time.monotonic()
        payload = {'sub': 'owner', 'iss': SETTINGS.issuer, 'aud': SETTINGS.resource,
                   'iat': int(time.time()), 'exp': int(time.time())+120, 'scope': 'poker:solve'}

        def signed(changes=None, private=key):
            return jwt.encode(dict(payload, **(changes or {})), private, algorithm='ES256', headers={'kid': 'test'})

        with TestClient(app, base_url='https://poker.example', headers=HEADERS) as client:
            self.assertEqual(client.get('/health').json()['engine'], 'turn-pilot-v1')
            self.assertEqual(client.get('/ready').status_code, 200)
            metadata = client.get('/.well-known/oauth-protected-resource').json()
            self.assertEqual(metadata['resource'], SETTINGS.resource)
            self.assertEqual(metadata['scopes_supported'], ['poker:solve'])
            self.assertEqual(client.post('/mcp', json=LIST).status_code, 401)
            call = dict(LIST, method='tools/call', params={'name': 'solve_turn_v1', 'arguments': {}})
            for changes in ({'sub': 'other'}, {'iss': 'https://other.example/'},
                            {'aud': 'https://other.example/mcp'}, {'scope': 'other:scope'}, {'exp': 1}):
                with self.subTest(changes=changes):
                    self.assertEqual(client.post('/mcp', json=call,
                        headers={'Authorization': 'Bearer '+signed(changes)}).status_code, 401)
            self.assertEqual(client.post('/mcp', json=call, headers={'Authorization': 'Bearer '+signed(
                private=ec.generate_private_key(ec.SECP256R1()))}).status_code, 401)
            self.assertFalse(app.state.runner.starts)
            self.assertFalse(app.state.runner.busy)
            response = client.post('/mcp', json=LIST, headers={'Authorization': 'Bearer '+signed()})
            tools = response.json()['result']['tools']
            self.assertEqual({tool['name'] for tool in tools},
                             {'solve_river', 'evaluate_river_call', 'solve_turn_v1'})
            self.assertTrue(all(tool['securitySchemes'] == [{'type': 'oauth2', 'scopes': ['poker:solve']}]
                                for tool in tools))
            self.assertNotIn('LOCAL', next(t['description'] for t in tools if t['name'] == 'solve_turn_v1'))
            request = json.loads((Path(__file__).resolve().parents[1]/'examples/turn-pilot.json').read_text())
            reply = client.post('/mcp', json=dict(call, params={'name': 'solve_turn_v1', 'arguments': request}),
                                headers={'Authorization': 'Bearer '+signed()}).json()['result']
            self.assertFalse(reply['isError'], reply)
            self.assertEqual(reply['structuredContent']['status'], 'computed')
            self.assertEqual(reply['structuredContent']['source'], 'computed_on_demand')
            self.assertEqual(len(reply['structuredContent']['views']), len(request['views']))
            self.assertLess(len(json.dumps(reply).encode()), 65_536)


if __name__ == '__main__':
    unittest.main()
