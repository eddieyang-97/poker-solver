from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from prior_control import exact_prior_value


class PriorControlTests(unittest.TestCase):
    def test_integer_chance_simulation_matches_independent_tree_evaluation(self):
        for maximum in (3,4,5):
            game = OneFace(maximum)
            guide = ProbabilityGuide(game)
            result = exact_prior_value(game,guide)
            independent = evaluate(game,guide.policy)
            self.assertEqual(result['ordered_chance_outcomes'],7776**2)
            self.assertEqual(result['p0_win_weight']+result['p0_loss_weight'],7776**2)
            self.assertEqual(sum(result['opening_weights_out_of_7776'].values()),7776)
            self.assertAlmostEqual(result['ev_p0'],independent['ev_p0'])


if __name__ == '__main__':
    unittest.main()
