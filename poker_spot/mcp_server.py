"""Minimal no-network MCP stdio adapter for Poker Spot (2025 JSON-RPC framing).

Dependencies: Python >=3.10 and numpy. The transport is newline-delimited
JSON-RPC 2.0, per MCP stdio. Emits *only* protocol messages to stdout.
"""
from __future__ import annotations

import json
import sys
from .validation import calculate

TOOL={
    'name':'solve_river',
    'description':(
      'Solve a simplified HEADS-UP NLHE RIVER subgame with weighted starting ranges. '
      'Returns computed CFR+ per-combo bet/check/call/fold frequencies and action EVs. '
      'Each player has check and up to three bet sizes; facing a bet, only fold or call '
      '(NO RAISES). Pot, effective remaining stack and ranges must describe the START '
      'of the river (not infer ranges from revealed showdown hands). No rake or earlier '
      'street solution. Strategy is an approximation in the supplied restricted tree; '
      'report NashConv and inputs. Never describe it as full GTO NLHE.'),
    'inputSchema':{
        'type':'object',
        'properties':{
            'board':{'type':'string','description':'Five river board cards e.g. Ks,9s,5h,Td,Ts'},
            'oop_range':{'type':'string','description':'Out-of-position weighted range, e.g. AA,AKs:0.75,KQo:0.5,AsJh. Relative starting weights.'},
            'ip_range':{'type':'string','description':'In-position weighted range. Same grammar.'},
            'pot':{'type':'number','exclusiveMinimum':0,'description':'Pot at the river BEFORE any bets.'},
            'stack':{'type':'number','exclusiveMinimum':0,'description':'Smaller remaining effective stack on the river.'},
            'bet_sizes':{'type':'array','items':{'type':'number','exclusiveMinimum':0,'maximum':3},'minItems':1,'maxItems':3,'description':'Bet fractions of starting river pot, e.g. [0.5,1.0]. Capped at effective stack.'},
            'oop_hand':{'type':'string','description':'Optional concrete out-of-position two cards, e.g. KdQd (must belong to oop_range).'},
            'ip_hand':{'type':'string','description':'Optional concrete in-position two cards, e.g. AsJh (must belong to ip_range).'},
            'iterations':{'type':'integer','minimum':20,'maximum':10000,'description':'CFR+ iterations; default 700. Run more if NashConv high.'},
        },
        'required':['board','oop_range','ip_range','pot','stack'],
        'additionalProperties':False,
    },
    'annotations':{'readOnlyHint':True, 'destructiveHint':False, 'openWorldHint':False}
}


CALL_TOOL={
    'name':'evaluate_river_call',
    'description':(
      'Compute exact river bluff-catch pot odds, equity and call-minus-fold EV against '
      'an explicitly assumed villain BETTING range with card removal. No equilibrium '
      'claim: outputs are conditional on the provided range. Useful when Hero faces '
      'a river bet and wants to test plausible value-to-bluff composition.'),
    'inputSchema':{
        'type':'object',
        'properties':{
            'board':{'type':'string','description':'Five board cards, e.g. Ks,9s,5h,Td,Ts'},
            'hero_hand':{'type':'string','description':'Hero concrete combo, e.g. KdQd'},
            'villain_betting_range':{'type':'string','description':'Villain betting range e.g. QJs,99:0.5,AsJh:0.25'},
            'pot':{'type':'number','exclusiveMinimum':0,'description':'Pot BEFORE villain bets'},
            'bet':{'type':'number','exclusiveMinimum':0,'description':'Villain river bet / amount to call'},
        },
        'required':['board','hero_hand','villain_betting_range','pot','bet'],
        'additionalProperties':False,
    },
    'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False}
}


def dispatch(req:dict):
    method=req.get('method')
    if method=='initialize':
        return {
          'protocolVersion':req.get('params',{}).get('protocolVersion','2025-06-18'),
          'serverInfo':{'name':'poker-spot-local','version':'0.1.0'},
          'capabilities':{'tools':{'listChanged':False}},
          'instructions': 'Study-only river CFR solver. Call solve_river using both players FULL plausible ranges, not revealed exact holdings alone. Report restricted tree and NashConv; distinguish computed model results from real-world GTO. Do not use for real-time play.'
        }
    if method=='ping':return {}
    if method=='tools/list':return {'tools':[TOOL,CALL_TOOL]}
    if method=='tools/call':
        params=req.get('params') or {}
        name=params.get('name')
        result=calculate(name,params.get('arguments') or {})
        return {'content':[{'type':'text','text':json.dumps(result)}], 'structuredContent':result, 'isError':False}
    if method in ('resources/list','prompts/list'):
        return {'resources':[]} if method=='resources/list' else {'prompts':[]}
    raise ValueError(f'Unsupported method: {method}')


def main():
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if 'id' not in request:continue  # notifications have no response
            ident=request['id']
            try:
                resp={'jsonrpc':'2.0','id':ident,'result':dispatch(request)}
            except Exception as exc:
                # Ordinary argument errors for a tool call are reported as tool errors.
                if request.get('method')=='tools/call':
                    resp={'jsonrpc':'2.0','id':ident,'result':{
                        'content':[{'type':'text','text':f'{type(exc).__name__}: {exc}'}],
                        'isError':True}}
                else:
                    resp={'jsonrpc':'2.0','id':ident,'error':{'code':-32603,'message':str(exc)}}
            sys.stdout.write(json.dumps(resp,separators=(',',':'))+'\n');sys.stdout.flush()
        except Exception as exc:
            print(f'Invalid MCP message: {exc}',file=sys.stderr)

if __name__=='__main__':main()
