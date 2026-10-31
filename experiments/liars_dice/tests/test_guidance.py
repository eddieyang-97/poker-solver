from array import array
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beliefs import posterior
from game import Game
from guidance import ProbabilityGuide, PosteriorResponse
from mccfr import Info, Solver, corrected_values
from one_face import OneFace, PRIOR, evaluate
from run_research import probability_table
from run_guided import exact_sample_moments


class GuidanceTests(unittest.TestCase):
    def test_frozen_moment_oracle_agrees_with_independent_game_value(self):
        game = OneFace(5)
        guide = ProbabilityGuide(game)
        uniform = lambda p,t,h:[1/len(game.actions(h))]*len(game.actions(h))
        for policy in (uniform,guide.policy):
            true_ev = evaluate(game,policy)['ev_p0']
            for updater in (0,1):
                zero = exact_sample_moments(game,policy,update=updater)
                guided = exact_sample_moments(game,policy,guide.baseline,updater)
                self.assertAlmostEqual(zero['mean'],true_ev*(1 if updater == 0 else -1))
                self.assertAlmostEqual(guided['mean'],zero['mean'])
                if policy is uniform:
                    self.assertLess(guided['variance'],zero['variance'])
                # A heuristic baseline is not guaranteed to help every policy.
                else:
                    self.assertGreater(guided['variance'],zero['variance'])
        with self.assertRaises(ValueError):
            exact_sample_moments(OneFace(14),uniform)

    def test_guide_probabilities_and_fallback_match_declared_prior(self):
        game = Game()
        guide = ProbabilityGuide(game)
        np.testing.assert_allclose(guide.truth,probability_table(game),rtol=0,atol=1e-14)
        self.assertTrue(np.all(guide.truth >= 0))
        self.assertTrue(np.all(guide.truth <= 1))
        solver = Solver(game,initial_policy=guide.policy,initial_regret=5)
        for history in ((), (game.actions(())[0],)):
            row = solver.policy(len(history)%2,0,history)
            self.assertEqual(row,guide.policy(len(history)%2,0,history))
            self.assertAlmostEqual(sum(row),1)

    def test_control_variate_unbiased_and_perfect_baseline_zero_variance(self):
        values, sampling, policy = [-1., .6], [.2, .8], [.7, .3]
        expected = sum(p*v for p,v in zip(policy,values))
        for baseline in ([0.,0.],[.3,-.9],values):
            estimates = []
            for a in range(2):
                row = corrected_values(values[a],sampling[a],a,baseline)
                estimates.append(sum(p*v for p,v in zip(policy,row)))
            self.assertAlmostEqual(sum(q*v for q,v in zip(sampling,estimates)),expected)
            variance = sum(q*(v-expected)**2 for q,v in zip(sampling,estimates))
            if baseline is values:
                self.assertEqual(variance,0)
            elif baseline == [0.,0.]:
                self.assertGreater(variance,1)

    def test_nonzero_baseline_full_trajectory_expectations(self):
        game = OneFace(4)
        guide = ProbabilityGuide(game)
        my_type, policy = 2, [.75,.25]
        for baselines in (guide.baseline,lambda p,t,h:[.37]*len(game.actions(h))):
            actual, correct, average = np.zeros(2), np.zeros(2), np.zeros(2)
            for opp, prior in enumerate(PRIOR):
                opening = [0.,1.] if opp == 0 else [.8,.2]
                sampled_open3 = .95*opening[0]+.025
                utilities = [-game.payoff((3,), (opp,my_type),1),-game.payoff((3,4), (opp,my_type),0)]
                mean = sum(p*v for p,v in zip(policy,utilities))
                correct += prior*opening[0]*(np.array(utilities)-mean)
                for path, probability in (((0,0),sampled_open3*.6),
                                          ((0,1,0),sampled_open3*.4),((1,0),1-sampled_open3)):
                    solver = Solver(game,baseline=baselines)
                    solver.infos[(0,opp,())] = Info(array('d',opening),array('d',[0,0]))
                    solver.infos[(1,my_type,(3,))] = Info(array('d',policy),array('d',[0,0]))

                    class Scripted:
                        def __init__(self):
                            self.script = iter(path)

                        def choices(self,population,weights):
                            return [next(self.script)]
                    solver.rng = Scripted()
                    solver.episode(1,(opp,my_type))
                    node = solver.infos[(1,my_type,(3,))]
                    actual += prior*probability*(np.array(node.regret)-policy)
                    average += prior*probability*np.array(node.average)
            np.testing.assert_allclose(actual,correct,rtol=0,atol=1e-14)
            np.testing.assert_allclose(average,policy,rtol=0,atol=1e-14)

    def test_guided_baseline_converges_on_exactly_evaluable_game(self):
        game = OneFace(5)
        guide = ProbabilityGuide(game)
        solver = Solver(game,seed=42,initial_policy=guide.policy,initial_regret=5,baseline=guide.baseline)
        solver.train(40000)
        result = evaluate(game,solver.policy)
        self.assertLess(result['nashconv'],.06)

    def test_posterior_acceleration_matches_independent_conditioning(self):
        game = OneFace(5)
        guide = ProbabilityGuide(game)
        for warm in (False,True):
            solver = Solver(game,seed=42,initial_policy=guide.policy if warm else None,
                            initial_regret=5 if warm else 0)
            solver.train(100)
            response = PosteriorResponse(game,solver,guide)
            for history in ((3,),(4,),(3,4),(3,4,5)):
                seat = len(history)%2
                np.testing.assert_allclose(response._belief(seat,history),
                                           posterior(game,seat,history,solver.policy),rtol=0,atol=1e-14)
                for hand in range(7):
                    row = response.policy(seat,hand,history)
                    self.assertEqual(len(row),len(game.actions(history)))
                    self.assertAlmostEqual(sum(row),1)
        # Impossible evidence is rejected rather than silently restored to prior.
        forced = Solver(game,initial_policy=lambda p,t,h:[0,0,1] if not h else [1/len(game.actions(h))]*len(game.actions(h)))
        response = PosteriorResponse(game,forced,guide)
        with self.assertRaises(ValueError):
            response._belief(1,(3,))

    def test_invalid_guidance_rejected(self):
        game = OneFace(4)
        for weight in (-1,float('nan')):
            with self.assertRaises(ValueError):
                Solver(game,initial_regret=weight,initial_policy=lambda p,t,h:[1,0])
        with self.assertRaises(ValueError):
            Solver(game,initial_regret=1)
        bad = Solver(game,initial_policy=lambda p,t,h:[float('nan')]*len(game.actions(h)))
        with self.assertRaises(ValueError):
            bad.policy(0,0,())
        bad = Solver(game,baseline=lambda p,t,h:[float('nan')]*len(game.actions(h)))
        with self.assertRaises(ValueError):
            bad.train(1)


if __name__ == '__main__':
    unittest.main()
