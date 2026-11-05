"""Own-hand sampled, opponent-hand integrated frozen graph updates.

For each seat's regret/average vector this is the conditional expectation of
the #54 paired-deal estimator given its own sampled hand. Both passes use the
same frozen policy; the other seat's sampled hand is never used in its update.
"""
import numpy as np

from recall_training import RecallTrainer
from recall_ablation import SampledFixtureCFR


class ConditionalUpdates:
    def increments(self, hands):
        n = len(self.game.hands)
        if len(hands) != 2 or any(type(h) is not int or not 0 <= h < n for h in hands):
            raise ValueError('Two valid sampled own-hand indices required')
        layout,graph = self.layout,self.layout.graph
        policies = []
        for i in range(len(graph.keys)):
            rows = self.regret[layout.offsets[i]:layout.offsets[i+1]].reshape(n,-1).clip(0)
            sums = rows.sum(axis=1,keepdims=True)
            policies.append(np.divide(rows,sums,out=np.full_like(rows,1/rows.shape[1]),where=sums>0))
        delta,average = [None]*len(graph.keys),[None]*len(graph.keys)
        prior = np.asarray(self.game.prior)
        counts = np.asarray(self.game.counts) if hasattr(self.game,'counts') else None
        maximum = 0.
        roots = []
        for seat in (0,1):
            own = hands[seat]
            reach = np.zeros((2,len(graph.keys),n))
            reach[:,0] = 1
            for i,p in enumerate(layout.players):
                children = layout.children[i]
                keep = children >= 0
                dest = children[keep]
                strategy = policies[i][own,keep,None] if p == seat else policies[i][:,keep].T
                reach[p,dest] += reach[p,i]*strategy
                reach[1-p,dest] += reach[1-p,i]
            values = np.zeros((len(graph.keys),n))
            for i in reversed(range(len(graph.keys))):
                p,history = graph.keys[i]
                children = layout.children[i]
                child = values[np.maximum(children,0)].copy()
                if history:
                    if counts is not None:
                        a = history[-1]
                        truth = counts[own,a]+counts[:,a] >= self.game.bids[a].quantity
                        terminal = (2*truth.astype(float)-1)*(1 if p == 1 else -1)
                    else:
                        terminal = np.array([self.game.payoff(history,(own,t) if seat == 0 else (t,own),p) for t in range(n)])
                    child[children < 0] = terminal
                strategy = policies[i][own,:,None] if p == seat else policies[i].T
                value = (strategy*child).sum(axis=0)
                values[i] = value
                if p == seat:
                    delta[i] = ((child-value)*(prior*reach[1-seat,i])[None,:]).sum(axis=1)*(1 if seat == 0 else -1)
                    average[i] = float(prior@reach[seat,i])*policies[i][own]
            if not np.isfinite(values).all() or not np.isfinite(reach).all():
                raise ArithmeticError('Nonfinite conditional pass')
            maximum = max(maximum,float(reach.max()))
            roots.append(float(prior@values[0]))
        # The two root values condition on different own hands; neither is a
        # realized-deal payoff. step() only uses increments and reach statistics.
        return delta,average,float(sum(roots)/2),maximum


class ConditionalTrainer(ConditionalUpdates,RecallTrainer):
    """Full-rule recall-1 trainer; same allocation/averaging/export as #54."""


class ConditionalFixtureTrainer(ConditionalUpdates,SampledFixtureCFR):
    """Same conditional update on the declared bounded recall fixtures."""
