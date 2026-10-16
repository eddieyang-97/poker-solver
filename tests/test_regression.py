import itertools
import math
import unittest

import numpy as np

from poker_spot.core import RiverSolver, cards, evaluate_river_call, expand_range, rank7


class RegressionTests(unittest.TestCase):
    def test_double_trips_three_pairs_and_board_ties(self):
        self.assertEqual(rank7(tuple('As Ah Ad Ks Kh Kd 2c'.split())), (6, 14, 13))
        self.assertEqual(rank7(tuple('As Ah Ks Kh Qs Qh 2c'.split())), (2, 14, 13, 12))
        tied = evaluate_river_call('As,Ks,Qs,Js,Ts', '2h3h', '4c5c,6c7c:0.2', 100, 100)
        self.assertEqual(tied['hero_equity_vs_assumed_betting_range'], 0.5)
        self.assertEqual(tied['ev_call_minus_fold'], 50)

    def test_weights_blockers_and_indifference(self):
        # Exactly one losing value combo and one winning bluff combo after hero removal.
        out = evaluate_river_call('Ks,9s,5h,Td,Ts', 'KdQd', 'AsJs:1,AsJh:0.5,KdJd', 100, 100)
        self.assertEqual(out['opponent_combos_after_blockers'], 2)
        self.assertEqual(out['weighted_opponent_combos_after_blockers'], 1.5)
        self.assertEqual(out['best_action_given_range'], 'indifferent')
        self.assertAlmostEqual(out['hero_equity_vs_assumed_betting_range'], 1/3, places=6)
        ranges = expand_range('AKs:0.5,AA:0,AsJh:0.2', cards('Ks,9s,5h,Td,Ts', 5))
        self.assertEqual(sum(ranges.values()), 1.7)
        self.assertTrue(all('Ks' not in hand for hand in ranges))

    def test_nonfinite_invalid_sizes_and_impossible_queries(self):
        for v in (math.inf, math.nan, -1, True):
            with self.assertRaises(ValueError):
                RiverSolver('2c,3d,4h,8s,9c', 'AA', 'KK', v, 100)
            with self.assertRaises(ValueError):
                evaluate_river_call('2c,3d,4h,8s,9c', 'AsAd', 'KK', 100, v)
        for sizes in ([0.5, 1.0], [1.0, 1.0], [math.nan], [True]):
            with self.assertRaises(ValueError):
                RiverSolver('2c,3d,4h,8s,9c', 'AA', 'KK', 100, 40, sizes)
        solver = RiverSolver('2c,3d,4h,8s,9c', 'AsAd,KhKd', 'AsQd', 100, 100, [1.0])
        with self.assertRaises(ValueError):
            solver.solve(100, oop_hand='AsAd')

    def test_overlapping_range_order_in_acceptance_bluffcatch(self):
        # QJs includes QsJs: later tokens replace that combo's earlier weight.
        # KdQd also removes QdJd. Five half-weight bluffs contribute 2.5 wins.
        common = 'AsQs,Js8s,99:0.5,55:0.25'
        bluffs = 'AsJh:0.5,AsQh:0.5,AsQc:0.5,AhQh:0.5,AhJh:0.5'
        results = []
        for overlap in ('QsJs,QJs:0.5', 'QJs:0.5,QsJs'):
            result = evaluate_river_call('Ks,9s,5h,Td,Ts', 'KdQd',
                                        f'{common},{overlap},{bluffs}', 505, 450)
            self.assertEqual(result['opponent_combos_after_blockers'], 16)
            self.assertEqual(result['best_action_given_range'], 'fold')
            results.append(result)
        self.assertEqual([r['weighted_opponent_combos_after_blockers'] for r in results], [8.25, 8.75])
        self.assertEqual([r['ev_call_minus_fold'] for r in results], [-24.2424, -48.5714])
        for result, total in zip(results, (8.25, 8.75)):
            self.assertAlmostEqual(result['hero_equity_vs_assumed_betting_range'], 2.5/total, places=6)

    def test_polarized_analytical_equilibrium_for_two_sizes(self):
        # IP equally weighted nuts/air vs one bluffcatcher, with no card collisions.
        # Indifference gives IP air bet B/(P+B), OOP call P/(P+B).
        for fraction in (0.5, 1.0):
            solver = RiverSolver('2c,3d,4h,8s,9c', 'KhKd', 'AsAd,QhJd', 100, 100, [fraction])
            out = solver.solve(1500, 'KhKd', 'QhJd')
            ip = out['hands']['ip']['node_strategy']['ip_after_oop_check']['frequency']
            oop = out['hands']['oop']['node_strategy'][f'oop_facing_ip_bet_{fraction:g}']['frequency']
            self.assertAlmostEqual(ip[f'bet_{fraction:g}pot'], fraction/(1+fraction), delta=0.04)
            self.assertAlmostEqual(oop['call'], 1/(1+fraction), delta=0.04)
            self.assertLess(out['nash_conv_pct_pot'], 0.5)

    def test_nashconv_against_exhaustive_pure_strategy_deviations(self):
        solver = RiverSolver('2c,3d,4h,8s,9c', 'KhKd', 'AsAd,QhJd:0.7', 100, 100, [1.0])
        out = solver.solve(200)
        base = {name: node.average().copy() for name, node in solver.nodes.items()}

        def expected():
            vals = solver._eval(solver.root, solver.w0, solver.w1)
            return float(solver.w0 @ vals[0]/solver.prob)

        best = []
        for side in (0, 1):
            nodes = [node for node in solver.nodes.values() if node.player == side]
            infosets = [(node, hand) for node in nodes for hand in range(node.n_hands)]
            values = []
            for actions in itertools.product((0, 1), repeat=len(infosets)):
                for node in solver.nodes.values():
                    node.avg_sum = base[node.name].copy()
                for (node, hand), action in zip(infosets, actions):
                    node.avg_sum[hand] = np.eye(2)[action]
                values.append(expected())
            best.append(max(values) if side == 0 else -min(values))
        self.assertAlmostEqual(out['nash_conv_chips'], sum(best), places=3)


if __name__ == '__main__':
    unittest.main()
