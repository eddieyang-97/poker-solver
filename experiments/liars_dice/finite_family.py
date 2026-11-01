"""Exact full-rule payoff matrix for a finite heuristic policy family.

Finite-family equilibrium is NOT full-game equilibrium. Root mixtures are
converted to perfect-recall behavioural policies using their own action reach.
"""
from functools import lru_cache
import numpy as np

from guidance import PosteriorResponse
from mccfr import normalize


CONFIGURATIONS = tuple((challenge,aspiration) for challenge in (.3,.5,.7)
                       for aspiration in (None,.2,.5,.8,.95))


class Family:
    def __init__(self, game, guide, configurations=CONFIGURATIONS):
        self.game, self.guide = game, guide
        self.configurations = configurations
        self.actions = guide.actions
        self.columns = guide.columns
        self.root = len(self.actions)
        self.choices = np.empty((len(configurations),len(game.prior),self.root+1),dtype=np.int16)
        for state,last in [(self.root,None),*enumerate(self.actions)]:
            history = () if last is None else (last,)
            legal = [a for a in game.actions(history) if a != -1]
            if not legal:
                self.choices[:,:,state] = -1
                continue
            ordered = sorted(legal,key=lambda a:guide.ties[self.columns[a]])
            cols = [self.columns[a] for a in ordered]
            truth = guide.truth[:,cols]
            # The safest fallback is independent of challenge threshold.
            safest = np.array(ordered)[np.argmax(truth,axis=1)]
            quantities = guide.quantities[cols]
            for k,(challenge,aspiration) in enumerate(configurations):
                if aspiration is None:
                    chosen = safest.copy()
                else:
                    supported = truth >= aspiration
                    best_q = np.max(np.where(supported,quantities[None,:],-1),axis=1)
                    score = np.where(supported & (quantities[None,:] == best_q[:,None]),truth,-1)
                    chosen = np.array(ordered)[np.argmax(score,axis=1)]
                    chosen[best_q == -1] = safest[best_q == -1]
                if last is not None:
                    chosen[guide.truth[:,self.columns[last]] < challenge] = -1
                self.choices[k,:,state] = chosen

    def state(self,history):
        return self.columns[history[-1]] if history else self.root

    def pure_policy(self,component):
        def policy(player,hand,history):
            chosen = self.choices[component,hand,self.state(history)]
            return [float(a == chosen) for a in self.game.actions(history)]
        return policy


def exact_matrix(family):
    """Integer weighted enumeration of every private deal; vectorized play."""
    game,guide = family.game,family.guide
    n,k = len(game.prior),len(family.configurations)
    h0 = np.repeat(np.arange(n),n)
    h1 = np.tile(np.arange(n),n)
    weights = np.rint(np.asarray(game.prior)*7776).astype(np.int64)
    chance = weights[h0]*weights[h1]
    total = 7776**2
    if chance.sum() != total:
        raise ValueError("Expected independent five-dice chance weights")
    numerators = np.zeros((k,k),dtype=np.int64)
    # Translate bid IDs back to column indices without assuming a contiguous ID scheme.
    offset = min(family.actions)
    translation = np.array([family.columns[a] for a in range(offset,max(family.actions)+1)])
    for i in range(k):
        for j in range(k):
            live = np.arange(n*n)
            state = np.full(n*n,family.root,dtype=np.int16)
            completed = 0
            for turn in range(151):
                player = turn%2
                component = i if player == 0 else j
                hand = h0 if player == 0 else h1
                chosen = family.choices[component,hand[live],state[live]]
                calls = chosen == -1
                ending = live[calls]
                if len(ending):
                    last = state[ending]
                    if (last == family.root).any():
                        raise AssertionError("Opening challenge")
                    true = guide.counts[h0[ending],last]+guide.counts[h1[ending],last] >= guide.quantities[last]
                    utility = (2*true.astype(np.int64)-1)*(1 if player == 1 else -1)
                    numerators[i,j] += utility @ chance[ending]
                    completed += len(ending)
                survivors = ~calls
                live = live[survivors]
                if not len(live):
                    break
                state[live] = translation[chosen[survivors]-offset]
            else:
                raise AssertionError("Finite policy did not terminate")
            if completed != n*n:
                raise AssertionError("Missing private deals")
    return numerators,total


def solve_matrix(matrix, checkpoints=(1000,10000,100000)):
    """Alternating regret matching+ and linear averaging; exact measured gap."""
    matrix = np.asarray(matrix,dtype=float)
    if matrix.ndim != 2 or not matrix.size or not np.isfinite(matrix).all():
        raise ValueError("Finite payoff matrix required")
    if not checkpoints or checkpoints != tuple(sorted(set(checkpoints))) or checkpoints[0] < 1:
        raise ValueError("Increasing positive checkpoints required")
    r0,r1 = np.zeros(matrix.shape[0]),np.zeros(matrix.shape[1])
    avg0,avg1 = np.zeros_like(r0),np.zeros_like(r1)
    reports = []
    for t in range(1,checkpoints[-1]+1):
        p0,p1 = np.asarray(normalize(r0)),np.asarray(normalize(r1))
        values0 = matrix @ p1
        r0 = np.maximum(0,r0+values0-p0 @ values0)
        p0 = np.asarray(normalize(r0))
        values1 = -p0 @ matrix
        r1 = np.maximum(0,r1+values1-p1 @ values1)
        avg0 += t*p0
        avg1 += t*p1
        if t in checkpoints:
            x,y = avg0/avg0.sum(),avg1/avg1.sum()
            lower,upper = float(np.min(x @ matrix)),float(np.max(matrix @ y))
            reports.append({'iterations':t,'value':float(x @ matrix @ y),
                            'family_value_lower':lower,'family_value_upper':upper,
                            'family_nashconv':upper-lower,
                            'mixture0':x.tolist(),'mixture1':y.tolist()})
    return reports


class Mixture:
    def __init__(self, family, weights0, weights1):
        self.family, self.game = family,family.game
        self.weights = np.asarray([weights0,weights1],dtype=float)
        if (self.weights.shape != (2,len(family.configurations)) or not np.isfinite(self.weights).all()
                or (self.weights < 0).any() or not np.allclose(self.weights.sum(axis=1),1,rtol=0,atol=1e-10)):
            raise ValueError("Two normalized component mixtures required")
        self._eligible = lru_cache(maxsize=512)(self._own_support)

    def _own_support(self,player,history):
        if not history:
            return np.ones((len(self.family.configurations),len(self.game.prior)),dtype=bool)
        previous = history[:-1]
        supported = self._eligible(player,previous)
        if len(previous)%2 == player:
            return supported & (self.family.choices[:,:,self.family.state(previous)] == history[-1])
        return supported

    def likelihood(self,player,history,action):
        legal = self.game.actions(history)
        if action not in legal:
            raise ValueError("Illegal requested action")
        weights = self.weights[player,:,None]*self._eligible(player,history)
        denominator = weights.sum(axis=0)
        choices = self.family.choices[:,:,self.family.state(history)]
        numerator = (weights*(choices == action)).sum(axis=0)
        # Arbitrary well-defined play at an own-zero-reach information set.
        return np.divide(numerator,denominator,out=np.full_like(numerator,1/len(legal)),where=denominator > 0)

    def policy(self,player,hand,history):
        legal = self.game.actions(history)
        weights = self.weights[player]*self._eligible(player,history)[:,hand]
        if weights.sum() == 0:
            return [1/len(legal)]*len(legal)
        choices = self.family.choices[:,hand,self.family.state(history)]
        total = weights.sum()
        probabilities = {}
        for action,weight in zip(choices.tolist(),weights.tolist()):
            probabilities[action] = probabilities.get(action,0.)+weight
        return [probabilities.get(a,0.)/total for a in legal]


class MixtureResponse(PosteriorResponse):
    def likelihood(self,actor,history,action):
        return self.target.likelihood(actor,history,action)
