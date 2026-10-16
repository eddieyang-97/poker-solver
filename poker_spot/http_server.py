"""Stateless Streamable HTTP MCP adapter for the restricted river study engine.

Uses JSON responses (not server-sent events). It supports the basic MCP methods
implemented by mcp_server.dispatch. This is a small integration adapter rather
than a full authorization / OAuth server.
"""
from __future__ import annotations

import asyncio
import hmac
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .core import cards, expand_range
from .mcp_server import dispatch

PROTOCOL_VERSION = "2025-06-18"
MAX_BODY_BYTES = 16_384
MAX_COMBOS_PER_SIDE = 180
MAX_COMPATIBLE_PAIR_UPPER_BOUND = 22_500
MAX_ITERATIONS = 1_500

app = FastAPI(title="Poker Solver MCP", docs_url=None, redoc_url=None, openapi_url=None)
_solve_slot = asyncio.Semaphore(1)


def _error(code: int, message: str, ident=None, status: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": ident,
                         "error": {"code": code, "message": message}},
                        status_code=status)


def _authorized(request: Request) -> bool:
    token = os.getenv("POKER_MCP_TOKEN", "")
    if not token:
        return False  # fail closed until deployment secret is configured
    supplied = request.headers.get("authorization", "")
    if not supplied.startswith("Bearer "):
        return False
    return hmac.compare_digest(supplied.removeprefix("Bearer "), token)


def _allowed_origin(request: Request) -> bool:
    # MCP clients often omit Origin. Browser-based callers that send it must be
    # explicitly allowlisted, mitigating DNS rebinding/cross-origin exposure.
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = {x.strip() for x in os.getenv("POKER_ALLOWED_ORIGINS", "").split(",") if x.strip()}
    return origin in allowed


def _validate_solver_request(message: dict) -> None:
    if message.get("method") != "tools/call":
        return
    call = message.get("params") or {}
    if call.get("name") != "solve_river":
        return
    args = call.get("arguments") or {}
    iterations = args.get("iterations", 700)
    if type(iterations) is not int or not 20 <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"iterations must be an integer in [20, {MAX_ITERATIONS}]")
    board = cards(args["board"], 5)
    n0 = len(expand_range(args["oop_range"], board))
    n1 = len(expand_range(args["ip_range"], board))
    if n0 > MAX_COMBOS_PER_SIDE or n1 > MAX_COMBOS_PER_SIDE or n0*n1 > MAX_COMPATIBLE_PAIR_UPPER_BOUND:
        raise ValueError("Range too large for the hosted MVP; narrow the supplied river ranges")


@app.get("/health")
async def health():
    if not os.getenv("POKER_MCP_TOKEN"):
        return JSONResponse({"status": "unconfigured"}, status_code=503)
    return {"status": "ok", "engine": "river-only", "version": "0.1.0"}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401,
                            headers={"WWW-Authenticate": "Bearer"})
    if not _allowed_origin(request):
        return JSONResponse({"error": "forbidden origin"}, status_code=403)
    if "application/json" not in request.headers.get("content-type", ""):
        return JSONResponse({"error": "content-type must be application/json"}, status_code=415)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse({"error": "request too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"error": "invalid content-length"}, status_code=400)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse({"error": "request too large"}, status_code=413)
    try:
        import json
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return _error(-32700, "Invalid JSON", status=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(-32600, "Invalid JSON-RPC request", status=400)
    if "id" not in message:
        # MCP initialized notifications / cancelled notifications do not need responses.
        return Response(status_code=202)
    ident = message["id"]
    try:
        _validate_solver_request(message)
        if message.get("method") == "tools/call" and (message.get("params") or {}).get("name") == "solve_river":
            # Prevent overlapping CPU-heavy CFR loops within a single worker.
            async with _solve_slot:
                result = await asyncio.to_thread(dispatch, message)
        else:
            result = await asyncio.to_thread(dispatch, message)
        return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": result},
                            headers={"MCP-Protocol-Version": PROTOCOL_VERSION})
    except (ValueError, KeyError, TypeError) as exc:
        if message.get("method") == "tools/call":
            result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
            return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": result})
        return _error(-32602, str(exc), ident)
    except Exception:
        # Never send stack traces over the network.
        return _error(-32603, "Internal server error", ident, status=500)


@app.get("/mcp")
async def mcp_get(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return Response(status_code=405, headers={"Allow": "POST"})
