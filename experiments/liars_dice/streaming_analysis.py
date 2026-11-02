"""Standalone frozen-policy analysis. No training or hosted registration."""
from copy import deepcopy
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

from game import Bid, Rules
from policy_space import BayesianComponent, PriorComponent
from run_bounded_response import population_at


FORMAT = 'liars-analysis-v1'
DEPENDENCIES = ('game.py', 'guidance.py', 'finite_family.py', 'policy_space.py', 'streaming_analysis.py',
                'run_bounded_response.py', 'one_face.py', 'mccfr.py', 'bounded_response.py')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def source_hashes():
    base = Path(__file__).parent
    return {name:hashlib.sha256((base/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in DEPENDENCIES}


def export_snapshot(receipt):
    payload = {'format':FORMAT, 'rules':asdict(Rules()), 'source_sha256_lf':source_hashes(),
               'input_receipt_sha256_canonical':hashlib.sha256(canonical(receipt)).hexdigest(),
               'components':receipt['components'],
               'rounds':[{'population_size':r['population_size'],
                          'deployed_mixture':{k:r['deployed_mixture'][k] for k in ('mixture0', 'mixture1')}}
                         for r in receipt['rounds']]}
    return canonical({'payload':payload, 'sha256':hashlib.sha256(canonical(payload)).hexdigest()})+b'\n'


def load_snapshot(data, generation=2):
    envelope = json.loads(data)
    payload = envelope['payload']
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    if envelope['sha256'] != digest or payload['format'] != FORMAT or payload['rules'] != asdict(Rules()):
        raise ValueError('Incompatible or corrupt snapshot')
    if payload['source_sha256_lf'] != source_hashes():
        raise ValueError('Snapshot implementation fingerprint mismatch')
    if type(generation) is not int or not 0 <= generation < len(payload['rounds']):
        raise ValueError('Unavailable population generation')
    specs = payload['components']
    # This artifact version supports the existing finite ancestry only.
    from finite_family import CONFIGURATIONS
    if len(specs) != 15+4*(len(payload['rounds'])-1) or len(payload['rounds']) not in (1, 2, 3):
        raise ValueError('Unsupported population layout')
    for i, (challenge, aspiration) in enumerate(CONFIGURATIONS):
        if specs[i] != {'type':'prior', 'challenge':challenge, 'aspiration':aspiration}:
            raise ValueError('Unsupported prior component')
    for i, spec in enumerate(specs[15:]):
        if (spec.get('type') != 'bayesian' or spec.get('reference_round') != i//4
                or set(spec) != {'type', 'reference_round', 'challenge', 'aspiration', 'tremble'}):
            raise ValueError('Invalid component ancestry')
    for i, row in enumerate(payload['rounds']):
        if row['population_size'] != 15+4*i:
            raise ValueError('Invalid population size')
    game, guide, target = population_at(payload, generation)
    return game, guide, target, f'{digest}:generation={generation}'


class CompiledPopulation:
    """DAG of the frozen reference models; full history is the external key."""
    def __init__(self, game, guide, target):
        self.game, self.guide, self.target = game, guide, target
        self.components = target.components
        self.models = []
        def visit(model):
            if any(model is old for old in self.models):
                return
            for component in model.components:
                if isinstance(component, BayesianComponent):
                    visit(component.target)
            self.models.append(model)
        visit(target)
        self.references = {i:next(j for j, m in enumerate(self.models) if m is c.target)
                           for i, c in enumerate(self.components) if isinstance(c, BayesianComponent)}
        self.belief_keys = tuple(sorted({(self.references[i], c.tremble)
                                        for i, c in enumerate(self.components) if isinstance(c, BayesianComponent)}))
        for model in self.models:
            if any(c is not self.components[i] for i, c in enumerate(model.components)):
                raise ValueError('Reference models must share the recorded component prefix')

    def state(self):
        return StreamingState(self)


class StreamingState:
    """Exact finite-model sufficient state; no history truncation in exact mode.

    All observed-action likelihoods use PRE-update masks and beliefs. Only
    after calculating them are the actor's masks and other-seat beliefs updated.
    """
    def __init__(self, compiled):
        self.compiled = compiled
        n, k = len(compiled.game.prior), len(compiled.components)
        self.reach = np.ones((2, k, n), dtype=bool)
        self.beliefs = {key:np.tile(compiled.guide.prior, (2, 1)) for key in compiled.belief_keys}
        self.posterior = np.tile(compiled.guide.prior, (2, 1))
        self.supported = [True, True]
        self.last, self.length = None, 0

    def choices(self, player):
        c = self.compiled
        history = () if self.last is None else (self.last,)
        bids = sorted((a for a in c.game.actions(history) if a != -1), key=lambda a:c.guide.ties[c.guide.columns[a]])
        columns = [c.guide.columns[a] for a in bids]
        result, truth_cache = [], {}
        for i, component in enumerate(c.components):
            if isinstance(component, PriorComponent):
                result.append(component.choices(player, history))
                continue
            if not bids:
                result.append(np.full(len(c.game.prior), -1))
                continue
            key = self.references_key(i)
            if key not in truth_cache:
                truth_cache[key] = component.truth(self.beliefs[key][player])
            truth = truth_cache[key]
            values = truth[:, columns]
            best = values.max(axis=1)
            chosen = np.array(bids)[np.argmax(values >= best[:, None]-1e-12, axis=1)]
            if component.aspiration is not None:
                supported = values >= component.aspiration-1e-12
                quantities = c.guide.quantities[columns]
                best_q = np.where(supported, quantities, -1).max(axis=1)
                eligible = supported & (quantities == best_q[:, None])
                scores = np.where(eligible, values, -1)
                best = scores.max(axis=1)
                indices = np.argmax(eligible & (scores >= best[:, None]-1e-12), axis=1)
                chosen[best_q >= 0] = np.array(bids)[indices[best_q >= 0]]
            if self.last is not None:
                chosen[truth[:, c.guide.columns[self.last]] < component.threshold] = -1
            result.append(chosen)
        return np.asarray(result)

    def references_key(self, index):
        return self.compiled.references[index], self.compiled.components[index].tremble

    def likelihood(self, player, action, choices=None, model_index=-1):
        c = self.compiled
        legal = c.game.actions(() if self.last is None else (self.last,))
        if action not in legal:
            raise ValueError('Illegal action')
        choices = self.choices(player) if choices is None else choices
        model = c.models[model_index]
        k = len(model.components)
        weights = model.weights[player, :, None]*self.reach[player, :k]
        denominator = weights.sum(axis=0)
        numerator = (weights*(choices[:k] == action)).sum(axis=0)
        return np.divide(numerator, denominator, out=np.full_like(numerator, 1/len(legal)), where=denominator > 0)

    def probabilities(self, player):
        choices = self.choices(player)
        legal = self.compiled.game.actions(() if self.last is None else (self.last,))
        return {a:self.likelihood(player, a, choices) for a in legal}

    def advance(self, action):
        c = self.compiled
        legal = c.game.actions(() if self.last is None else (self.last,))
        if action == -1 or action not in legal:
            raise ValueError('History must contain legal bids only')
        player = self.length%2
        choices = self.choices(player)
        likelihoods = [self.likelihood(player, action, choices, j) for j in range(len(c.models))]
        other = 1-player
        if self.supported[other]:
            self.posterior[other] *= likelihoods[-1]
            total = self.posterior[other].sum()
            self.supported[other] = bool(total > 0)
            if total > 0:
                self.posterior[other] /= total
        for (reference, tremble), beliefs in self.beliefs.items():
            beliefs[other] *= (1-tremble)*likelihoods[reference]+tremble/len(legal)
            beliefs[other] /= beliefs[other].sum()
        self.reach[player] &= choices == action
        self.last, self.length = action, self.length+1

    def array_bytes(self):
        return self.reach.nbytes+self.posterior.nbytes+sum(b.nbytes for b in self.beliefs.values())


class StreamingPolicy:
    """Exact mode, or explicitly lossy last-one/last-two observation baselines."""
    def __init__(self, compiled, remember=None, cache_size=64):
        if remember not in (None, 1, 2):
            raise ValueError('Supported representations: full, last one, last two')
        self.compiled, self.game, self.remember = compiled, compiled.game, remember
        self.state = lru_cache(maxsize=cache_size)(self._state)
        self.actions = lru_cache(maxsize=cache_size)(self._actions)

    def _state(self, history):
        state = self.compiled.state()
        # The boundary bid consumes one memory slot. k=1 retains only the
        # last bid/parity, resetting all beliefs and reach masks.
        start = 0 if self.remember is None else max(0, len(history)-self.remember+1)
        if start:
            state.last, state.length = history[start-1], start
        for action in history[start:]:
            state.advance(action)
        return state

    def _actions(self, player, history):
        if player != len(history)%2:
            raise ValueError('Wrong player to act')
        return self.state(history).probabilities(player)

    def likelihood(self, player, history, action):
        return self.actions(player, history)[action]

    def policy(self, player, hand, history):
        return [float(self.likelihood(player, history, a)[hand]) for a in self.game.actions(history)]


class Analyzer:
    """Pure analysis interface with bounded memoization, no online training."""
    def __init__(self, snapshot_bytes, generation=2, cache_size=64):
        game, guide, target, model_id = load_snapshot(snapshot_bytes, generation)
        self.game, self.guide, self.model_id = game, guide, model_id
        self._compiled = CompiledPopulation(game, guide, target)
        self._evaluate = lru_cache(maxsize=cache_size)(self._analysis)

    def analyze(self, hero_hand, hero_seat, history, model_id):
        if model_id != self.model_id:
            raise ValueError('Requested model/version mismatch')
        if (len(hero_hand) != 5 or any(type(d) is not int or not 1 <= d <= 6 for d in hero_hand)
                or type(hero_seat) is not int or hero_seat not in (0, 1)
                or not isinstance(history, (list, tuple)) or len(history) > 150):
            raise ValueError('Invalid hand, seat or history length')
        ids, prefix = [], ()
        for raw in history:
            if (not isinstance(raw, dict) or set(raw) != {'quantity', 'face', 'mode'}
                    or type(raw['quantity']) is not int or type(raw['face']) is not int
                    or raw['mode'] not in ('fly', 'zhai')):
                raise ValueError('Invalid bid description')
            try:
                action = self.game.bids.index(Bid(**raw))
            except ValueError as error:
                raise ValueError('Unsupported bid') from error
            if action not in self.game.actions(prefix):
                raise ValueError('Illegal bidding history')
            ids.append(action)
            prefix = tuple(ids)
        if len(ids)%2 != hero_seat:
            raise ValueError('Hero is not the player to act')
        hand = tuple(sorted(hero_hand))
        return deepcopy(self._evaluate(hand, hero_seat, tuple(ids)))

    def _analysis(self, hand, seat, history):
        state = self._compiled.state()
        for action in history:
            state.advance(action)
        index = self.game.hands.index(hand)
        result = {'format':FORMAT, 'model_id':self.model_id, 'hero_hand':list(hand), 'hero_seat':seat,
                  'history':[asdict(self.game.bids[a]) for a in history],
                  'legal_actions':[{'action':'challenge'} if a == -1 else asdict(self.game.bids[a]) for a in self.game.actions(history)],
                  'posterior_hand_order':'game.hand_distribution lexicographic multisets',
                  'opponent_posterior':state.posterior[seat].tolist() if state.supported[seat] else None,
                  'status':'ok' if state.supported[seat] else 'zero_model_support',
                  'challenge':None, 'continuation':{'status':'abstain', 'reason':'strategy_quality_not_validated'},
                  'gto_recommendation':None}
        if history:
            bid = history[-1]
            true = self.guide.counts[index, bid]+self.guide.counts[:, bid] >= self.game.bids[bid].quantity
            probability = float(true @ state.posterior[seat]) if state.supported[seat] else None
            result['challenge'] = {'prior_truth_probability':float(self.guide.truth[index, bid]),
                                   'model_truth_probability':probability,
                                   'model_ev':None if probability is None else 1-2*probability,
                                   'own_contribution':int(self.guide.counts[index, bid])}
        return result
