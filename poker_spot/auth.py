"""OAuth resource-server checks. The external provider owns login, consent and PKCE."""
import asyncio
import hmac
import json
import os
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

import httpx
import jwt

SCOPE = 'poker:solve'


def https_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Expected an absolute HTTPS URL without credentials, query or fragment')
    return value


@dataclass(frozen=True)
class Settings:
    resource: str = ''
    issuer: str = ''
    jwks_url: str = ''
    subjects: frozenset[str] = frozenset()
    local_token: str = ''
    origins: tuple[str, ...] = ('https://chatgpt.com',)

    @classmethod
    def from_env(cls):
        local = os.getenv('POKER_MODE') == 'local' and not os.getenv('RENDER')
        if local:
            token = os.getenv('POKER_MCP_TOKEN', '')
            if len(token) < 32:
                return cls()
            return cls(local_token=token)
        values = [os.getenv(key, '') for key in ('POKER_RESOURCE', 'POKER_OAUTH_ISSUER', 'POKER_OAUTH_JWKS_URL')]
        if not all(values):
            return cls()
        resource, issuer, jwks = map(https_url, values)
        subjects = frozenset(x.strip() for x in os.getenv('POKER_ALLOWED_SUBJECTS', '').split(',') if x.strip())
        return cls(resource=resource, issuer=issuer, jwks_url=jwks, subjects=subjects)

    @property
    def configured(self):
        return bool(self.local_token or (self.resource and self.issuer and self.jwks_url and self.subjects))

    @property
    def metadata_url(self):
        url = urlsplit(self.resource)
        return f'{url.scheme}://{url.netloc}/.well-known/oauth-protected-resource'

    def challenge(self):
        if not self.resource:
            return 'Bearer'
        return f'Bearer resource_metadata="{self.metadata_url}", scope="{SCOPE}"'


class Verifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = {}
        self.fetched = -float('inf')
        self.lock = asyncio.Lock()

    async def verify(self, authorization: str) -> bool:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 8192:
            return False
        token = parts[1]
        if self.settings.local_token:
            return hmac.compare_digest(token.encode(), self.settings.local_token.encode())
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') not in ('RS256', 'ES256') or not isinstance(header.get('kid'), str):
                return False
            kid = header['kid']
            # Refresh on rotation, but never fetch on every attacker-selected kid.
            async with self.lock:
                age = monotonic() - self.fetched
                if age > 300 or (kid not in self.keys and age > 60):
                    self.fetched = monotonic()
                    self.keys = {}
                    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                        async with client.stream('GET', self.settings.jwks_url) as response:
                            response.raise_for_status()
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > 65536:
                                    return False
                    keys = json.loads(body)['keys']
                    self.keys = {key['kid']: jwt.PyJWK.from_dict(key) for key in keys
                                 if key.get('kty') in ('RSA', 'EC') and key.get('use', 'sig') == 'sig'}
            key = self.keys.get(kid)
            if key is None or key.algorithm_name != header['alg']:
                return False
            claims = jwt.decode(token, key.key, algorithms=[key.algorithm_name],
                                issuer=self.settings.issuer, audience=self.settings.resource,
                                options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
            scope = claims.get('scope', '')
            return (claims['sub'] in self.settings.subjects and isinstance(scope, str)
                    and SCOPE in scope.split())
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, httpx.HTTPError):
            return False
