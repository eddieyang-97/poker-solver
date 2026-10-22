"""Isolated release gate tests: never contact Render or request credentials."""
import unittest

import httpx

from scripts.smoke_release import ReleaseSmokeError, smoke_release


SHA = 'a'*40
ORIGIN = 'https://poker.example'


def response_for(request, *, commit=SHA, health=200, ready=200, mcp=401,
                 redirect=False, auth='Bearer resource_metadata="https://poker.example/.well-known/oauth-protected-resource"'):
    path = request.url.path
    if path == '/health':
        if redirect:
            return httpx.Response(302, headers={'Location': 'https://other.example/'})
        return httpx.Response(health, json={'status': 'ok', 'auth_configured': True,
                                           'engine': 'river-only', 'version': '0.2.0',
                                           'deployment': {'commit': commit}})
    if path == '/ready':
        return httpx.Response(ready, json={'status': 'ready' if ready == 200 else 'unconfigured'})
    if path == '/mcp':
        return httpx.Response(mcp, json={'error': 'unauthorized'},
                              headers={'WWW-Authenticate': auth})
    raise AssertionError('Unexpected outbound path: ' + path)


class ReleaseSmokeTests(unittest.TestCase):
    def make_client(self, **kwargs):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, 'authorization' in request.headers))
            return response_for(request, **kwargs)
        return httpx.Client(transport=httpx.MockTransport(handler)), seen

    def test_matching_sha_auth_boundary_and_only_three_safe_gets(self):
        with self.make_client()[0] as client:
            output = smoke_release(ORIGIN, SHA, client=client)
        self.assertEqual(output['commit'], SHA)
        self.assertEqual(output['mcp_unauthenticated'], 401)
        client, seen = self.make_client()
        with client:
            smoke_release(ORIGIN, SHA, client=client)
        self.assertEqual(seen, [('GET', '/health', False), ('GET', '/ready', False),
                                ('GET', '/mcp', False)])

    def test_rejects_invalid_target_and_expected_sha_without_network(self):
        for origin in ('http://poker.example', 'https://user:password@poker.example',
                       'https://poker.example/mcp', 'https://poker.example?token=value',
                       'https://poker.example/', 'javascript:alert(1)'):
            with self.subTest(origin=origin), self.assertRaises(ReleaseSmokeError):
                smoke_release(origin, SHA)
        for sha in ('', SHA[:-1], SHA+'1', SHA.upper(), 'not-a-sha'):
            with self.subTest(sha=sha), self.assertRaises(ReleaseSmokeError):
                smoke_release(ORIGIN, sha)

    def test_rejects_wrong_or_missing_sha_and_unready_service(self):
        for params in ({'commit': 'b'*40}, {'commit': None}, {'health': 503},
                       {'ready': 503}, {'mcp': 200}, {'auth': ''}, {'redirect': True}):
            with self.subTest(params=params):
                client, _ = self.make_client(**params)
                with client, self.assertRaises(ReleaseSmokeError):
                    smoke_release(ORIGIN, SHA, client=client)

    def test_no_response_body_or_private_data_in_error(self):
        def handler(request):
            return httpx.Response(503, text='private-service-debug-secret')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ReleaseSmokeError) as error:
                smoke_release(ORIGIN, SHA, client=client)
        self.assertNotIn('private-service-debug-secret', str(error.exception))


if __name__ == '__main__':
    unittest.main()
