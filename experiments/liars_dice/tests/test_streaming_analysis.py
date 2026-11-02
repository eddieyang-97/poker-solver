from collections import Counter
from dataclasses import asdict
from itertools import product
import json
from pathlib import Path
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import Bid
from streaming_analysis import Analyzer, CompiledPopulation, StreamingPolicy, export_snapshot, load_snapshot


class StreamingAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((Path(__file__).resolve().parents[1]/'outputs/policy-space.json').read_text())
        cls.snapshot = export_snapshot(cls.receipt)

    def test_snapshot_and_api_validation_cache_isolation(self):
        self.assertEqual(self.snapshot, export_snapshot(self.receipt))
        damaged = json.loads(self.snapshot)
        damaged['payload']['rules']['face_one'] = False
        with self.assertRaises(ValueError):
            load_snapshot(json.dumps(damaged))
        analyzer = Analyzer(self.snapshot, cache_size=2)
        args = ([1, 1, 2, 3, 5], 1, [{'quantity':5, 'face':4, 'mode':'fly'}], analyzer.model_id)
        first = analyzer.analyze(*args)
        first['hero_hand'][0] = 6
        self.assertEqual(analyzer.analyze(*args)['hero_hand'][0], 1)
        self.assertEqual(analyzer._evaluate.cache_info().hits, 1)
        for hand, seat, history, model in [([True, 1, 2, 3, 5], 1, args[2], args[3]),
                                           (args[0], 0, args[2], args[3]),
                                           (args[0], 1, [{'quantity':2, 'face':4, 'mode':'fly'}], args[3]),
                                           (args[0], 1, args[2], 'wrong-model'),
                                           (args[0], 1, [{'quantity':5, 'face':4, 'mode':'fly', 'opponent_hand':[1]*5}], args[3])]:
            with self.assertRaises(ValueError):
                analyzer.analyze(hand, seat, history, model)
        zero = analyzer.analyze([2, 3, 4, 5, 6], 1, [{'quantity':14, 'face':1, 'mode':'zhai'}], analyzer.model_id)
        self.assertEqual(zero['status'], 'zero_model_support')
        self.assertIsNone(zero['challenge']['model_ev'])
        self.assertIsNone(zero['opponent_posterior'])

    def test_stream_matches_recursive_reference_on_legal_and_off_policy_histories(self):
        rng = random.Random(46001)
        for generation in (0, 1, 2):
            game, guide, target, _ = load_snapshot(self.snapshot, generation)
            compiled = CompiledPopulation(game, guide, target)
            for trial in range(12):
                state, history = compiled.state(), ()
                external = np.tile(guide.prior, (2, 1))
                support = [True, True]
                for _ in range(8):
                    actor = len(history)%2
                    actual = state.choices(actor)
                    for index, component in enumerate(target.components):
                        np.testing.assert_array_equal(actual[index], component.choices(actor, history))
                    legal = game.actions(history)
                    for action in legal[::max(1, len(legal)//5)]:
                        np.testing.assert_allclose(state.likelihood(actor, action), target.likelihood(actor, history, action), atol=1e-13)
                    bids = [a for a in legal if a != -1]
                    if not bids:
                        break
                    # Low ordered bids create long chains; random jumps test
                    # legal histories outside this target's own support.
                    action = bids[0] if trial < 3 else rng.choice(bids)
                    if support[1-actor]:
                        external[1-actor] *= target.likelihood(actor, history, action)
                        total = external[1-actor].sum()
                        support[1-actor] = bool(total > 0)
                        if total > 0:
                            external[1-actor] /= total
                    state.advance(action)
                    history += (action,)
                    self.assertEqual(state.supported, support)
                    np.testing.assert_allclose(state.posterior, external, atol=1e-13)

    def test_raw_roll_scoring_and_prior_probabilities(self):
        game, guide, _, _ = load_snapshot(self.snapshot, 0)
        raw = Counter(tuple(sorted(roll)) for roll in product(range(1, 7), repeat=5))
        self.assertEqual(sum(raw.values()), 7776)
        weights = np.array([raw[h] for h in game.hands])
        def direct(hand, face, mode):
            if all(d == face for d in hand):
                return 7
            if mode == 'zhai' or face == 1:
                return hand.count(face)
            if all(d == 1 for d in hand):
                return 7
            matches = sum(d in (1, face) for d in hand)
            return 6 if matches == 5 else matches
        counts = np.array([[direct(h, b.face, b.mode) for b in game.bids] for h in game.hands])
        np.testing.assert_array_equal(counts, guide.counts)
        for hand in (0, 80, 251):
            probabilities = ((counts[hand, :, None]+counts.T) >= guide.quantities[:, None]) @ weights/7776
            np.testing.assert_allclose(probabilities, guide.truth[hand], atol=1e-15)

    def test_full_history_beliefs_differ_and_private_input_does_not_leak(self):
        analyzer = Analyzer(self.snapshot)
        g = analyzer.game
        policies = [StreamingPolicy(analyzer._compiled, remember=k) for k in (None, 1, 2)]
        histories = [(g.bids.index(Bid(4, 4, 'fly')),),
                     tuple(g.bids.index(Bid(q, f, 'fly')) for q, f in ((3, 4), (3, 5), (4, 4)))]
        # Compare model-internal beliefs, which remain defined through the
        # declared tremble even when external conditioning has zero support.
        key = analyzer._compiled.belief_keys[0]
        self.assertFalse(np.allclose(policies[0].state(histories[0]).beliefs[key][1],
                                     policies[0].state(histories[1]).beliefs[key][1]))
        for action in g.actions(histories[0]):
            np.testing.assert_array_equal(policies[1].likelihood(1, histories[0], action),
                                          policies[1].likelihood(1, histories[1], action))
        for history in histories:
            payload = [asdict(g.bids[a]) for a in history]
            first = analyzer.analyze([1, 1, 2, 3, 5], 1, payload, analyzer.model_id)
            second = analyzer.analyze([2, 2, 3, 5, 6], 1, payload, analyzer.model_id)
            self.assertEqual(first['opponent_posterior'], second['opponent_posterior'])
            self.assertEqual(first['continuation']['status'], 'abstain')
            for policy in policies:
                self.assertAlmostEqual(sum(policy.policy(1, 100, history)), 1)


if __name__ == '__main__':
    unittest.main()
