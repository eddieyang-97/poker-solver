import math
import unittest

import numpy as np

from benchmarks.turn_policy import TurnPolicyOracle
from poker_spot.turn import Chance, Decision, Terminal, TurnSolver, evaluate_turn_all_in_call
from poker_spot.validation import validate


class TurnTests(unittest.TestCase):
    def test_exact_all_in_runouts_and_call_ev(self):
        result = evaluate_turn_all_in_call('2c,3d,4h,8s', 'KhKd', 'AsAd', 100, 100)
        self.assertAlmostEqual(result['equity'], 2/44)
        self.assertAlmostEqual(result['ev_call_minus_fold'], 300*2/44-100)
        self.assertEqual(result['best_action_given_range'], 'fold')
        self.assertAlmostEqual(result['required_equity'], 1/3)
        # A weighted missing-draw range produces genuine call indifference.
        mixed = evaluate_turn_all_in_call('2c,3d,4h,8s', 'KhKd', 'AsAd,QhJd:0.4318181818181818', 100, 100)
        self.assertAlmostEqual(mixed['equity'], 1/3)
        self.assertEqual(mixed['best_action_given_range'], 'indifferent')

    def test_per_deal_chance_not_union_of_range_cards(self):
        solver = TurnSolver('2c,3d,4h,8s', 'KhKd,AsKs:0.3', 'AsAd,QhJd:0.5', 100, 100, [], [])
        np.testing.assert_array_equal(solver.river_valid.sum(axis=0), 44*solver.valid)
        self.assertEqual(solver.valid[1, 0], 0)
        result = solver.solve(20, 'KhKd')
        oracle = TurnPolicyOracle(solver).evaluate()
        self.assertAlmostEqual(result['diagnostics']['oop_ev'], oracle['oop_ev'], places=10)
        self.assertAlmostEqual(result['diagnostics']['nash_conv_chips'], 0, places=10)
        reach = result['hands']['oop']['node_strategy']['turn/check/check/river@As']['reach_probability_given_hand']
        # Given KK, only QJ (weight .5) allows As; total opponent mass is 1.5.
        self.assertAlmostEqual(reach, (0.5/1.5)/44)
        rows = result['hands']['oop']['node_strategy']
        self.assertAlmostEqual(sum(row['reach_probability_given_hand'] for key, row in rows.items()
                                   if key.startswith('turn/check/check/river@')), 1)

    def test_pot_stack_carry_and_fold_refunds(self):
        solver = TurnSolver('2c,3d,4h,8s', 'KhKd', 'AsAd,QhJd', 100, 80, [0.5], [0.5, 1.0])
        called = solver.root.children[1].children[1]
        self.assertIsInstance(called, Chance)
        self.assertEqual(solver.effective_bets[called.child.name], [30])
        # A river bet is uncalled on a fold: prior matched turn chips count,
        # but the bettor's uncalled river bet is refunded.
        fold = called.child.children[1].children[0]
        self.assertEqual(fold.contrib, (80, 50))
        left, right = solver._terminal(fold, solver.weights[0][None, :]*solver.masks[0],
                                        solver.weights[1][None, :]*solver.masks[1])
        index = solver.rivers.index('9c')
        self.assertAlmostEqual(left[index, 0], 100*2)
        self.assertTrue(np.all(right[index] == -100))
        all_in = TurnSolver('2c,3d,4h,8s', 'KhKd', 'AsAd', 100, 100, [1.0], [0.5])
        leaf = all_in.root.children[1].children[1]
        self.assertIsInstance(leaf, Terminal)
        self.assertEqual(leaf.kind, 'runout')
        self.assertEqual(leaf.contrib, (100, 100))

    def test_two_street_profile_and_best_response_oracle(self):
        solver = TurnSolver('Ks,9s,5h,Td', 'KdQd,AsJh:0.5', 'QsJs,9h9d:0.5', 100, 140, [0.5], [0.5, 1.0])
        result = solver.solve(500, 'KdQd', 'QsJs', 'Ts')
        oracle = TurnPolicyOracle(solver)
        direct = oracle.evaluate()
        for key in ('oop_ev', 'ip_ev', 'nash_conv_chips'):
            self.assertAlmostEqual(result['diagnostics'][key], direct[key], delta=1e-9)
        self.assertAlmostEqual(direct['oop_ev']+direct['ip_ev'], 0, places=10)
        self.assertLess(result['diagnostics']['nash_conv_pct_pot'], 0.5)
        self.assertTrue(any('@Ts' in key for key in result['hands']['oop']['node_strategy']))
        np.testing.assert_allclose(solver.nodes['turn/check/check/river'].average().sum(axis=-1), 1)
        # Public rivers are separate information sets, with different policies.
        river = solver.nodes['turn/check/check/river'].average()
        self.assertGreater(np.max(np.ptp(river, axis=0)), 0.05)
        # Root action EVs hold all later actions to the average policy. They do
        # not optimize future decisions along a rarely selected turn action.
        row = result['hands']['oop']['node_strategy']['turn']['action_ev_relative_to_half_turn_pot']
        opponent = oracle.weights[1]
        for action, child in zip(solver.root.actions, solver.root.children, strict=True):
            self.assertAlmostEqual(row[action], oracle._walk(child, 0, 0, opponent, False)/sum(opponent), places=10)

    def test_oracle_detects_corrupted_runout_evaluation(self):
        solver = TurnSolver('2c,3d,4h,8s', 'KhKd', 'AsAd', 100, 100, [1.0], [])
        solver.runout_sign[0, 0] += 0.2
        result = solver.solve(40)
        direct = TurnPolicyOracle(solver).evaluate()
        self.assertGreater(abs(result['diagnostics']['oop_ev']-direct['oop_ev'])
                           +abs(result['diagnostics']['nash_conv_chips']-direct['nash_conv_chips']), 0.1)

    def test_single_hand_game_against_exact_backward_minimax(self):
        # With singleton ranges, both players know the hands. Backward induction
        # is exact, but the turn decision must precede observation of the river.
        solver = TurnSolver('Js,Ts,2c,3d', 'AsKs', 'QhQd', 100, 150, [0.5], [0.5])
        result = solver.solve(1500, 'AsKs')
        oracle = TurnPolicyOracle(solver)

        def minimax(node, context=None):
            if isinstance(node, Decision):
                choose = max if node.player == 0 else min
                return choose(minimax(child, context) for child in node.children)
            if isinstance(node, Chance):
                return sum(minimax(node.child, k) for k, card in enumerate(solver.rivers)
                           if card not in solver.hands[0][0] and card not in solver.hands[1][0])/44
            return oracle._payoff(node, 0, 0, 0, context)

        value = minimax(solver.root)
        self.assertAlmostEqual(value, -300/11, places=10)
        diagnostic = result['diagnostics']
        self.assertLess(abs(diagnostic['oop_ev']-value), diagnostic['nash_conv_chips']+1e-9)
        self.assertLess(diagnostic['nash_conv_pct_pot'], 0.5)
        actions = result['hands']['oop']['node_strategy']['turn']['action_ev_relative_to_half_turn_pot']
        for name, child in zip(solver.root.actions, solver.root.children, strict=True):
            self.assertAlmostEqual(actions[name], oracle._walk(child, 0, 0, [1.0], False), places=10)

    def test_invalid_and_resource_inputs_and_no_hosted_tool(self):
        base = dict(board='2c,3d,4h,8s', oop_range='KhKd', ip_range='AsAd', pot=100, stack=100)
        for change in ({'board': '2c,3d,4h,8s,9c'}, {'board': '2c,2c,4h,8s'},
                       {'pot': True}, {'stack': math.nan}, {'river_bet_sizes': [0]},
                       {'turn_bet_sizes': [0.5, 0.5]}, {'turn_bet_sizes': [0.3, 0.6, 1]},
                       {'ip_range': 'KhKs'}, {'oop_range': 'AA,KK,QQ,JJ,TT'}, {'ip_range': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                TurnSolver(**(base | change))
        solver = TurnSolver(**base)
        for kwargs in ({'iterations': 2001}, {'iterations': True}, {'oop_hand': 'AhAc'},
                       {'river_card': '2c'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                solver.solve(**kwargs)
        with self.assertRaises(ValueError):
            validate('solve_turn', base, hosted=True)
        solver.solve(20)
        with self.assertRaises(ValueError):
            solver.solve(20)
        close_sizes = TurnSolver(**base, turn_bet_sizes=[0.5, 0.50000001])
        self.assertEqual(len(set(close_sizes.root.actions)), 3)

    def test_river_display_filter_does_not_reveal_future_to_turn_player(self):
        config = dict(board='2c,3d,4h,8s', oop_range='KhKd', ip_range='AsAd,QhJd', pot=100, stack=150)
        first = TurnSolver(**config).solve(100, 'KhKd', river_card='9c')
        second = TurnSolver(**config).solve(100, 'KhKd', river_card='As')
        self.assertEqual(first['diagnostics'], second['diagnostics'])
        self.assertEqual(first['hands']['oop']['node_strategy']['turn'], second['hands']['oop']['node_strategy']['turn'])


if __name__ == '__main__':
    unittest.main()
