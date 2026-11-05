"""Chance-sampled cumulative graph CFR with exact hands and one-bid recall.

Each pass enumerates ALL public graph edges with fixed policies and samples only
the independent private deal. Expected increments equal exact-deal graph CFR.
No imperfect-recall equilibrium guarantee is implied.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random

import numpy as np

from fixed_strategy import PublicGraph


class Layout:
    def __init__(self, game):
        self.game = game
        self.graph = PublicGraph(game,1)
        self.offsets = np.cumsum([0]+[len(a)*len(game.hands) for a in self.graph.actions])
        self.entries = int(self.offsets[-1])
        self.children = [np.array([-1 if c is None else c for c in row]) for row in self.graph.children]
        self.players = [p for p,_ in self.graph.keys]

    def row(self, data, node, hand):
        width = len(self.graph.actions[node])
        start = self.offsets[node]+hand*width
        return data[start:start+width]


class RecallTrainer:
    def __init__(self, game, seed=490011, max_bytes=128*1024**2):
        self.layout = Layout(game)
        self.game = game
        self.array_bytes = self.layout.entries*16
        if type(max_bytes) is not int or max_bytes < self.array_bytes:
            raise MemoryError('Regret/average array budget exceeded before allocation')
        self.regret = np.zeros(self.layout.entries)
        self.average = np.zeros_like(self.regret)
        self.rng = random.Random(seed)
        self.visits = np.zeros((2,len(game.hands)),dtype=np.int64)
        self.iterations = 0
        self.maximum_reach = 0.

    def increments(self, hands):
        if len(hands) != 2 or any(type(h) is not int or not 0 <= h < len(self.game.hands) for h in hands):
            raise ValueError('Two valid private hand indices required')
        layout, graph = self.layout, self.layout.graph
        policies = []
        for i,p in enumerate(layout.players):
            row = layout.row(self.regret,i,hands[p]).clip(0)
            total = row.sum()
            policies.append(row/total if total else np.full(len(row),1/len(row)))
        reach = np.zeros((2,len(graph.keys)))
        reach[:,0] = 1
        for i,p in enumerate(layout.players):
            children = layout.children[i]
            keep = children >= 0
            # Destinations within one node are unique. Across nodes these adds
            # sum all abstracted paths, including zero-policy own branches.
            dest = children[keep]
            reach[p,dest] += reach[p,i]*policies[i][keep]
            reach[1-p,dest] += reach[1-p,i]
        values = np.zeros(len(graph.keys))
        delta, averages = [None]*len(values), [None]*len(values)
        for i in reversed(range(len(values))):
            p, history = graph.keys[i]
            children = layout.children[i]
            child = values[np.maximum(children,0)].copy()
            if history:
                child[children < 0] = self.game.payoff(history,hands,p)
            value = float(policies[i]@child)
            values[i] = value
            delta[i] = (1 if p == 0 else -1)*reach[1-p,i]*(child-value)
            averages[i] = reach[p,i]*policies[i]
        if not np.isfinite(reach).all() or not np.isfinite(values).all():
            raise ArithmeticError('Nonfinite graph pass')
        return delta, averages, float(values[0]), float(reach.max())

    def step(self, hands=None):
        hands = tuple(self.rng.choices(range(len(self.game.hands)),weights=self.game.prior,k=2)) if hands is None else hands
        delta, averages, value, reach = self.increments(hands)
        for i,p in enumerate(self.layout.players):
            r = self.layout.row(self.regret,i,hands[p])
            a = self.layout.row(self.average,i,hands[p])
            r += delta[i]
            a += averages[i]
            if not np.isfinite(r).all() or not np.isfinite(a).all():
                raise ArithmeticError('Nonfinite cumulative update')
        for p,h in enumerate(hands):
            self.visits[p,h] += 1
        self.maximum_reach = max(self.maximum_reach,reach)
        self.iterations += 1
        return value

    def freeze(self):
        data = self.average.copy()
        for i in range(len(self.layout.graph.keys)):
            rows = data[self.layout.offsets[i]:self.layout.offsets[i+1]].reshape(len(self.game.hands),-1)
            total = rows.sum(axis=1,keepdims=True)
            np.divide(rows,total,out=rows,where=total>0)
            rows[np.flatnonzero(total[:,0] == 0)] = 1/rows.shape[1]
        return RecallPolicy(self.layout,data)


class RecallPolicy:
    def __init__(self, layout, data):
        self.layout, self.game = layout, layout.game
        if data.dtype != np.dtype('float64') or data.shape != (layout.entries,):
            raise ValueError('Incompatible policy array')
        for i in range(len(layout.graph.keys)):
            rows = data[layout.offsets[i]:layout.offsets[i+1]].reshape(len(self.game.hands),-1)
            if not np.isfinite(rows).all() or (rows < 0).any() or not np.allclose(rows.sum(axis=1),1,atol=1e-12,rtol=0):
                raise ValueError('Invalid policy probabilities')
        self.data = data.copy()
        self.data.flags.writeable = False

    def policy(self, player, hand, history):
        if player != len(history)%2:
            raise ValueError('Wrong seat to act')
        i = self.layout.graph.index[self.layout.graph.key(player,history)]
        return self.layout.row(self.data,i,hand).copy()

    def actions(self, player, history):
        if player != len(history)%2:
            raise ValueError('Wrong seat to act')
        i = self.layout.graph.index[self.layout.graph.key(player,history)]
        rows = self.data[self.layout.offsets[i]:self.layout.offsets[i+1]].reshape(len(self.game.hands),-1)
        return {a:rows[:,j] for j,a in enumerate(self.layout.graph.actions[i]) if rows[:,j].any()}

    def save(self, path):
        rules = asdict(self.game.rules)
        metadata = json.dumps({'format':'recall-policy-v1','recall':1,'rules':rules,
                               'hands':self.game.hands,'keys':self.layout.graph.keys,
                               'actions':self.layout.graph.actions},sort_keys=True,separators=(',',':'))
        np.savez_compressed(path,metadata=np.array(metadata),probabilities=self.data)
        return {'file':Path(path).name,'bytes':Path(path).stat().st_size,
                'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                'probabilities_sha256':hashlib.sha256(self.data.astype('<f8').tobytes()).hexdigest()}

    @classmethod
    def load(cls, game, path):
        layout = Layout(game)
        with np.load(path,allow_pickle=False) as archive:
            meta = json.loads(str(archive['metadata']))
            expected = {'format':'recall-policy-v1','recall':1,'rules':asdict(game.rules),
                        'hands':game.hands,'keys':layout.graph.keys,'actions':layout.graph.actions}
            if meta != json.loads(json.dumps(expected)) or set(archive.files) != {'metadata','probabilities'}:
                raise ValueError('Incompatible policy metadata')
            return cls(layout,archive['probabilities'])
