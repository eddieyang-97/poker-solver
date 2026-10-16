import copy
import json
import os
import random
import unittest
from unittest.mock import patch

from benchmarks.harness import (
    ROOT, compare_fixture, evaluate_profile, import_reference, make_game, parse_cards, rank7,
    reference_config, run_reference, state_mapping, validate_fixture, verify_reference,
)
from algorithms.naive_eval import showdown_values_naive
from algorithms.vector_eval import build_blocked_indices, build_strength_summary, showdown_values
from games.river_holdem import evaluate_7
from poker_spot.core import DECK


FIXTURES = json.loads((ROOT / 'fixtures.json').read_text())


class BenchmarkTests(unittest.TestCase):
    def test_reference_integrity_and_independent_hand_evaluation(self):
        verify_reference()
        rng = random.Random(20261016)
        for _ in range(300):
            hand = rng.sample(DECK, 7)
            self.assertEqual(rank7(tuple(sorted(hand))), evaluate_7(parse_cards(hand)))
        for text in ('As Ah Ad Ac Ks Qs Js', 'As Ah Ad Ks Kh Kd 2c', 'As 2s 3s 4s 5s 9h Td'):
            hand = text.split()
            self.assertEqual(rank7(tuple(sorted(hand))), evaluate_7(parse_cards(hand)))

    def test_reject_mismatched_trees_and_rounding(self):
        for changes in ({'rake': 1}, {'max_raises': 1}, {'include_all_in': True},
                        {'bet_sizes': [0.333333333]}, {'stack': 20, 'bet_sizes': [0.5, 1]},
                        {'pot': 100.001}, {'board': ['As']*5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_fixture(dict(FIXTURES[0], **changes))
        bad = copy.deepcopy(FIXTURES[0])
        bad['oop'] *= 2
        with self.assertRaises(ValueError):
            make_game(bad)
        with self.assertRaises(ValueError):
            state_mapping(make_game(FIXTURES[2], raises=2), FIXTURES[2])

    def test_upstream_naive_fallback_for_disjoint_strengths(self):
        game = make_game(FIXTURES[0])
        summary = build_strength_summary(game.hands[1])
        blocked = build_blocked_indices(game.hands[0], summary)
        # Pinned upstream fast path is unsupported for custom disjoint strengths.
        with self.assertRaises(KeyError):
            showdown_values(game.hands[0], summary, blocked, game.hand_weights[1], 10000, 0)
        self.assertEqual(showdown_values_naive(game.hands[0], game.hands[1], game.hand_weights[1], 10000, 0), [5000])

    def test_independent_same_tree_roundtrip_and_fault_detection(self):
        result = compare_fixture(FIXTURES[0], iterations=500, reference_iterations=800)
        self.assertEqual(result['failures'], [])
        self.assertLess(result['same_profile_max_action_ev_delta_pot'], 1e-10)
        # Corrupt the product evaluator only; reference ranks/training stay intact.
        with patch('poker_spot.core.rank7', return_value=(0,)):
            corrupted = compare_fixture(FIXTURES[0], iterations=100, reference_iterations=100)
        self.assertIn('independent_same_profile_action_ev_disagrees', corrupted['failures'])

    def test_actual_reach_is_not_own_strategic_reach(self):
        game = make_game(FIXTURES[0])
        mapping = state_mapping(game, FIXTURES[0])
        profile = {0: {}, 1: {}}

        def walk(state):
            if game.is_terminal(state):
                return
            actions = game.legal_actions(state)
            from algorithms.vector_eval import action_tokens
            profile[state.player][game.infoset_key(state, state.player)] = (
                action_tokens(actions), [[1/len(actions)]*len(actions) for _ in game.hands[state.player]])
            for action in actions:
                walk(game.next_state(state, action))
        walk(game.initial_state())
        evaluated = evaluate_profile(game, profile)
        self.assertEqual(set(mapping.values()), {'oop_first', 'ip_after_oop_check',
                                                'ip_facing_oop_bet_1', 'oop_facing_ip_bet_1'})
        self.assertAlmostEqual(sum(evaluated['nodes'][(1, 'c')]['reach']), 0.5)
        self.assertAlmostEqual(sum(evaluated['nodes'][(0, 'c/b10000')]['reach']), 0.25)

    def test_exact_issue_contract_in_independent_process(self):
        config = json.loads((ROOT / 'reference-polarized.json').read_text())
        actual = reference_config(FIXTURES[0])
        actual['pot'] /= 100
        actual['stack'] /= 100
        self.assertEqual(actual, config)
        exported = run_reference(config, 4000)
        self.assertNotEqual(exported['pid'], os.getpid())
        self.assertFalse(exported['product_modules_loaded'])
        golden = json.loads((ROOT / 'reference-polarized-output.json').read_text())
        self.assertEqual(exported['config'], golden['config'])
        self.assertEqual(exported['reference_commit'], golden['reference_commit'])
        # Same pinned code, inputs and iteration schedule: deterministic replay,
        # not a required exact mix across different approximate equilibria.
        for actual_player, expected in zip(exported['players'], golden['players'], strict=True):
            self.assertEqual(actual_player['hands'], expected['hands'])
            self.assertEqual(actual_player['weights'], expected['weights'])
            for key, node in actual_player['profile'].items():
                self.assertEqual(node['actions'], expected['profile'][key]['actions'])
                for row, expected_row in zip(node['strategy'], expected['profile'][key]['strategy'], strict=True):
                    for value, expected_value in zip(row, expected_row, strict=True):
                        self.assertAlmostEqual(value, expected_value, delta=1e-9)
        self.assertLess(exported['checkpoints'][-1]['raw_exploitability'], 0.25)
        self.assertLess(exported['checkpoints'][-1]['raw_exploitability'],
                        exported['checkpoints'][0]['raw_exploitability'])

    def test_serialized_reference_order_and_weight_validation(self):
        game = make_game(FIXTURES[0])
        exported = run_reference(reference_config(FIXTURES[0]), 100)
        original = import_reference(game, exported)
        reordered = copy.deepcopy(exported)
        player = reordered['players'][1]
        player['hands'].reverse()
        player['weights'].reverse()
        for node in player['profile'].values():
            node['strategy'].reverse()
        self.assertEqual(import_reference(game, reordered), original)
        player['weights'][0] = 0.9
        with self.assertRaises(ValueError):
            import_reference(game, reordered)


if __name__ == '__main__':
    unittest.main()
