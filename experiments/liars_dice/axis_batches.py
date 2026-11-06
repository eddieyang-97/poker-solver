"""Axis reduction variant of #57's frozen chance blocks.

The historical pass stays unchanged for source/probability receipt replay.
Only aggregation by sample position changes here. Final duplicate private-hand
updates still use the inherited multiplicity-safe scatter.
"""
import numpy as np

from crossed_batches import BatchFixtureTrainer, BatchTrainer


def pair_average(raw, player, size, crossed):
    if crossed:
        return raw.reshape(raw.shape[0],size,size).sum(axis=2 if player==0 else 1).T/(size*size)
    return raw.T/size


class AxisUpdates:
    def batch_increments(self, hands):
        # Keep the graph/terminal recurrence explicit and directly comparable
        # with the frozen reference; do not rewrite historical source manifests.
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
            delta[i] = pair_average(raw,p,k,self.crossed)
            averages[i] = pair_average(reach[p,i]*strategy,p,k,self.crossed)
        if not np.isfinite(values).all() or not np.isfinite(reach).all():
            raise ArithmeticError('Nonfinite batch pass')
        return delta,averages,float(values[0].mean()),float(reach.max())


class AxisTrainer(AxisUpdates,BatchTrainer):
    """Full-rule one-bid blocks, with all other #57 semantics inherited."""


class AxisFixtureTrainer(AxisUpdates,BatchFixtureTrainer):
    """Same operator on the declared recall 1/2/full house fixtures."""
