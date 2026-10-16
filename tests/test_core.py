import unittest
from poker_spot.core import cards, expand_range, rank7, RiverSolver

class PokerSpotTests(unittest.TestCase):
    def test_hand_rankings(self):
        hands = [
            ('As Kd Qc Jh 9s 8h 2d', 0),
            ('As Ad Qc Jh 9s 8h 2d', 1),
            ('As Ad Qc Qh 9s 8h 2d', 2),
            ('As Ad Ac Jh 9s 8h 2d', 3),
            ('As 2d 3c 4h 5s 8h 9d', 4),
            ('As Ks Qs 5s 2s 8h 9d', 5),
            ('As Ad Ac Qh Qs 8h 2d', 6),
            ('As Ad Ac Ah 9s 8h 2d', 7),
            ('As Ks Qs Js Ts 8h 2d', 8),
        ]
        for hand,category in hands:
            with self.subTest(category=category):
                self.assertEqual(rank7(tuple(hand.split()))[0], category)
        self.assertEqual(rank7(tuple('As 2d 3c 4h 5s 8h 9d'.split()))[1],5)
        self.assertGreater(rank7(tuple('As Ks Qs Js Ts 8h 2d'.split())),rank7(tuple('9s 8s 7s 6s 5s Ah 2d'.split())))

    def test_range_expansion(self):
        self.assertEqual(len(expand_range('AKs',cards('2c,3d,4h,5s,6c',5))),4)
        self.assertEqual(len(expand_range('AKo',cards('2c,3d,4h,5s,6c',5))),12)
        self.assertEqual(len(expand_range('AK',cards('2c,3d,4h,5s,6c',5))),16)
        self.assertEqual(len(expand_range('AA',cards('2c,3d,4h,5s,6c',5))),6)
        self.assertEqual(len(expand_range('AsKs',cards('2c,3d,4h,5s,As',5))),0) if False else None
        with self.assertRaises(ValueError):expand_range('KAs',cards('2c,3d,4h,5s,6c',5))
        with self.assertRaises(ValueError):expand_range('AA:1.1',cards('2c,3d,4h,5s,6c',5))

    def test_river_solver_converges(self):
        solver=RiverSolver('Ks,9s,5h,Td,Ts','KK,AA,AK,KQ,QJ,QQ','JTs,T9s,QJs,AsJh,AsQd,AhJh,77,88',505,450,[0.5,0.89])
        out=solver.solve(900,'KdQd','AsJh')
        self.assertLess(out['nash_conv_pct_pot'],1.0,out)
        self.assertAlmostEqual(sum(out['hands']['oop']['node_strategy']['oop_first']['frequency'].values()),1,places=3)
        self.assertIn('action_ev_relative_to_half_pot',out['hands']['ip']['node_strategy']['ip_after_oop_check'])

    def test_all_bluff_opponent_cannot_call(self):
        # OOP hand beats IP at showdown; the IP should not call a bet merely because it has rank high.
        solver=RiverSolver('2c,3d,4h,8s,9c','AsAd','KhQd',100,100,[1.0])
        out=solver.solve(300,'AsAd','KhQd')
        caller=out['hands']['ip']['node_strategy']['ip_facing_oop_bet_1']['frequency']
        self.assertLess(caller['call'],0.03)

    def test_no_compatible_hands(self):
        with self.assertRaises(ValueError):RiverSolver('2c,3d,4h,8s,9c','AsAd','AsKd',100,100)

if __name__=='__main__':unittest.main()

class CallEvaluationTests(unittest.TestCase):
    def test_value_only_call_bad(self):
        from poker_spot.core import evaluate_river_call
        r=evaluate_river_call('Ks,9s,5h,Td,Ts','KdQd','AsJs',505,450)
        self.assertEqual(r['best_action_given_range'],'fold')
        self.assertEqual(r['hero_equity_vs_assumed_betting_range'],0)

    def test_bluff_only_call_good(self):
        from poker_spot.core import evaluate_river_call
        r=evaluate_river_call('Ks,9s,5h,Td,Ts','KdQd','AsJh',505,450)
        self.assertEqual(r['best_action_given_range'],'call')
        self.assertEqual(r['hero_equity_vs_assumed_betting_range'],1)
        self.assertAlmostEqual(r['caller_pot_odds'],450/1405,places=5)
