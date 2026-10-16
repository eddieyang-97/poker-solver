"""Small, exact-showdown, approximate-equilibrium heads-up *river* solver.

CFR+ for a restricted, no-raises game tree. No third-party poker engine.
This is a research/study tool, not an unrestricted NLHE equilibrium solver.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK = tuple(r + s for r in RANKS for s in SUITS)
RINDEX = {c: i + 2 for i, c in enumerate(RANKS)}
CARD_INDEX = {c: i for i,c in enumerate(DECK)}


def cards(text: str | list[str], n: int) -> tuple[str, ...]:
    if isinstance(text, str):
        value=text.strip()
        if re.fullmatch(r'(?:[2-9TJQKA][cdhs]){2}',value) and n==2:
            parts=[value[:2],value[2:]]
        else:
            parts = [p for p in re.split(r'[,\s]+', value) if p]
    else:
        parts = list(text)
    parts = [str(c).strip() for c in parts]
    if len(parts) != n or any(c not in CARD_INDEX for c in parts) or len(set(parts)) != n:
        raise ValueError(f'Expected {n} distinct cards, e.g. "Ks,9s,5h,Td,Ts"')
    return tuple(parts)


def combo_key(a: str,b: str) -> tuple[str,str]:
    return tuple(sorted((a,b), key=lambda s:CARD_INDEX[s]))


def expand_range(spec: str, board: tuple[str, ...]) -> dict[tuple[str,str],float]:
    """Expand AA, AKs, AKo, AK, exact AcKd, each with optional :weight in [0,1]."""
    if not spec.strip(): raise ValueError('Ranges must not be empty')
    result: dict[tuple[str,str],float] = {}
    dead = set(board)
    for raw in re.split(r'[,\s]+',spec.strip()):
        if not raw:continue
        tok,sep,weight = raw.partition(':')
        w=float(weight) if sep else 1.0
        if not (0 <= w <= 1):raise ValueError(f'Invalid weight {raw}')
        if re.fullmatch(r'[2-9TJQKA][cdhs][2-9TJQKA][cdhs]',tok):
            a,b=tok[:2],tok[2:]
            if a==b:raise ValueError(f'Repeated card in {tok}')
            combos=[combo_key(a,b)]
        elif re.fullmatch(r'[2-9TJQKA]{2}[so]?',tok):
            a,b=tok[:2]
            if RINDEX[a]<RINDEX[b]:raise ValueError(f'Hand ranks must descend: {tok}')
            typ=tok[2:] if len(tok)>2 else ''
            if a==b:
                if typ:raise ValueError(f'Pocket pairs do not take s/o: {tok}')
                combos=[combo_key(a+s,b+t) for s,t in itertools.combinations(SUITS,2)]
            else:
                combos=[combo_key(a+s,b+t) for s in SUITS for t in SUITS if (not typ or ((s==t)==(typ=='s')))]
        else:raise ValueError(f'Bad range token: {raw}')
        for c in combos:
            if not any(x in dead for x in c):result[c]=w
    result={k:v for k,v in result.items() if v>0}
    if not result:raise ValueError('Range has no legal positive-weight combos after board removal')
    return result


def straight_high(rank_set: set[int]) -> int:
    if 14 in rank_set:rank_set=rank_set|{1}
    for h in range(14,4,-1):
        if all(x in rank_set for x in range(h-4,h+1)):return h
    return 0


@lru_cache(maxsize=200000)
def rank7(cs: tuple[str,...]) -> tuple[int,...]:
    """Evaluate a 7-card poker hand as a comparable tuple (category 0..8)."""
    rs=[RINDEX[c[0]] for c in cs]
    by_suit={s:[RINDEX[c[0]] for c in cs if c[1]==s] for s in SUITS}
    for s,rr in by_suit.items():
        if len(rr)>=5:
            sf=straight_high(set(rr))
            if sf:return (8,sf)
    counts={r:rs.count(r) for r in set(rs)}
    quads=sorted((r for r,k in counts.items() if k>=4),reverse=True)
    if quads:return (7,quads[0],max(r for r in counts if r!=quads[0]))
    trips=sorted((r for r,k in counts.items() if k>=3),reverse=True)
    if trips:
        pairs=sorted((r for r,k in counts.items() if k>=2 and r!=trips[0]),reverse=True)
        if pairs:return (6,trips[0],pairs[0])
    for rr in by_suit.values():
        if len(rr)>=5:return (5,*sorted(rr,reverse=True)[:5])
    st=straight_high(set(rs))
    if st:return (4,st)
    if trips:
        kicks=sorted((r for r in rs if r!=trips[0]),reverse=True)[:2]
        return (3,trips[0],*kicks)
    pairs=sorted((r for r,k in counts.items() if k>=2),reverse=True)
    if len(pairs)>=2:
        return (2,pairs[0],pairs[1],max(r for r in counts if r not in pairs[:2]))
    if pairs:return (1,pairs[0],*sorted((r for r in rs if r!=pairs[0]),reverse=True)[:3])
    return (0,*sorted(rs,reverse=True)[:5])


@dataclass
class Node:
    name: str
    player: int
    actions: tuple[str,...]
    children: tuple[Any,...]
    n_hands: int
    regret: np.ndarray = field(init=False)
    avg_sum: np.ndarray = field(init=False)
    strat: np.ndarray = field(init=False)

    def __post_init__(self):
        self.regret=np.zeros((self.n_hands,len(self.actions)),dtype=float)
        self.avg_sum=np.zeros_like(self.regret)
        self.strat=np.full_like(self.regret,1/len(self.actions))

    def update_strategy(self):
        positive=np.maximum(self.regret,0)
        s=positive.sum(axis=1,keepdims=True)
        np.divide(positive,s,out=self.strat,where=s>0)
        self.strat[s[:,0]==0,:]=1/len(self.actions)

    def average(self):
        s=self.avg_sum.sum(axis=1,keepdims=True)
        out=np.full_like(self.avg_sum,1/len(self.actions))
        np.divide(self.avg_sum,s,out=out,where=s>0)
        return out


def tree(n0:int,n1:int,pot:float,stack:float,sizes:list[float]) -> Node:
    def terminal(kind:str,amount:float=0):return (kind,amount)
    ip_choices=[]
    for b in sizes:
        amt=min(stack, b*pot)
        ip_choices.append(Node(f'ip_facing_oop_bet_{b:g}',1,('fold','call'),
            (terminal('ip_folds'),terminal('showdown',amt)),n1))
    oop_choices=[]
    for b in sizes:
        amt=min(stack, b*pot)
        oop_choices.append(Node(f'oop_facing_ip_bet_{b:g}',0,('fold','call'),
            (terminal('oop_folds'),terminal('showdown',amt)),n0))
    after_check=Node('ip_after_oop_check',1,('check',)+tuple(f'bet_{b:g}pot' for b in sizes),
        (terminal('showdown',0),)+tuple(oop_choices),n1)
    return Node('oop_first',0,('check',)+tuple(f'bet_{b:g}pot' for b in sizes),
                (after_check,)+tuple(ip_choices),n0)


class RiverSolver:
    def __init__(self,board: str,oop_range: str,ip_range: str,pot:float,stack:float,
                 bet_sizes:list[float]|None=None):
        self.board=cards(board,5)
        if pot<=0 or stack<=0:raise ValueError('Pot and stack must be positive')
        self.pot=float(pot);self.stack=float(stack)
        self.sizes=bet_sizes if bet_sizes is not None else [0.5,1.0]
        if not 1<=len(self.sizes)<=3 or any(not 0 < b <= 3 for b in self.sizes) or len(set(self.sizes))!=len(self.sizes):
            raise ValueError('Provide 1-3 distinct bet sizes as pot fractions in (0,3]')
        if any(b*self.pot>=self.stack for b in self.sizes) and len({min(self.stack,b*self.pot) for b in self.sizes})!=len(self.sizes):
            raise ValueError('Multiple bet sizes collapse to identical all-ins')
        self.r0=expand_range(oop_range,self.board)
        self.r1=expand_range(ip_range,self.board)
        self.h0=list(self.r0);self.h1=list(self.r1)
        self.w0=np.array(list(self.r0.values()),dtype=float)
        self.w1=np.array(list(self.r1.values()),dtype=float)
        self.valid=np.array([[not (set(a)&set(b)) for b in self.h1] for a in self.h0],dtype=np.float64)
        if not np.any(self.valid):raise ValueError('Ranges have no compatible hole-card pairs')
        scores0=[rank7(tuple(sorted(self.board+c))) for c in self.h0]
        scores1=[rank7(tuple(sorted(self.board+c))) for c in self.h1]
        # Cached 7-card ranks are sortable tuples; map to a comparable ordinal.
        order={score:i for i,score in enumerate(sorted(set(scores0+scores1)))}
        x=np.array([order[s] for s in scores0],dtype=np.int32)
        y=np.array([order[s] for s in scores1],dtype=np.int32)
        self.sign=np.sign(x[:,None]-y[None,:]).astype(np.float64)*self.valid
        self.prob=float(self.w0@self.valid@self.w1)
        self.root=tree(len(self.h0),len(self.h1),self.pot,self.stack,self.sizes)
        self.nodes={}
        def walk(n):
            if isinstance(n,Node):
                self.nodes[n.name]=n
                for c in n.children:walk(c)
        walk(self.root)

    def _terminal(self,t:tuple[str,float],r0:np.ndarray,r1:np.ndarray):
        kind,b=t
        if kind=='showdown':
            half=self.pot/2+b
            return half*(self.sign@r1), -half*(self.sign.T@r0)
        if kind=='ip_folds':
            half=self.pot/2
            return half*(self.valid@r1),-half*(self.valid.T@r0)
        if kind=='oop_folds':
            half=-self.pot/2
            return half*(self.valid@r1),-half*(self.valid.T@r0)
        raise AssertionError(kind)

    def _recurse(self,node: Node | tuple[str,float],r0:np.ndarray,r1:np.ndarray,iteration:int):
        if not isinstance(node,Node):return self._terminal(node,r0,r1)
        own_reach=r0 if node.player==0 else r1
        s=node.strat
        node.avg_sum+=iteration*own_reach[:,None]*s
        child=[]
        for a,c in enumerate(node.children):
            if node.player==0:
                child.append(self._recurse(c,r0*s[:,a],r1,iteration))
            else:
                child.append(self._recurse(c,r0,r1*s[:,a],iteration))
        if node.player==0:
            # actor counterfactual: own action reach must be omitted; child values are with own reach multiplied
            # Recompute each actor action with a unit reach at the actor node by eliminating the local action weight.
            # Since all terminal cfvs0 omit own reach, those child cfvs0 are already action values.
            vals=np.stack([v[0] for v in child],axis=1)
            mixed=(vals*s).sum(axis=1)
            node.regret=np.maximum(0,node.regret+vals-mixed[:,None])
            return mixed, np.sum([v[1] for v in child],axis=0)
        vals=np.stack([v[1] for v in child],axis=1)
        mixed=(vals*s).sum(axis=1)
        node.regret=np.maximum(0,node.regret+vals-mixed[:,None])
        return np.sum([v[0] for v in child],axis=0),mixed

    def _eval(self,node,r0,r1,best_response:int|None=None,collect:dict|None=None):
        if not isinstance(node,Node):return self._terminal(node,r0,r1)
        strat=node.average()
        results=[]
        for a,c in enumerate(node.children):
            if node.player==0:
                results.append(self._eval(c,r0*strat[:,a],r1,best_response,collect))
            else:
                results.append(self._eval(c,r0,r1*strat[:,a],best_response,collect))
        if collect is not None:
            actor_values=np.stack([v[node.player] for v in results],axis=1)
            opponent_reach=(self.valid@r1 if node.player==0 else self.valid.T@r0)
            action_values=np.divide(actor_values, opponent_reach[:,None],
                                    out=np.full_like(actor_values,np.nan), where=opponent_reach[:,None]>1e-14)
            collect[node.name]={'ev': action_values, 'own_reach': r0 if node.player==0 else r1,
                                'opponent_reach': opponent_reach}
        if node.player==0:
            actor=np.stack([v[0] for v in results],axis=1)
            res0=actor.max(axis=1) if best_response==0 else (actor*strat).sum(axis=1)
            return res0, np.sum([v[1] for v in results],axis=0)
        actor=np.stack([v[1] for v in results],axis=1)
        res1=actor.max(axis=1) if best_response==1 else (actor*strat).sum(axis=1)
        return np.sum([v[0] for v in results],axis=0),res1

    def solve(self,iterations:int=500,oop_hand:str|None=None,ip_hand:str|None=None):
        if not 20<=iterations<=10000:raise ValueError('Iterations must be between 20 and 10000')
        for t in range(1,iterations+1):
            for n in self.nodes.values():n.update_strategy()
            self._recurse(self.root,self.w0,self.w1,t)
        node_values={}
        values=self._eval(self.root,self.w0,self.w1,collect=node_values)
        br0=self._eval(self.root,self.w0,self.w1,0)[0]
        br1=self._eval(self.root,self.w0,self.w1,1)[1]
        game_ev=float(self.w0@values[0]/self.prob)
        gap=float((self.w0@br0+self.w1@br1)/self.prob)
        out={'model':'two-player zero-sum, fixed river ranges, no raises, no rake',
             'board':list(self.board),'pot':self.pot,'stack':self.stack,'bet_sizes':self.sizes,
             'iterations':iterations,'range_combos':{'oop':len(self.h0),'ip':len(self.h1)},
             'root_ev_oop_relative_to_split_pot':round(game_ev,4),
             'nash_conv_chips':round(max(0,gap),4),
             'nash_conv_pct_pot':round(max(0,gap)/self.pot*100,3),
             'interpretation':'EVs are relative to receiving half the starting pot. Max regrets / EV exploitability depend on the restricted tree.'}
        queried=[('oop',oop_hand,self.h0,0),('ip',ip_hand,self.h1,1)]
        out['hands']={}
        for label,text,hands,side in queried:
            if not text:continue
            cs=cards(text,2)
            key=combo_key(*cs)
            if key not in hands:raise ValueError(f'{label} hand {text} not in supplied starting range')
            idx=hands.index(key)
            nodeout={}
            for n in self.nodes.values():
                if n.player!=side:continue
                strat=n.average()[idx]
                av=node_values[n.name]['ev'][idx]
                ownr=node_values[n.name]['own_reach'][idx]
                reach=ownr/(self.w0[idx] if side==0 else self.w1[idx])
                nodeout[n.name]={
                    'frequency':{action:round(float(freq),4) for action,freq in zip(n.actions,strat)},
                    'action_ev_relative_to_half_pot':{
                        action:(round(float(ev),4) if np.isfinite(ev) else None)
                        for action,ev in zip(n.actions,av)},
                    'own_reach_probability':round(float(reach),4),
                }
            out['hands'][label]={'combo':list(key),'node_strategy':nodeout}
        return out


def evaluate_river_call(board:str,hero_hand:str,villain_betting_range:str,
                        pot:float,bet:float)->dict:
    """Exact call/fold equity and incremental EV against a *provided* betting range.

    pot = amount before villain's river bet. bet = amount hero must call.
    No range-inference or equilibrium calculation is performed here.
    """
    b=cards(board,5);h=cards(hero_hand,2)
    if set(h)&set(b):raise ValueError('Hero shares a card with the board')
    if pot<=0 or bet<=0:raise ValueError('Pot and bet must be positive')
    hands=expand_range(villain_betting_range,b)
    compatible={c:w for c,w in hands.items() if not (set(c)&set(h))}
    if not compatible:raise ValueError('No opponent combos remain after blocking with hero hand')
    hero_score=rank7(tuple(sorted(b+h)))
    weights=sum(compatible.values())
    equity=0.0; wins=0.0;ties=0.0
    for combo,w in compatible.items():
        villain_score=rank7(tuple(sorted(b+combo)))
        if hero_score>villain_score:wins+=w
        elif hero_score==villain_score:ties+=w
    equity=(wins+0.5*ties)/weights
    threshold=float(bet/(pot+2*bet))
    ev=float(equity*(pot+2*bet)-bet)
    return {
      'board':list(b),'hero_hand':list(h), 'pot_before_bet':pot,
      'villain_bet':bet,'caller_pot_odds':round(threshold,6),
      'hero_equity_vs_assumed_betting_range':round(equity,6),
      'ev_call_minus_fold':round(ev,4),
      'best_action_given_range':'call' if ev>1e-8 else 'fold' if ev<-1e-8 else 'indifferent',
      'opponent_combos_after_blockers':len(compatible),
      'weighted_opponent_combos_after_blockers':round(weights,3),
      'assumption':'Villain betting range is given exogenously; result is exact for that range, not solver-derived equilibrium.'
    }
