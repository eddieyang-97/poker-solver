"""Exact differential checks against the retained two-player CFR+ traversal."""
from copy import deepcopy
import unittest

import numpy as np

from poker_spot.turn import Terminal, TurnSolver


BASE = dict(board='2c,3d,4h,8s', oop_range='KhKd', ip_range='AsAd,QhJd:0.7',
            pot=100, stack=200, turn_bet_sizes=[0.5], river_bet_sizes=[0.5])


def old_training_schedule(solver, iterations):
    """Original full refresh, both-value walk; no optimized trainer calls."""
    marks = {iterations, max(1, iterations//4), max(1, iterations//2)}
    checkpoints = []
    for iteration in range(1, iterations+1):
        for side in (0, 1):
            for node in solver.nodes.values():
                node.update_strategy()
            solver._walk(solver.root, *solver.weights, iteration=iteration, update_player=side)
        solver.iterations = iteration
        if iteration in marks:
            checkpoints.append(solver.diagnostics())
    return checkpoints


class TurnTrainingTests(unittest.TestCase):
    def assert_same_state(self, first, second):
        self.assertEqual(list(first.nodes), list(second.nodes))
        self.assertEqual(first.effective_bets, second.effective_bets)
        for name, node in first.nodes.items():
            other = second.nodes[name]
            self.assertEqual(node.actions, other.actions)
            for field in ('regret', 'strategy_sum', 'strategy'):
                np.testing.assert_array_equal(getattr(node, field), getattr(other, field), err_msg=name+'/'+field)
            np.testing.assert_array_equal(node.average(), other.average(), err_msg=name+'/average')

    def assert_same_evaluation(self, first, second):
        left, right = {}, {}
        values = first._walk(first.root, *first.weights, collect=left)
        expected = second._walk(second.root, *second.weights, collect=right)
        for actual, baseline in zip(values, expected, strict=True):
            np.testing.assert_array_equal(actual, baseline)
        self.assertEqual(left.keys(), right.keys())
        for name, row in left.items():
            for field, actual in row.items():
                np.testing.assert_array_equal(actual, right[name][field], err_msg=name+'/'+field)
        self.assertEqual(first.diagnostics(), second.diagnostics())

    def test_training_pass_matches_both_player_walk(self):
        configs = [BASE,
                   BASE | dict(turn_bet_sizes=[], river_bet_sizes=[]),
                   BASE | dict(turn_bet_sizes=[], river_bet_sizes=[0.5]),
                   BASE | dict(turn_bet_sizes=[0.5], river_bet_sizes=[]),
                   BASE | dict(stack=80, turn_bet_sizes=[0.5, 1.0], river_bet_sizes=[0.5, 1.0]),
                   BASE | dict(stack=100, turn_bet_sizes=[1.0], river_bet_sizes=[0.5]),
                   BASE | dict(oop_range='KhKd:1e-15,AsKs:3e-16', ip_range='AsAd:1e-15,QhJd:7e-16'),
                   BASE | dict(oop_range='AA,KK,QQ,JJ', ip_range='AA,KK,QQ,JJ',
                               turn_bet_sizes=[0.5, 1.0], river_bet_sizes=[0.5, 1.0])]
        rng = np.random.default_rng(26)
        for config in configs:
            seed = TurnSolver(**config)
            for node in seed.nodes.values():
                node.regret[:] = rng.uniform(-1, 2, size=node.regret.shape)
                node.strategy_sum[:] = rng.uniform(0, 1, size=node.strategy_sum.shape)
                node.update_strategy()
            for side in (0, 1):
                with self.subTest(config=config, side=side):
                    actual, expected = deepcopy(seed), deepcopy(seed)
                    value = actual._train(actual.root, *actual.weights, 7, side)
                    baseline = expected._walk(expected.root, *expected.weights, iteration=7, update_player=side)[side]
                    np.testing.assert_array_equal(value, baseline)
                    self.assert_same_state(actual, expected)
                    self.assert_same_evaluation(actual, expected)

    def test_full_2000_iteration_schedule_and_all_node_values_match(self):
        configs = [BASE,
                   BASE | dict(oop_range='KhKd,AsKs:0.3', ip_range='AsAd,QhJd:0.7'),
                   BASE | dict(stack=100, turn_bet_sizes=[1.0], river_bet_sizes=[0.5])]
        for config in configs:
            with self.subTest(config=config):
                actual, expected = TurnSolver(**config), TurnSolver(**config)
                result = actual.solve(2000)
                checkpoints = old_training_schedule(expected, 2000)
                self.assertEqual(result['checkpoints'], checkpoints)
                self.assert_same_state(actual, expected)
                self.assert_same_evaluation(actual, expected)

    def test_preseeded_regrets_and_general_tree_schedule_match(self):
        rng = np.random.default_rng(32)
        configs = [BASE | dict(turn_bet_sizes=[], river_bet_sizes=[]),
                   BASE | dict(turn_bet_sizes=[0.5, 1.0], river_bet_sizes=[0.5, 1.0]),
                   BASE | dict(oop_range='KhKd:1e-15,AsKs:3e-16', ip_range='AsAd:1e-15,QhJd:7e-16')]
        for config in configs:
            actual = TurnSolver(**config)
            for node in actual.nodes.values():
                # Leave current strategies stale to test first-pass refresh.
                node.regret[:] = rng.uniform(-1, 2, size=node.regret.shape)
                node.strategy_sum[:] = rng.uniform(0, 1, size=node.strategy_sum.shape)
            expected = deepcopy(actual)
            with self.subTest(config=config):
                result = actual.solve(24)
                self.assertEqual(result['checkpoints'], old_training_schedule(expected, 24))
                self.assert_same_state(actual, expected)
                self.assert_same_evaluation(actual, expected)

    def test_training_preserves_matched_showdown_assertion(self):
        solver = TurnSolver(**BASE)
        leaf = Terminal('runout', (10, 20), 0)
        for side in (0, 1):
            with self.assertRaisesRegex(AssertionError, 'matched contributions'):
                solver._train(leaf, *solver.weights, 1, side)
        with self.assertRaisesRegex(AssertionError, 'matched contributions'):
            solver._walk(leaf, *solver.weights)


if __name__ == '__main__':
    unittest.main()
