from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from beliefs import posterior
from finite_family import Family, exact_matrix
from guidance import ProbabilityGuide
from game import Bid, Game
from one_face import OneFace, evaluate
from policy_space import BayesianComponent, PopulationMixture, PriorComponent, exact_pair


class PolicySpaceTests(unittest.TestCase):
    def setUp(self):
        self.game = OneFace(5)
        self.guide = ProbabilityGuide(self.game)
        self.family = Family(self.game, self.guide, ((.3, None), (.7, .2), (.5, .95)))
        self.components = [PriorComponent(self.family, i) for i in range(3)]
        self.mix = PopulationMixture(self.game, self.components, [.2, .3, .5], [.4, .1, .5])

    def test_batched_posterior_histograms_and_off_model_completion(self):
        response = BayesianComponent(self.game, self.guide, self.mix, tremble=.07)
        def trembled(player, hand, history):
            legal = self.game.actions(history)
            return [.93*p+.07/len(legal) for p in self.mix.policy(player, hand, history)]
        for history in ((), (3,), (4,), (3, 4), (3, 4, 5)):
            player = len(history)%2
            expected = posterior(self.game, player, history, trembled)
            np.testing.assert_allclose(response.belief(player, history), expected, atol=1e-14)
            truth = response.truth(expected)
            for hand in range(len(self.game.prior)):
                for col, quantity in enumerate(self.guide.quantities):
                    direct = sum(p for i, p in enumerate(expected)
                                 if self.guide.counts[hand, col]+self.guide.counts[i, col] >= quantity)
                    self.assertAlmostEqual(truth[hand, col], direct)
            self.assertTrue(np.isin(response.choices(player, history), self.game.actions(history)).all())
        # Complete even when the untrembled reference could not generate a bid.
        pure = PopulationMixture(self.game, self.components[:1], [1], [1])
        response = BayesianComponent(self.game, self.guide, pure)
        self.assertTrue(np.isfinite(response.belief(1, (5,))).all())
        for kwargs in ({'tremble':0}, {'threshold':2}, {'aspiration':-1}):
            with self.assertRaises(ValueError):
                BayesianComponent(self.game, self.guide, pure, **kwargs)

    def test_general_exact_enumerator_and_history_mixture_realization(self):
        old, total = exact_matrix(self.family)
        for i, first in enumerate(self.components):
            for j, second in enumerate(self.components):
                numerator, _ = exact_pair(self.game, self.guide, first, second)
                self.assertEqual(numerator, old[i, j])
        responses = [BayesianComponent(self.game, self.guide, self.mix, threshold=.4),
                     BayesianComponent(self.game, self.guide, self.mix, threshold=.6, aspiration=.8)]
        # Frozen reference snapshots must not grow with the live population.
        self.components.extend(responses)
        self.assertEqual(len(self.mix.components), 3)
        x, y = np.array([.1, .2, .1, .3, .3]), np.array([.3, .1, .2, .1, .3])
        matrix = np.array([[exact_pair(self.game, self.guide, a, b)[0]/total
                            for b in self.components] for a in self.components])
        mixture = PopulationMixture(self.game, self.components, x, y)
        self.assertAlmostEqual(evaluate(self.game, mixture.policy)['ev_p0'], x @ matrix @ y)
        for i, response in enumerate(responses, 3):
            def policy(p, t, h):
                return response.policy(p, t, h) if p == 0 else self.family.pure_policy(1)(p, t, h)
            self.assertAlmostEqual(matrix[i, 1], evaluate(self.game, policy)['ev_p0'])
        with self.assertRaises(RuntimeError):
            exact_pair(self.game, self.guide, responses[0], responses[1], max_nodes=1)

    def test_full_rule_histograms_and_distinct_public_histories(self):
        game = Game()
        guide = ProbabilityGuide(game)
        family = Family(game, guide, ((.3, None), (.7, .8)))
        components = [PriorComponent(family, i) for i in range(2)]
        mix = PopulationMixture(game, components, [.3, .7], [.6, .4])
        response = BayesianComponent(game, guide, mix)
        bid = lambda q, f:game.bids.index(Bid(q, f, 'fly'))
        short = (bid(4, 4),)
        long = (bid(3, 4), bid(3, 5), bid(4, 4))
        self.assertFalse(np.allclose(response.belief(1, short), response.belief(1, long)))
        weights = response.belief(1, long)
        for hand in (0, 53, 140, 251):
            direct = ((guide.counts[hand, :, None]+guide.counts.T) >= guide.quantities[:, None]) @ weights
            np.testing.assert_allclose(response.truth(weights)[hand], direct, atol=1e-14)
        numerator, _ = exact_pair(game, guide, components[0], components[1])
        old, _ = exact_matrix(family)
        self.assertEqual(numerator, old[0, 1])


if __name__ == '__main__':
    unittest.main()
