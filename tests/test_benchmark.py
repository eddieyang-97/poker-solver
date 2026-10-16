import copy
import json
import random
import unittest
from unittest.mock import patch

from benchmarks.harness import (
    ROOT, compare_fixture, evaluate_profile, make_game, parse_cards, rank7,
    state_mapping, validate_fixture, verify_reference,
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


if __name__ == '__main__':
    unittest.main()
