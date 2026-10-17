import copy
import json
import unittest

from benchmarks.harness import compare_fixture, evaluate_profile, make_game
from benchmarks.texas import DATA, import_policy
from benchmarks.texas_blockers import (
    CHIP_GATE, analytical_profile, chance_diagnostics, diagnostic_commands,
    evaluate_runs, load_blocker_fixture,
)


class TexasBlockerDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_blocker_fixture()
        cls.record = json.loads((DATA.parent.parent / 'docs' / 'texas-blocker-results.json').read_text())

    def test_conditional_chance_and_analytical_policy(self):
        chance = chance_diagnostics(self.fixture)
        self.assertEqual(chance['compatible_pairs'], 114)
        self.assertEqual(chance['unnormalized_joint_weight'], 75)
        self.assertEqual(chance['ip_category_probability_after_card_removal'],
                         {'AA': 0.48, 'KK': 0.04, 'QJ': 0.48})
        game = make_game(self.fixture)
        profile = import_policy(game, self.record['execution']['runs'][0]['strategy'])
        result = evaluate_profile(game, analytical_profile(game, profile))
        self.assertAlmostEqual(result['root'][0], -25, places=9)
        self.assertLess(result['gap'], 1e-9)

    def test_recorded_external_failures_stay_failures(self):
        result = evaluate_runs(self.record['execution'])
        self.assertEqual(result['failed_runs'], [4000, 40000])
        for row, recorded in zip(result['runs'], self.record['analysis']['runs'], strict=True):
            self.assertEqual(row['status'], 'FAIL')
            self.assertGreater(row['independently_evaluated_nashconv'], CHIP_GATE)
            self.assertAlmostEqual(row['independently_evaluated_nashconv'],
                                   recorded['independently_evaluated_nashconv'], delta=1e-9)
        with self.assertRaises(ValueError):
            diagnostic_commands(1000000)
        altered = copy.deepcopy(self.record['execution'])
        altered['runs'][0]['input_commands'] = 'different game'
        with self.assertRaises(ValueError):
            evaluate_runs(altered)

    def test_independent_engines_pass_the_weighted_game(self):
        result = compare_fixture(self.fixture, iterations=500, reference_iterations=800)
        self.assertEqual(result['failures'], [])
        self.assertLess(result['local_nashconv'], CHIP_GATE)
        self.assertLess(result['reference_nashconv'], CHIP_GATE)


if __name__ == '__main__':
    unittest.main()
