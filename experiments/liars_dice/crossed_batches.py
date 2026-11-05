"""Frozen, vectorized private-chance minibatches; standalone research only.

Diagonal blocks average K paired updates. Crossed blocks average all K*K pairs
from the same two independent lists of K true-prior hand samples. Repeated hand
indices retain their multiplicity. Both have the original estimator's mean.
"""
import numpy as np

from recall_ablation import SampledFixtureCFR
from recall_training import RecallTrainer


class BatchUpdates:
    def configure_batch(self, batch_size, crossed):
        if type(batch_size) is not int or not 1 <= batch_size <= 32:
            raise ValueError('Batch size must be an integer from 1 to 32')
        if type(crossed) is not bool:
            raise ValueError('Crossed must be Boolean')
        self.batch_size, self.crossed = batch_size, crossed
        k = batch_size
        self.pair_rows = (np.repeat(np.arange(k),k),np.tile(np.arange(k),k)) if crossed else (np.arange(k),np.arange(k))
        self.counts = np.asarray(self.game.counts)

    def batch_increments(self, hands):
        k,n = self.batch_size,len(self.game.hands)
        if len(hands) != 2 or any(len(row) != k for row in hands):
            raise ValueError('Two hand lists matching the declared batch size required')
        if any(type(h) is not int or not 0 <= h < n for row in hands for h in row):
            raise ValueError('Valid integer hand indices required')
        ids = np.asarray(hands)
        mapping = self.pair_rows
        d = len(mapping[0])
        layout,graph = self.layout,self.layout.graph
        policies = []
        for i,p in enumerate(layout.players):
            rows = self.regret[layout.offsets[i]:layout.offsets[i+1]].reshape(n,-1)[ids[p]].clip(0)
            total = rows.sum(axis=1,keepdims=True)
            policies.append(np.divide(rows,total,out=np.full_like(rows,1/rows.shape[1]),where=total>0))
        reach = np.zeros((2,len(graph.keys),d))
        reach[:,0] = 1
        for i,p in enumerate(layout.players):
            children = layout.children[i]
            keep = children >= 0
            dest = children[keep]
            strategy = policies[i][mapping[p]][:,keep].T
            reach[p,dest] += reach[p,i]*strategy
            reach[1-p,dest] += reach[1-p,i]
        values = np.zeros((len(graph.keys),d))
        delta,averages = [None]*len(values),[None]*len(values)
        for i in reversed(range(len(values))):
            p,history = graph.keys[i]
            children = layout.children[i]
            child = values[np.maximum(children,0)].copy()
            if history:
                a = history[-1]
                truth = self.counts[ids[0,mapping[0]],a]+self.counts[ids[1,mapping[1]],a] >= self.game.bids[a].quantity
                child[children < 0] = (2*truth.astype(float)-1)*(1 if p == 1 else -1)
            strategy = policies[i][mapping[p]].T
            value = (strategy*child).sum(axis=0)
            values[i] = value
            raw = (child-value)*reach[1-p,i]*(1 if p == 0 else -1)
            delta[i],averages[i] = np.zeros((k,len(children))),np.zeros((k,len(children)))
            np.add.at(delta[i],mapping[p],raw.T/d)
            np.add.at(averages[i],mapping[p],(reach[p,i]*strategy).T/d)
        if not np.isfinite(values).all() or not np.isfinite(reach).all():
            raise ArithmeticError('Nonfinite batch pass')
        return delta,averages,float(values[0].mean()),float(reach.max())

    def step(self, hands=None):
        k,n = self.batch_size,len(self.game.hands)
        if hands is None:
            sampled = self.rng.choices(range(n),weights=self.game.prior,k=2*k)
            hands = (sampled[:k],sampled[k:])
        delta,averages,value,reach = self.batch_increments(hands)
        ids = np.asarray(hands)
        for i,p in enumerate(self.layout.players):
            for data,increment in ((self.regret,delta[i]),(self.average,averages[i])):
                rows = data[self.layout.offsets[i]:self.layout.offsets[i+1]].reshape(n,-1)
                np.add.at(rows,ids[p],increment)
                if not np.isfinite(rows[ids[p]]).all():
                    raise ArithmeticError('Nonfinite cumulative batch update')
        for p in (0,1): np.add.at(self.visits[p],ids[p],1)
        self.maximum_reach = max(self.maximum_reach,reach)
        self.iterations += 1
        return value


class BatchTrainer(BatchUpdates,RecallTrainer):
    def __init__(self, game, seed, batch_size=8, crossed=True):
        super().__init__(game,seed)
        self.configure_batch(batch_size,crossed)


class BatchFixtureTrainer(BatchUpdates,SampledFixtureCFR):
    def __init__(self, game, recall, seed, batch_size=8, crossed=True):
        super().__init__(game,recall,seed)
        self.configure_batch(batch_size,crossed)
