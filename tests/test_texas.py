import copy
import json
import unittest

from benchmarks.harness import evaluate_profile, make_game
from benchmarks.texas import DATA, commands, import_policy, load_fixture


class TexasAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.game = make_game(cls.fixture)
        cls.record = json.loads((DATA.parent.parent / 'docs' / 'texassolver-results.json').read_text())
        cls.dump = cls.record['execution']['strategy']

    def test_actual_recorded_policy_and_unreachable_values(self):
        profile = import_policy(self.game, self.dump)
        result = evaluate_profile(self.game, profile)
        self.assertAlmostEqual(result['root'][0], -25, places=9)
        self.assertLess(result['gap'], 1e-9)
        self.assertEqual(len(result['nodes']), 4)
        # IP facing an OOP bet has no opponent reach in this exported policy.
        self.assertTrue(all(value == 0 for value in result['nodes'][(1, 'b10000')]['reach']))
        self.assertEqual(commands(self.fixture), self.record['execution']['input_commands'])
        self.assertEqual(len(profile[0]['root'][1]), 6)
        self.assertEqual(len(profile[1]['c'][1]), 18)

    def test_reject_tree_player_combo_and_probability_mismatches(self):
        variants = []
        bad = copy.deepcopy(self.dump)
        bad['player'] = 0
        variants.append(bad)
        bad = copy.deepcopy(self.dump)
        bad['actions'][1] = 'BET 50.000000'
        variants.append(bad)
        bad = copy.deepcopy(self.dump)
        bad['childrens']['RAISE 200.000000'] = {}
        variants.append(bad)
        bad = copy.deepcopy(self.dump)
        del bad['childrens']['CHECK']
        variants.append(bad)
        bad = copy.deepcopy(self.dump)
        bad['strategy']['strategy'].pop('KhKd')
        variants.append(bad)
        bad = copy.deepcopy(self.dump)
        bad['strategy']['strategy']['KhKd'] = [float('nan'), 0]
        variants.append(bad)
        for dump in variants:
            with self.subTest(dump=dump['actions']), self.assertRaises(ValueError):
                import_policy(self.game, dump)

    def test_refuse_other_fixtures_and_implicit_range_substitution(self):
        for changed in ({'bet_sizes': [0.5]}, {'stack': 200}, {'id': 'polarized_pot'}):
            with self.assertRaises(ValueError):
                commands(dict(self.fixture, **changed))


if __name__ == '__main__':
    unittest.main()
