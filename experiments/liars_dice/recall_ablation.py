"""Matched training/recall experiments on explicitly action-restricted house games.

Original trainers stay unchanged so their historical receipts remain replayable.
Adapters reuse their recurrence, allowing recall 1/2/full on bounded fixtures.
"""
import numpy as np
import random

from fixed_strategy import GraphCFR, PublicGraph
from game import Bid, Game
from recall_training import Layout, RecallTrainer


class HouseFixture:
    """Six named bids; original legality/payoff, independently weighted five-dice.

    Hands with identical contributions to EVERY retained bid are lossless types
    in this restricted game only. They are not full-game hand abstractions.
    """
    def __init__(self, zhai_quantity=2, compress=True):
        if zhai_quantity not in (2,3): raise ValueError('Fixture quantity must be 2 or 3')
        self.full = Game()
        self.zhai_quantity = zhai_quantity
        self.selected = tuple(self.full.bids.index(Bid(q,f,m))
            for q,m in ((3,'fly'),(zhai_quantity,'zhai'),(zhai_quantity+2,'fly')) for f in (2,4))
        profiles = [tuple(row[a] for a in self.selected) for row in self.full.counts]
        unique = sorted(set(profiles)) if compress else list(range(252))
        mapping = {v:i for i,v in enumerate(unique)}
        self.projection = tuple(mapping[p] if compress else i for i,p in enumerate(profiles))
        self.hands = tuple(unique)
        self.counts = unique if compress else profiles
        self.weights = [0]*len(unique)
        for i,w in enumerate(self.full.prior):
            self.weights[self.projection[i]] += round(w*7776)
        self.prior = tuple(w/7776 for w in self.weights)
        self.bids = tuple(self.full.bids[a] for a in self.selected)
        self._legal = {}
        for last in (None,*range(6)):
            legal = self.full.actions(() if last is None else (self.selected[last],))
            self._legal[last] = tuple(([-1] if last is not None else [])+
                                     [i for i,a in enumerate(self.selected) if a in legal])

    def actions(self, history): return self._legal[history[-1] if history else None]
    def rank(self, action): return self.bids[action].rank

    def payoff(self, history, hands, challenger):
        a = history[-1]
        true = self.counts[hands[0]][a]+self.counts[hands[1]][a] >= self.bids[a].quantity
        winner = 1-challenger if true else challenger
        return 1. if winner == 0 else -1.


class FixtureLayout(Layout):
    def __init__(self, game, recall):
        if not isinstance(game,HouseFixture): raise ValueError('Only declared restricted house fixtures')
        self.game = game
        self.graph = PublicGraph(game,recall,max_states=1000)
        self.offsets = np.cumsum([0]+[len(a)*len(game.hands) for a in self.graph.actions])
        self.entries = int(self.offsets[-1])
        self.children = [np.array([-1 if c is None else c for c in row]) for row in self.graph.children]
        self.players = [p for p,_ in self.graph.keys]


class SampledFixtureCFR(RecallTrainer):
    """Same sampled recurrence; only layout construction differs from #54."""
    def __init__(self, game, recall, seed):
        self.layout = FixtureLayout(game,recall)
        self.game = game
        self.array_bytes = self.layout.entries*16
        if self.array_bytes > 32*1024**2: raise MemoryError('Fixture arrays exceed 32 MiB')
        self.regret = np.zeros(self.layout.entries)
        self.average = np.zeros_like(self.regret)
        self.rng = random.Random(seed)
        self.visits = np.zeros((2,len(game.hands)),dtype=np.int64)
        self.iterations = 0
        self.maximum_reach = 0.


class ExactFixtureCFR(GraphCFR):
    """Same exact recurrence; bounded 56-type fixture instead of tiny Dudo."""
    def __init__(self, game, recall):
        if not isinstance(game,HouseFixture) or len(game.hands) > 56:
            raise ValueError('Only losslessly compressed declared house fixtures')
        self.game, self.graph = game, PublicGraph(game,recall,max_states=1000)
        n = len(game.hands)
        entries = sum(map(len,self.graph.actions))*n
        self.estimated_array_bytes = 8*(5*entries+6*len(self.graph.keys)*n*n)
        if self.estimated_array_bytes > 64*1024**2: raise MemoryError('Exact scratch exceeds 64 MiB estimate')
        self.regrets = [np.zeros((n,len(a))) for a in self.graph.actions]
        self.averages = [np.zeros_like(r) for r in self.regrets]
        self.terminals = [None if not h else np.array([
            [game.payoff(h,(a,b),p) for b in range(n)] for a in range(n)]) for p,h in self.graph.keys]
        self.iterations = 0
