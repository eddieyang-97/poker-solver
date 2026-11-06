"""Exact target caching, portable pure responses and independent bounded replay.

Only frozen one-bid target probabilities are cached. Response decisions and
opponent-hand masses continue to use complete public histories.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from types import MappingProxyType

import numpy as np

from game import Game
from one_face import OneFace
from recall_training import RecallPolicy


class CachedRecallModel:
    def __init__(self,target):
        if type(target) is not RecallPolicy or target.layout.graph.recall != 1:
            raise ValueError('Only a validated frozen one-bid policy may use this cache')
        self.target=target
        graph=target.layout.graph
        representatives={0:()}
        entries=[]
        for i,(p,_) in enumerate(graph.keys):
            history=representatives[i]
            for a,child in zip(graph.actions[i],graph.children[i]):
                if child is not None: representatives.setdefault(child,history+(a,))
            entries.append(MappingProxyType(target.actions(p,history)))
        self.entries=tuple(entries)

    def actions(self,player,history):
        if player != len(history)%2: raise ValueError('Wrong target seat')
        graph=self.target.layout.graph
        return self.entries[graph.index[graph.key(player,history)]]


def game_tag(game):
    if type(game) is Game: return {'kind':'house','rules':asdict(game.rules)}
    if type(game) is OneFace: return {'kind':'one-face','maximum':game.maximum}
    raise ValueError('Only declared house/one-face games supported')


class ResponsePlan:
    """Frozen pure choices: full public history plus own private hand only."""
    def __init__(self,game,seat,decisions,target_sha256):
        game_tag(game)
        if type(seat) is not int or seat not in (0,1): raise ValueError('Seat 0/1 required')
        if not isinstance(target_sha256,str) or len(target_sha256)!=64 or any(c not in '0123456789abcdef' for c in target_sha256):
            raise ValueError('Target probability fingerprint required')
        self.game,self.seat,self.target_sha256=game,seat,target_sha256
        result={}
        for history,choices in decisions.items():
            if not isinstance(history,tuple) or len(history)%2 != seat: raise ValueError('Wrong response history')
            prefix=()
            for a in history:
                if type(a) is not int or a==-1 or a not in game.actions(prefix): raise ValueError('Illegal public history')
                prefix+=(a,)
            if len(choices)!=len(game.hands) or any(type(a) is not int or a not in game.actions(history) for a in choices):
                raise ValueError('Illegal private-hand response choices')
            row=np.array(choices,dtype=np.int64);row.flags.writeable=False
            result[history]=row
        self.decisions=MappingProxyType(result)

    @classmethod
    def from_search(cls,search,target_sha256):
        if search.result is None: raise ValueError('Solve the response first')
        return cls(search.game,search.seat,{h:a.tolist() for h,a in search.decisions.items()},target_sha256)

    def choices(self,player,history):
        if player!=self.seat or player!=len(history)%2: raise ValueError('Wrong responder seat')
        if history in self.decisions: return self.decisions[history]
        return np.full(len(self.game.hands),-1 if history else self.game.actions(())[0],dtype=int)

    def policy(self,player,hand,history):
        if type(hand) is not int or not 0<=hand<len(self.game.hands): raise ValueError('Invalid own hand')
        chosen=self.choices(player,history)[hand]
        return [float(a==chosen) for a in self.game.actions(history)]

    def save(self,path):
        result={'format':'full-history-response-v1','game':game_tag(self.game),'seat':self.seat,
                'target_probabilities_sha256':self.target_sha256,
                'decisions':[{'history':list(h),'choices':a.tolist()} for h,a in sorted(self.decisions.items(),key=lambda x:(len(x[0]),x[0]))]}
        data=json.dumps(result,sort_keys=True,separators=(',',':')).encode()+b'\n'
        Path(path).write_bytes(data)
        return {'file':Path(path).name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'decision_nodes':len(self.decisions)}

    @classmethod
    def load(cls,game,path,target_sha256):
        data=json.loads(Path(path).read_text())
        if (set(data)!={'format','game','seat','target_probabilities_sha256','decisions'}
                or data['format']!='full-history-response-v1' or data['game']!=game_tag(game)
                or data['target_probabilities_sha256']!=target_sha256): raise ValueError('Incompatible response plan')
        choices={}
        for row in data['decisions']:
            if set(row)!={'history','choices'}: raise ValueError('Invalid response entry')
            history=tuple(row['history'])
            if history in choices: raise ValueError('Duplicate response history')
            choices[history]=row['choices']
        return cls(game,data['seat'],choices,target_sha256)


def raw_columns(game):
    """Independent raw-dice scoring; never reads search guide/count tables."""
    if type(game) is OneFace:
        return {a:np.array(game.hands) for a in game.actions(())}, {a:a for a in game.actions(())}
    if type(game) is not Game: raise ValueError('Unsupported replay game')
    dice=np.array(game.hands)
    ones=(dice==1).sum(axis=1)
    result={}
    for a,b in enumerate(game.bids):
        hits=(dice==b.face).sum(axis=1)
        if b.face==1: value=hits.copy()
        elif b.mode=='fly':
            value=hits+ones
            value=np.where(value==5,6,value)
            value=np.where(ones==5,7 if game.rules.all_ones_wild_seven else 6,value)
        else:
            value=hits.copy()
            if game.rules.zhai_mixed_bonus: value=np.where((hits>0)&(hits+ones==5),6,value)
        result[a]=np.where(hits==5,7,value)
    return result,{a:b.quantity for a,b in enumerate(game.bids)}


class ReplayLimit(RuntimeError):
    def __init__(self,stats,wall,cpu):
        super().__init__('Exact replay budget exceeded; no value produced')
        self.stats,self.wall_seconds,self.cpu_seconds=stats.copy(),wall,cpu


def exact_response_value(game,target,plan,node_limit=200000,seconds=20):
    """Enumerate weighted chance/public actions in float64; abort, never truncate.

    Terminal 8x8 count-pair sums use independently scored raw dice. Target rows
    are reconstructed through the scalar policy API, not the search cache.
    Limits return no partial value; callers retain the failure and sampled check.
    """
    if (type(node_limit) is not int or node_limit<1 or not np.isfinite(seconds) or seconds<=0
            or plan.game is not game or target.game is not game): raise ValueError('Compatible objects and positive replay limits required')
    # The following target-row cache is sound only for this declared class.
    if type(target) is not RecallPolicy or target.layout.graph.recall!=1: raise ValueError('Frozen one-bid target required')
    if hashlib.sha256(target.data.astype('<f8').tobytes()).hexdigest()!=plan.target_sha256:
        raise ValueError('Replay target fingerprint differs')
    counts,quantities=raw_columns(game)
    truth={a:np.add.outer(np.arange(8),np.arange(8))>=q for a,q in quantities.items()}
    rows={};start=time.perf_counter();cpu=time.process_time()
    stats={'public_nodes':0,'terminals':0,'scalar_target_rows':0}
    def terminal(a,own,opp,challenging):
        first=np.bincount(counts[a],weights=own,minlength=8)
        second=np.bincount(counts[a],weights=opp,minlength=8)
        joint=first[:,None]*second[None,:]
        signed=2*float(joint[truth[a]].sum())-float(joint.sum())
        stats['terminals']+=1
        return -signed if challenging else signed
    def walk(history,own,opp):
        stats['public_nodes']+=1
        if stats['public_nodes']>node_limit or time.perf_counter()-start>seconds:
            raise ReplayLimit(stats,time.perf_counter()-start,time.process_time()-cpu)
        p=len(history)%2
        if p==plan.seat:
            chosen=plan.choices(p,history);total=0.
            for a in np.unique(chosen[own>0]):
                a=int(a);mass=own*(chosen==a)
                total+=terminal(history[-1],mass,opp,True) if a==-1 else walk(history+(a,),mass,opp)
            return total
        key=target.layout.graph.key(p,history)
        if key not in rows:
            legal=game.actions(history)
            table=np.array([target.policy(p,h,history) for h in range(len(game.hands))])
            rows[key]={a:table[:,j] for j,a in enumerate(legal) if table[:,j].any()}
            stats['scalar_target_rows']+=len(game.hands)
        total=0.
        for a,probability in rows[key].items():
            mass=opp*probability
            if not mass.any(): continue
            total+=terminal(history[-1],own,mass,False) if a==-1 else walk(history+(a,),own,mass)
        return total
    value=walk((),np.asarray(game.prior),np.asarray(game.prior))
    if not np.isfinite(value) or not -1-1e-12<=value<=1+1e-12: raise ArithmeticError('Invalid exact replay value')
    return {'value':float(value),'stats':stats,'wall_seconds':time.perf_counter()-start,
            'cpu_seconds':time.process_time()-cpu,'arithmetic':'float64 exhaustive weighted policy replay, not interval certified'}
