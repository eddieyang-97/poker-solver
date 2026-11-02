from collections import Counter
from itertools import product
import json
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
from policy_space import BayesianComponent, PopulationMixture, PriorComponent, exact_pair, prune_weights


class PolicySpaceTests(unittest.TestCase):
    def test_explicit_support_projection_and_inactive_components(self):
        weights, lost = prune_weights([1e-8, .4, .6-1e-8], 1e-6)
        self.assertEqual(weights[0], 0)
        self.assertAlmostEqual(lost, 1e-8)
        np.testing.assert_allclose(prune_weights([.5, .5], .9)[0], [1, 0])
        class Inactive:
            def choices(self, player, history):
                raise AssertionError('Zero-weight component evaluated')
        game = OneFace(5)
        guide = ProbabilityGuide(game)
        family = Family(game, guide, ((.5, None),))
        mix = PopulationMixture(game, [PriorComponent(family, 0), Inactive()], [1, 0], [1, 0])
        self.assertAlmostEqual(sum(mix.policy(0, 0, (3, 4))), 1)
        for weights, cutoff in (([.2, .2], .1), ([1], -1), ([float('nan')], 0)):
            with self.assertRaises(ValueError):
                prune_weights(weights, cutoff)

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

    def test_recorded_nested_full_rule_pair_against_scalar_roll_oracle(self):
        receipt = json.loads((Path(__file__).resolve().parents[1]/'outputs/policy-space.json').read_text())
        game = Game()
        guide = ProbabilityGuide(game)
        prior_count = receipt['rounds'][0]['population_size']
        specs = receipt['components']
        family = Family(game, guide, tuple((s['challenge'], s['aspiration']) for s in specs[:prior_count]))
        components = [PriorComponent(family, i) for i in range(prior_count)]
        for generation in (0, 1):
            row = receipt['rounds'][generation]
            weights = row['deployed_mixture']
            self.assertEqual(len(components), row['population_size'])
            target = PopulationMixture(game, components, weights['mixture0'], weights['mixture1'])
            components.extend(BayesianComponent(game, guide, target, s['challenge'], s['aspiration'], s['tremble'])
                              for s in specs if s.get('reference_round') == generation)
        # Generation two vs generation one: both policies condition on full
        # histories, with nested frozen references. This is a published entry.
        first, second = 19, 15
        pair = components[first], components[second]

        # Enumerate ordered rolls independently of game.prior/multinomial code.
        rolls = Counter(tuple(sorted(roll)) for roll in product(range(1, 7), repeat=5))
        indices = {hand:i for i, hand in enumerate(game.hands)}

        def score(hand, bid):
            if all(d == bid.face for d in hand):
                return 7
            if bid.mode == 'zhai' or bid.face == 1:
                return hand.count(bid.face)
            if all(d == 1 for d in hand):
                return 7
            count = sum(d in (1, bid.face) for d in hand)
            return 6 if count == 5 else count

        # Cache only fixed-policy action vectors, not paths, chance masses or
        # payoffs. Each private deal is traversed separately from the root.
        choices, challengers, switches = {}, set(), set()
        numerator, total_weight, longest = 0, 0, 0
        for hand0, weight0 in rolls.items():
            for hand1, weight1 in rolls.items():
                hands, history = (hand0, hand1), ()
                for _ in range(151):
                    player = len(history)%2
                    if history not in choices:
                        choices[history] = pair[player].choices(player, history)
                    action = int(choices[history][indices[hands[player]]])
                    if action == -1:
                        self.assertTrue(history)
                        bid = game.bids[history[-1]]
                        true = sum(score(hand, bid) for hand in hands) >= bid.quantity
                        loser = player if true else 1-player
                        utility = -1 if loser == 0 else 1
                        numerator += utility*weight0*weight1
                        total_weight += weight0*weight1
                        challengers.add(player)
                        longest = max(longest, len(history))
                        break
                    bid = game.bids[action]
                    if not history:
                        self.assertGreaterEqual(bid.quantity, 3)
                    else:
                        last = game.bids[history[-1]]
                        if last.mode == bid.mode:
                            self.assertGreater((bid.quantity, bid.face), (last.quantity, last.face))
                        else:
                            self.assertGreaterEqual(bid.quantity, last.quantity+(-1 if last.mode == 'fly' else 2))
                            switches.add((last.mode, bid.mode))
                    history += (action,)
                else:
                    self.fail('Scalar replay did not terminate')
        self.assertEqual(total_weight, 6**10)
        self.assertEqual(challengers, {0, 1})
        self.assertEqual(switches, {('fly', 'zhai'), ('zhai', 'fly')})
        self.assertGreaterEqual(longest, 3)
        self.assertEqual(numerator, receipt['payoff_numerators'][first][second])
        self.assertEqual(numerator, exact_pair(game, guide, *pair)[0])


if __name__ == '__main__':
    unittest.main()
