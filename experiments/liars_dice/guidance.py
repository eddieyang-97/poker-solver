"""Prior-only guidance; exact probability calculations, heuristic play/values."""
from functools import lru_cache
import numpy as np

from game import Game
from one_face import OneFace


class ProbabilityGuide:
    def __init__(self, game, threshold=0.5):
        if not 0 <= threshold <= 1:
            raise ValueError("Challenge threshold must be in [0,1]")
        self.game, self.threshold = game, threshold
        if isinstance(game, Game):
            self.actions = tuple(range(len(game.bids)))
            counts = np.asarray(game.counts)
            quantities = [b.quantity for b in game.bids]
            self.ties = [(b.quantity, -b.face, b.mode != 'fly') for b in game.bids]
        elif isinstance(game, OneFace):
            self.actions = tuple(range(3, game.maximum+1))
            counts = np.repeat(np.array(game.hands)[:, None], len(self.actions), axis=1)
            quantities = list(self.actions)
            self.ties = [(q,) for q in quantities]
        else:
            raise ValueError("Guidance supports only declared full/one-face dice games")
        self.columns = {a: i for i, a in enumerate(self.actions)}
        self.counts, self.quantities = counts, np.asarray(quantities)
        self.prior = np.asarray(game.prior)
        weights = np.rint(self.prior*7776).astype(np.int64)
        if weights.sum() != 7776 or not np.allclose(weights/7776,self.prior,rtol=0,atol=1e-15):
            raise ValueError("Expected exact dice multiplicities out of 7776")
        self.truth = np.empty_like(counts, dtype=float)
        for col, q in enumerate(quantities):
            # Exact finite chance sum (floating-point evaluation, no sampling).
            self.truth[:, col] = (((counts[:, col, None]+counts[None, :, col]) >= q) @ weights)/7776
        # Cache only bounded public last-bid states, never full private histories.
        self._choices = lru_cache(maxsize=len(self.actions)+1)(self._choose_all)

    def _choose_all(self, last):
        history = () if last is None else (last,)
        legal = self.game.actions(history)
        bids = [a for a in legal if a != -1]
        if not bids:
            return np.full(len(self.prior), -1, dtype=int)
        ordered = sorted(bids, key=lambda a: self.ties[self.columns[a]])
        cols = [self.columns[a] for a in ordered]
        choices = np.array(ordered)[np.argmax(self.truth[:, cols], axis=1)]
        if last is not None:
            choices[self.truth[:, self.columns[last]] < self.threshold] = -1
        return choices

    def policy(self, player, hand, history):
        chosen = self._choices(history[-1] if history else None)[hand]
        return [float(a == chosen) for a in self.game.actions(history)]

    def baseline(self, player, hand, history):
        # Hypothetical immediate challenge values under the independent prior.
        # This is NOT a continuation solve or an action-conditioned value.
        result = []
        for a in self.game.actions(history):
            if a == -1:
                result.append(1 - 2*self.truth[hand, self.columns[history[-1]]])
            else:
                result.append(2*self.truth[hand, self.columns[a]]-1)
        return result


class PosteriorResponse:
    """Frozen-policy Bayesian probability bot; NOT an exact best response.

    Observes own private hand and full public history, plus the target's frozen
    behavioural policy. Never receives the target's realized private hand.
    """
    def __init__(self, game, target, guide, threshold=0.5, cache_size=512):
        self.game, self.target, self.guide = game, target, guide
        self.threshold = threshold
        self.zero_support = 0
        self._belief = lru_cache(maxsize=cache_size)(self._posterior)

    def likelihood(self, actor, history, action):
        legal = self.game.actions(history)
        index = legal.index(action)
        if self.target.initial_policy is None:
            result = np.full(len(self.game.prior), 1/len(legal))
        else:
            # This acceleration is specific to this guide's deterministic prior.
            if self.target.initial_policy != self.guide.policy:
                return np.array([self.target.policy(actor,t,history)[index] for t in range(len(self.game.prior))])
            result = (self.guide._choices(history[-1] if history else None) == action).astype(float)
        for hand in range(len(result)):
            node = self.target.infos.get(self.game.key(actor,hand,history))
            if node is not None and sum(node.average):
                result[hand] = node.average[index]/sum(node.average)
        return result

    def _posterior(self, own_seat, history):
        if not history:
            return self.guide.prior.copy()
        previous = history[:-1]
        weights = self._belief(own_seat, previous).copy()
        actor = len(previous) % 2
        if actor != own_seat:
            weights *= self.likelihood(actor, previous, history[-1])
            total = weights.sum()
            if total <= 0:
                self.zero_support += 1
                raise ValueError("Observed target history has zero frozen-policy support")
            weights /= total
        return weights

    def policy(self, player, hand, history):
        weights = self._belief(player,history)
        own = self.guide.counts[hand]
        truth = ((own[:, None]+self.guide.counts.T) >= self.guide.quantities[:, None]) @ weights
        legal = self.game.actions(history)
        if history and truth[self.guide.columns[history[-1]]] < self.threshold:
            chosen = -1
        else:
            bids = [a for a in legal if a != -1]
            if not bids:
                chosen = -1
            else:
                ordered = sorted(bids,key=lambda a:self.guide.ties[self.guide.columns[a]])
                best = max(truth[self.guide.columns[a]] for a in ordered)
                chosen = next(a for a in ordered if truth[self.guide.columns[a]] >= best-1e-12)
        return [float(a == chosen) for a in legal]
