import copy
import itertools
import json
from pathlib import Path
import unittest

import numpy as np

from benchmarks.raises import (check_tree, compare, policy_delta, product_profile, product_value,
                                reference_game, set_profile)
from poker_spot.core import Node, rank7
from poker_spot.raises import RaiseRiverSolver, Terminal
from scripts.benchmark_river_raises import random_policy_checks
from scripts.solve_river_raises import execute

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT/'benchmarks/raise-fixtures.json').read_text())[1]['config']


def scalar_value(solver, policy, target=0):
    """Explicit deals and a separately carried chip ledger; never read leaf payoffs."""
    total = mass = 0

    def visit(node, hands, paid, winner=None):
        if not isinstance(node, Node):
            if winner is None:
                scores = [rank7(tuple(sorted(solver.board+h))) for h in hands]
                winner = 0 if scores[0] > scores[1] else 1 if scores[1] > scores[0] else None
            if winner is None:
                value = (paid[1]-paid[0])/2
            else:
                value = solver.pot/2+paid[1] if winner == 0 else -solver.pot/2-paid[0]
            return value if target == 0 else -value
        weights = policy[node.name][hands[node.player]]
        out = 0
        for action, child, probability in zip(node.actions, node.children, weights, strict=True):
            next_paid = list(paid)
            if '_to_' in action:
                next_paid[node.player] = float(action.split('_to_')[1])
            elif action == 'call':
                next_paid[node.player] = max(paid)
            folded = 1-node.player if action == 'fold' else None
            out += probability*visit(child, hands, next_paid, folded)
        return out

    for i, h0 in enumerate(solver.h0):
        for j, h1 in enumerate(solver.h1):
            if set(h0) & set(h1):
                continue
            weight = solver.w0[i]*solver.w1[j]
            total += weight*visit(solver.root, (h0, h1), [0, 0])
            mass += weight
    return total/mass


class RaiseTests(unittest.TestCase):
    def test_tree_and_raise_total_semantics(self):
        solver = RaiseRiverSolver(**CONFIG)
        self.assertEqual(solver.nodes['c/b5000'].player, 0)
        self.assertIn('raise_to_150.00', solver.nodes['c/b5000'].actions)
        self.assertIn('raise_to_150.00', solver.nodes['b5000'].actions)
        for key in ('b5000/r10000', 'c/b5000/r10000'):
            self.assertEqual(solver.nodes[key].actions, ('fold', 'call'))
            self.assertEqual(solver.locations[key]['additional_raises_used'], 1)
        self.assertEqual(len(solver.nodes), 6)

    def test_called_raise_and_fold_refund_terminal_formulas(self):
        solver = RaiseRiverSolver(**dict(CONFIG, oop_range='AsAd', ip_range='KsKc'))
        leaf = solver.terminals['c/b5000/r10000/f']
        self.assertEqual(leaf.contributions, (15000, 5000))
        self.assertEqual(leaf.refunds, (10000, 0))
        self.assertEqual(leaf.settled, (5000, 5000))
        for key, expected in (('c/b5000/r10000/f', 100), ('c/b5000/r10000/c', 200), ('b5000/r10000/f', -100)):
            values = solver._terminal(solver.terminals[key], solver.w0, solver.w1)
            self.assertEqual(float(values[0][0]), expected)
            self.assertEqual(float(values[1][0]), -expected)
        tie = RaiseRiverSolver(**dict(CONFIG, oop_range='AsAd', ip_range='AhAc'))
        self.assertEqual(float(tie._terminal(tie.terminals['c/b5000/r10000/c'], tie.w0, tie.w1)[0][0]), 0)

    def test_stack_caps_short_allin_raise_and_no_empty_sidepot(self):
        short = RaiseRiverSolver(**dict(CONFIG, stack=75))
        row = next(a for a in short.locations['c/b5000']['actions'] if a['kind'] == 'raise')
        self.assertEqual(row['total_to_cents'], 7500)
        self.assertFalse(row['full_raise'])
        self.assertTrue(row['all_in'])
        self.assertEqual(short.nodes['c/b5000/r2500'].actions, ('fold', 'call'))
        opening = RaiseRiverSolver(**dict(CONFIG, stack=50))
        self.assertEqual(opening.nodes['b5000'].actions, ('fold', 'call'))
        self.assertEqual(opening.nodes['c/b5000'].actions, ('fold', 'call'))
        tiny = RaiseRiverSolver(**dict(CONFIG, stack=1))
        self.assertEqual(tiny.bet_cents, [100])
        fractional = RaiseRiverSolver(**dict(CONFIG, pot=100.2, bet_sizes=[0.1]))
        self.assertEqual(fractional.solve(20)['effective_bet_amounts'], [10.02])
        self.assertIn('b1002/r6012', fractional.nodes)

    def test_invalid_sizes_minimum_raises_rounding_and_bounds(self):
        for change in ({'pot': 100.01}, {'raise_sizes': [0.01]}, {'raise_sizes': [0.333333]},
                       {'stack': 100, 'raise_sizes': [0.5, 1]}, {'stack': 50, 'bet_sizes': [0.5, 1]},
                       {'minimum_bet': 60}, {'bet_sizes': [True]}, {'stack': float('nan')},
                       {'raise_sizes': [1, 0.5]}, {'bet_sizes': [0.25, 0.5, 1]}, {'oop_range': 'AK,AQ'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RaiseRiverSolver(**dict(CONFIG, **change))
        solver = RaiseRiverSolver(**CONFIG)
        for n in (True, 0, 5001):
            with self.assertRaises(ValueError):
                solver.solve(n)
        with self.assertRaises(ValueError):
            solver.solve(20, '2c2d')

    def test_card_removal_queries_and_no_compatible_deals(self):
        solver = RaiseRiverSolver(**dict(CONFIG, oop_range='2c2d,AsAd,KhKd'))
        self.assertEqual(len(solver.h0), 2)
        with self.assertRaises(ValueError):
            RaiseRiverSolver(**dict(CONFIG, oop_range='AsAd', ip_range='AsKh'))

    def test_global_range_scaling_preserves_all_action_evs(self):
        first = RaiseRiverSolver(**CONFIG).solve(400, 'AsAd', 'KsKc')
        for side in ('oop_range', 'ip_range'):
            scaled = copy.deepcopy(CONFIG)
            scaled[side] = ','.join(t.split(':')[0]+':'+str(float(t.split(':')[1])*1e-15) for t in scaled[side].split(','))
            actual = RaiseRiverSolver(**scaled).solve(400, 'AsAd', 'KsKc')
            self.assertEqual(first['hands'], actual['hands'])
            self.assertEqual(first['nash_conv_chips'], actual['nash_conv_chips'])

    def test_scalar_mixed_policy_and_exhaustive_hidden_hand_best_responses(self):
        solver = RaiseRiverSolver(**dict(CONFIG, oop_range='AsAd:1,KhKd:0.4', ip_range='AhAc:0.6,KsKc:1'))
        rng = np.random.default_rng(13013)
        for _ in range(3):
            for node in solver.nodes.values():
                node.avg_sum = rng.random(node.avg_sum.shape)+0.1
            policy = {key: {h: node.average()[i].copy() for i, h in enumerate(solver.h0 if node.player == 0 else solver.h1)}
                      for key, node in solver.nodes.items()}
            actual = product_value(solver)
            self.assertAlmostEqual(scalar_value(solver, policy), actual['root'][0], places=10)
            for side in (0, 1):
                hands = solver.h0 if side == 0 else solver.h1
                infos = [(key, h, len(node.actions)) for key, node in solver.nodes.items() if node.player == side for h in hands]
                best = -float('inf')
                for choices in itertools.product(*(range(n) for _, _, n in infos)):
                    chosen = copy.deepcopy(policy)
                    for (key, hand, n), action in zip(infos, choices, strict=True):
                        chosen[key][hand] = np.eye(n)[action]
                    best = max(best, scalar_value(solver, chosen, side))
                self.assertAlmostEqual(best, actual['br'][side], places=10)

    def test_zero_opponent_reach_is_null_not_zero(self):
        solver = RaiseRiverSolver(**CONFIG)
        for node in solver.nodes.values():
            node.avg_sum[:] = 0
            node.avg_sum[:, 0] = 1
        result = solver.solve(20, 'AsAd', 'KsKc')
        # Force an evaluated zero-reach branch after the solve; training can explore it.
        for node in solver.nodes.values():
            node.avg_sum[:] = 0
            node.avg_sum[:, 0] = 1
        values = product_value(solver)
        self.assertTrue(np.isnan(values['nodes']['b5000/r10000']['ev']).all())
        self.assertEqual(result['maximum_additional_raises'], 1)
        with self.assertRaises(ValueError):
            solver.solve(20)

    def test_independent_training_and_bidirectional_mapping(self):
        result = compare(CONFIG, 300, 600)
        self.assertEqual(result['failures'], [])
        self.assertFalse(result['reference_metadata']['product_modules_loaded'])
        for rows in result['query_recommendations'].values():
            self.assertEqual(len(rows), 6)
            for row in rows:
                self.assertAlmostEqual(sum(a['frequency'] for a in row['actions'].values()), 1)
                self.assertGreaterEqual(row['joint_node_reach'], row['joint_queried_hand_reach']-1e-12)
                if row['mixture_conditional_regret'] is not None:
                    self.assertGreaterEqual(row['mixture_conditional_regret'], 0)
        self.assertLess(result['same_policy_max_delta'], 1e-8)
        self.assertLess(random_policy_checks(CONFIG, 13, 4)['maximum_delta'], 1e-8)

    def test_adapter_rejects_tree_and_payoff_faults(self):
        solver = RaiseRiverSolver(**CONFIG)
        game, _ = reference_game(CONFIG)
        check_tree(solver, game)
        game.base_pot += 1
        with self.assertRaises(ValueError):
            check_tree(solver, game)
        game, _ = reference_game(CONFIG)
        game.include_all_in = True
        with self.assertRaises(ValueError):
            check_tree(solver, game)
        game, _ = reference_game(CONFIG)
        node = solver.nodes['c/b5000/r10000']
        node.children = (Terminal((15000, 5001), 0), node.children[1])
        with self.assertRaises(ValueError):
            check_tree(solver, game)
        solver = RaiseRiverSolver(**CONFIG)
        profile = product_profile(solver, game)
        bad = copy.deepcopy(profile)
        bad[0]['root'][1][0][0] = float('nan')
        with self.assertRaises(ValueError):
            set_profile(solver, game, bad)
        bad = copy.deepcopy(profile)
        bad[0]['extra'] = bad[0]['root']
        with self.assertRaises(ValueError):
            set_profile(solver, game, bad)
        set_profile(solver, game, profile)
        original = solver._terminal
        solver._terminal = lambda *args: tuple(v+1 for v in original(*args))
        self.assertGreater(policy_delta(solver, game, profile)[0], 1e-8)

    def test_actual_worker_and_timeout_and_no_hosted_registration(self):
        config = dict(CONFIG, context='post_session', iterations=20)
        result = execute(config)
        self.assertEqual(result['status'], 'computed', result)
        self.assertGreater(result['metrics']['peak_resident_memory']['bytes'], 0)
        self.assertEqual(execute(config, timeout=0.001)['error']['code'], 'TIMEOUT')
        self.assertEqual(execute(dict(config, context='live'))['status'], 'not_run')
        from poker_spot.validation import validate
        with self.assertRaises(ValueError):
            validate('solve_river_raises', config, hosted=True)


if __name__ == '__main__':
    unittest.main()
