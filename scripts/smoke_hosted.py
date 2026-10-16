"""Official SDK hosted smoke test. Supply an OAuth access token in the environment.

Never prints/saves the token. This verifies transport and calculations, not the
interactive login/PKCE flow or ChatGPT host. Do not pass an ID token.
"""
import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def smoke(url: str, token: str):
    if not url.startswith('https://'):
        raise ValueError('Hosted endpoint must use HTTPS')
    async with httpx.AsyncClient(headers={'Authorization': f'Bearer {token}'}, timeout=60) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                print('Connected:', initialized.serverInfo.name, initialized.protocolVersion)
                print('Tools:', [tool.name for tool in (await session.list_tools()).tools])
                result = await session.call_tool('evaluate_river_call', {
                    'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd',
                    'villain_betting_range': 'AsJs,AsJh:0.5', 'pot': 100, 'bet': 100})
                assert not result.isError, 'Hosted call failed'
                assert result.structuredContent['best_action_given_range'] == 'indifferent'
                solve = await session.call_tool('solve_river', {
                    'board': '2c,3d,4h,8s,9c', 'oop_range': 'KhKd', 'ip_range': 'AsAd,QhJd',
                    'pot': 100, 'stack': 100, 'bet_sizes': [1.0], 'iterations': 1500,
                    'ip_hand': 'QhJd', 'oop_hand': 'KhKd'})
                assert not solve.isError, 'Hosted solve failed'
                assert solve.structuredContent['nash_conv_pct_pot'] < 0.5
                print(json.dumps({'call': result.structuredContent, 'solve': solve.structuredContent}, indent=2))


if __name__ == '__main__':
    asyncio.run(smoke(os.environ['POKER_RESOURCE'], os.environ['POKER_ACCEPTANCE_TOKEN']))
