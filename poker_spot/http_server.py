"""Stateless official-SDK Streamable HTTP service; fail-closed OAuth authorization."""
import copy
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import SCOPE, Settings, Verifier
from .execution import CalculationError, Runner
from .mcp_server import CALL_TOOL, TOOL

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 16_384


def create_app(settings: Settings | None = None, runner: Runner | None = None):
    settings = settings or Settings.from_env()
    verifier = Verifier(settings)
    runner = runner or Runner()
    server = Server('poker-spot-study', version='0.2.0', instructions=(
        'Post-session heads-up river study only. Supply both complete weighted arrival ranges. '
        'Computed CFR results use a no-raise, no-rake restricted tree. Report NashConv and '
        'assumptions; never claim full GTO. For a checked river, inspect ip_after_oop_check.'))

    @server.list_tools()
    async def list_tools():
        definitions = copy.deepcopy([TOOL, CALL_TOOL])
        definitions[0]['inputSchema']['properties']['iterations']['maximum'] = 1500
        for definition in definitions:
            definition['securitySchemes'] = [{'type': 'oauth2', 'scopes': [SCOPE]}]
            definition['_meta'] = {'securitySchemes': definition['securitySchemes']}
        return [Tool(**definition) for definition in definitions]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        try:
            result = await runner.run(name, arguments)
            logger.info('calculation_completed tool=%s', name)
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(result))],
                                  structuredContent=result, isError=False)
        except CalculationError as exc:
            logger.info('calculation_failed code=%s', exc.code)
            error = {'code': exc.code, 'message': str(exc)}
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(error))],
                                  structuredContent={'error': error}, isError=True)
        except Exception:
            logger.error('calculation_failed code=internal_error')
            return CallToolResult(content=[TextContent(type='text', text='Internal calculation error')],
                                  structuredContent={'error': {'code': 'internal_error'}}, isError=True)

    host = urlsplit(settings.resource).netloc
    manager = StreamableHTTPSessionManager(
        server, stateless=True, json_response=True, max_request_body_size=MAX_BODY_BYTES,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host] if host else ['127.0.0.1:*', 'localhost:*', 'testserver'],
            allowed_origins=list(settings.origins)))

    class ProtectedMCP:
        async def __call__(self, scope, receive, send):
            request = Request(scope, receive)
            if not settings.configured:
                response = JSONResponse({'error': 'service_not_configured'}, status_code=503)
            elif not await verifier.verify(request.headers.get('authorization', '')):
                response = JSONResponse({'error': 'unauthorized'}, status_code=401,
                                        headers={'WWW-Authenticate': settings.challenge()})
            else:
                body_done = False

                async def bounded_receive():
                    nonlocal body_done
                    if body_done:
                        return await receive()
                    message = await asyncio.wait_for(receive(), timeout=10)
                    if message['type'] == 'http.request' and not message.get('more_body', False):
                        body_done = True
                    return message

                try:
                    return await manager.handle_request(scope, bounded_receive, send)
                except TimeoutError:
                    response = JSONResponse({'error': 'request_body_timeout'}, status_code=408)
            await response(scope, receive, send)

    async def health(request):
        return JSONResponse({'status': 'ok', 'auth_configured': settings.configured,
                             'engine': 'river-only', 'version': '0.2.0'})

    async def ready(request):
        return JSONResponse({'status': 'ready' if settings.configured else 'unconfigured'},
                            status_code=200 if settings.configured else 503)

    async def metadata(request):
        if not settings.resource:
            return JSONResponse({'error': 'oauth_not_configured'}, status_code=503)
        return JSONResponse({'resource': settings.resource,
                             'authorization_servers': [settings.issuer],
                             'scopes_supported': [SCOPE], 'bearer_methods_supported': ['header']})

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    app = Starlette(lifespan=lifespan, routes=[
        Route('/health', health), Route('/ready', ready),
        Route('/.well-known/oauth-protected-resource', metadata),
        Route('/.well-known/oauth-protected-resource/mcp', metadata),
        Route('/mcp', ProtectedMCP(), methods=['GET', 'POST', 'DELETE']),
    ])
    app.state.verifier = verifier
    app.state.runner = runner
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins),
                       allow_methods=['GET', 'POST', 'DELETE'],
                       allow_headers=['Authorization', 'Content-Type', 'MCP-Protocol-Version'],
                       expose_headers=['WWW-Authenticate', 'MCP-Protocol-Version'])
    return app


app = create_app()
