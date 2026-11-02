from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bounded_response import PopulationModel, ResponseSearch
from finite_family import Family
from guidance import ProbabilityGuide
from game import Game
from one_face import OneFace, evaluate
from policy_space import BayesianComponent, PopulationMixture, PriorComponent, exact_pair


class BoundedResponseTests(unittest.TestCase):
    def fixture(self, maximum=5):
        game = OneFace(maximum)
        guide = ProbabilityGuide(game)
        family = Family(game, guide, ((.3, None), (.7, .2), (.5, .95)))
        components = [PriorComponent(family, i) for i in range(3)]
        target = PopulationMixture(game, components, [.2, .3, .5], [.4, .1, .5])
        return game, guide, target

    def test_sparse_model_matches_behavioral_likelihoods_and_zero_reach(self):
        game, guide, target = self.fixture()
        response = BayesianComponent(game, guide, target)
        target = PopulationMixture(game, [*target.components, response], [.2, .3, .1, .4], [.4, .1, .2, .3])
        model = PopulationModel(target)
        for history in ((), (3,), (5,), (3, 4), (3, 4, 5)):
            player = len(history)%2
            sparse = model.actions(player, history)
            for action in game.actions(history):
                np.testing.assert_allclose(sparse.get(action, np.zeros(len(game.prior))),
                                           target.likelihood(player, history, action), atol=1e-14)

    def test_bounds_contain_independent_br_and_policy_realizes_lower(self):
        for maximum in (3, 5, 7):
            game, guide, target = self.fixture(maximum)
            reference = evaluate(game, target.policy)
            for seat in (0, 1):
                previous_lower, previous_upper = -1., 1.
                for budget in (1, 2, 8, 10000):
                    search = ResponseSearch(game, guide, PopulationModel(target), seat, depth=4, max_nodes=budget)
                    result = search.solve()
                    exact = reference[f'br{seat}']
                    self.assertLessEqual(result['lower'], exact+1e-12)
                    self.assertGreaterEqual(result['upper'], exact-1e-12)
                    self.assertGreaterEqual(result['lower'], previous_lower-1e-12)
                    self.assertLessEqual(result['upper'], previous_upper+1e-12)
                    self.assertLessEqual(result['stats']['expanded_own_nodes'], budget)
                    def profile(player, hand, history):
                        return (search.policy if player == seat else target.policy)(player, hand, history)
                    value = evaluate(game, profile)['ev_p0']*(1 if seat == 0 else -1)
                    self.assertAlmostEqual(value, result['lower'])
                    previous_lower, previous_upper = result['lower'], result['upper']
                self.assertAlmostEqual(result['lower'], exact)
                self.assertAlmostEqual(result['upper'], exact)

    def test_frontier_depth_and_invalid_inputs(self):
        game, guide, target = self.fixture()
        for seat in (0, 1):
            shallow = ResponseSearch(game, guide, PopulationModel(target), seat, depth=1).solve()
            deep = ResponseSearch(game, guide, PopulationModel(target), seat, depth=2).solve()
            self.assertGreaterEqual(deep['lower'], shallow['lower']-1e-12)
            self.assertLessEqual(deep['upper'], shallow['upper']+1e-12)
            self.assertGreater(shallow['stats']['depth_frontiers']+shallow['stats']['forced_challenges'], 0)
            self.assertAlmostEqual(deep['width'], 0)
        for kwargs in ({'seat':2}, {'seat':0, 'depth':0}, {'seat':0, 'max_nodes':0}):
            with self.assertRaises(ValueError):
                ResponseSearch(game, guide, PopulationModel(target), **kwargs)
        search = ResponseSearch(game, guide, PopulationModel(target), 0)
        with self.assertRaises(ValueError):
            search.choices(0, ())
        search.solve()
        with self.assertRaises(ValueError):
            search.choices(1, (3,))
        self.assertEqual(search.solve(), search.result)

    def test_nested_opponent_exact_br_and_full_rule_deployment(self):
        for game in (OneFace(7), Game()):
            guide = ProbabilityGuide(game)
            family = Family(game, guide, ((.3, None), (.7, .8)))
            components = [PriorComponent(family, i) for i in range(2)]
            base = PopulationMixture(game, components, [.3, .7], [.6, .4])
            components.append(BayesianComponent(game, guide, base, threshold=.4, aspiration=.8))
            target = PopulationMixture(game, components, [.2, .3, .5], [.4, .1, .5])
            small = isinstance(game, OneFace)
            reference = evaluate(game, target.policy) if small else None
            for seat in (0, 1):
                search = ResponseSearch(game, guide, PopulationModel(target), seat,
                                        depth=4 if small else 1, max_nodes=10000 if small else 2)
                bound = search.solve()
                value = 0.
                for index, weight in enumerate(target.weights[1-seat]):
                    first, second = (search, components[index]) if seat == 0 else (components[index], search)
                    numerator, _ = exact_pair(game, guide, first, second)
                    value += weight*numerator/7776**2*(1 if seat == 0 else -1)
                self.assertAlmostEqual(value, bound['lower'])
                if small:
                    self.assertAlmostEqual(bound['lower'], reference[f'br{seat}'])
                    self.assertAlmostEqual(bound['upper'], reference[f'br{seat}'])
                else:
                    self.assertLessEqual(bound['lower'], bound['upper']+1e-12)
                    self.assertLessEqual(bound['stats']['expanded_own_nodes'], 2)

    def test_incumbent_survives_smaller_refinement_budget(self):
        game, guide, target = self.fixture(7)
        model = PopulationModel(target)
        for seat in (0, 1):
            incumbent = ResponseSearch(game, guide, model, seat, depth=1)
            original = incumbent.solve().copy()
            refinement = ResponseSearch(game, guide, model, seat, depth=4, max_nodes=1, incumbent=incumbent)
            result = refinement.solve()
            self.assertGreaterEqual(result['lower'], original['lower']-1e-12)
            self.assertLessEqual(result['upper'], original['upper']+1e-12)
            self.assertEqual(incumbent.result, original)
            policy = lambda p, t, h:(refinement.policy if p == seat else target.policy)(p, t, h)
            self.assertAlmostEqual(evaluate(game, policy)['ev_p0']*(1 if seat == 0 else -1), result['lower'])
            with self.assertRaises(ValueError):
                ResponseSearch(game, guide, model, 1-seat, incumbent=incumbent)
            with self.assertRaises(ValueError):
                ResponseSearch(game, guide, PopulationModel(self.fixture(7)[2]), seat, incumbent=incumbent)


if __name__ == '__main__':
    unittest.main()
