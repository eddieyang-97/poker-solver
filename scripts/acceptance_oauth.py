"""Interactive hosted OAuth/PKCE diagnostic with the official MCP client.

No tokens, codes, verifier, password or client secret are saved or printed.
The verified owner subject is saved in ignored .data/ for operator allowlisting.
The public client's only callback must be http://127.0.0.1:8733/callback.
"""
import asyncio
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata

from smoke_hosted import smoke

CALLBACK = 'http://127.0.0.1:8733/callback'


async def main():
    resource = os.environ['POKER_RESOURCE']
    issuer = os.environ['POKER_OAUTH_ISSUER']
    client_id = os.environ['POKER_OAUTH_CLIENT_ID']
    if not all(urlsplit(url).scheme == 'https' for url in (resource, issuer)):
        raise ValueError('HTTPS required')
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(issuer.rstrip('/')+'/.well-known/openid-configuration')
        response.raise_for_status()
        discovery = response.json()
    if discovery['issuer'] != issuer or 'S256' not in discovery.get('code_challenge_methods_supported', []):
        raise ValueError('Issuer mismatch or missing S256 support')
    expected_origin = urlsplit(issuer).netloc
    for field in ('jwks_uri', 'authorization_endpoint', 'token_endpoint'):
        if urlsplit(discovery[field]).scheme != 'https' or urlsplit(discovery[field]).netloc != expected_origin:
            raise ValueError('Unexpected provider endpoint origin')
    received = Queue(maxsize=1)
    expected_state = ['']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # callback URLs contain authorization codes

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/done':
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Authorization returned. Return to the solver setup chat.')
                return
            args = parse_qs(url.query)
            state = args.get('state', [''])[0]
            valid = (url.path == '/callback' and bool(expected_state[0]) and bool(state)
                     and hmac.compare_digest(state, expected_state[0])
                     and args.get('iss', [issuer])[0] == issuer and not received.full())
            if not valid or 'code' not in args:
                self.send_response(400)
                self.end_headers()
                return
            received.put_nowait((args['code'][0], state))
            expected_state[0] = ''
            self.send_response(302)
            self.send_header('Location', '/done')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

    listener = HTTPServer(('127.0.0.1', 8733), Handler)
    thread = Thread(target=listener.serve_forever, daemon=True)
    thread.start()

    class Storage:
        tokens = None

        async def get_tokens(self):
            return self.tokens

        async def set_tokens(self, tokens):
            key = await asyncio.to_thread(
                jwt.PyJWKClient(discovery['jwks_uri'], timeout=5).get_signing_key_from_jwt,
                tokens.access_token)
            claims = jwt.decode(tokens.access_token, key.key, algorithms=['RS256', 'ES256'],
                                issuer=issuer, audience=resource,
                                options={'require': ['sub', 'exp', 'iat']})
            if 'poker:solve' not in claims.get('scope', '').split():
                raise ValueError('Poker permission missing from token')
            target = Path('.data/acceptance-owner-subject')
            target.parent.mkdir(exist_ok=True)
            target.write_text(claims['sub'], encoding='utf-8')
            print('Verified owner subject saved privately in .data/acceptance-owner-subject. '
                  'Allowlist it in Render, then redeploy. Tokens remain in memory only.', flush=True)
            self.tokens = tokens

        async def get_client_info(self):
            return OAuthClientInformationFull(client_id=client_id, **metadata.model_dump())

        async def set_client_info(self, info):
            raise ValueError('Only the pre-registered public acceptance client may be used')

    async def redirect(url):
        if not url.startswith(discovery['authorization_endpoint']+'?'):
            raise ValueError('Unexpected authorization endpoint')
        expected_state[0] = parse_qs(urlsplit(url).query)['state'][0]
        print('Open this authorization URL in the browser and inspect consent:\n'+url, flush=True)

    async def callback():
        try:
            return await asyncio.to_thread(received.get, True, 600)
        except Empty:
            raise TimeoutError('Authorization callback expired') from None

    metadata = OAuthClientMetadata(client_name='Poker hosted acceptance', redirect_uris=[CALLBACK],
                                   token_endpoint_auth_method='none', grant_types=['authorization_code'],
                                   response_types=['code'], scope='poker:solve')
    storage = Storage()
    provider = OAuthClientProvider(resource, metadata, storage, redirect, callback, timeout=600)
    try:
        async with httpx.AsyncClient(auth=provider, timeout=660) as client:
            response = await client.post(resource, json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                                         headers={'Accept': 'application/json, text/event-stream'})
        if storage.tokens is None:
            raise RuntimeError('OAuth did not issue verified tokens; ensure MCP challenges with 401')
        # Owner is initially denied by a bootstrap subject; wait for explicit operator allowlisting.
        token = storage.tokens.access_token
        async with httpx.AsyncClient(headers={'Authorization': f'Bearer {token}'}, timeout=60) as client:
            for _ in range(120):
                check = await client.post(resource, json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                                          headers={'Accept': 'application/json, text/event-stream'})
                if check.status_code == 200:
                    break
                await asyncio.sleep(5)
            else:
                raise TimeoutError('Owner allowlisting was not completed')
        await smoke(resource, token)
        print(json.dumps({'oauth': 'S256, exact issuer/audience/scope verified',
                          'hosted_tools': 'both passed', 'chatgpt': 'not tested by this script'}), flush=True)
    finally:
        storage.tokens = None
        listener.shutdown()
        listener.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    asyncio.run(main())
