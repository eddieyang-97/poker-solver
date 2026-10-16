"""Official MCP client -> HTTP app -> OAuth verifier -> real worker -> solver."""
import time
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from poker_spot.auth import Settings
from poker_spot.http_server import create_app


class SDKIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_tools_roundtrip(self):
        private = ec.generate_private_key(ec.SECP256R1())
        settings = Settings(resource='https://poker.example/mcp', issuer='https://identity.example/',
                            jwks_url='https://identity.example/keys', subjects=frozenset({'owner'}))
        app = create_app(settings)
        app.state.verifier.keys = {'test': jwt.PyJWK.from_json(
            jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))}
        app.state.verifier.fetched = time.monotonic()
        token = jwt.encode({'sub': 'owner', 'iss': settings.issuer, 'aud': settings.resource,
                            'iat': int(time.time()), 'exp': int(time.time())+60,
                            'scope': 'poker:solve'}, private, algorithm='ES256', headers={'kid': 'test'})
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        headers={'Authorization': f'Bearer {token}'}) as client:
                async with streamable_http_client(settings.resource, http_client=client) as (read, write, session_id):
                    async with ClientSession(read, write) as session:
                        initialized = await session.initialize()
                        self.assertEqual(initialized.serverInfo.name, 'poker-spot-study')
                        self.assertIsNone(session_id())
                        listed = await session.list_tools()
                        self.assertEqual({t.name for t in listed.tools}, {'solve_river', 'evaluate_river_call'})
                        call = await session.call_tool('evaluate_river_call', {
                            'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd',
                            'villain_betting_range': 'AsJs,AsJh:0.5', 'pot': 100, 'bet': 100})
                        self.assertFalse(call.isError)
                        self.assertEqual(call.structuredContent['best_action_given_range'], 'indifferent')
                        solve = await session.call_tool('solve_river', {
                            'board': '2c,3d,4h,8s,9c', 'oop_range': 'KhKd', 'ip_range': 'AsAd,QhJd',
                            'pot': 100, 'stack': 100, 'bet_sizes': [1.0], 'iterations': 1500,
                            'ip_hand': 'QhJd', 'oop_hand': 'KhKd'})
                        self.assertFalse(solve.isError)
                        self.assertLess(solve.structuredContent['nash_conv_pct_pot'], 0.5)
                        invalid = await session.call_tool('solve_river', {'board': 'bad'})
                        self.assertTrue(invalid.isError)
                        self.assertEqual(invalid.structuredContent['error']['code'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
