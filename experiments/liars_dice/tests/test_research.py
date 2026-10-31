import contextlib
import io
from array import array
from itertools import product
import math
from pathlib import Path
import random
import runpy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import Bid, Game, Rules, contribution, hand_distribution
from mccfr import Info, Solver
from one_face import ExactCFR, OneFace, PRIOR, VALUES, evaluate
from run_abstraction import Adjacent, expand_policy
from summarize import complexity, lower_bound
from beliefs import posterior, challenge_ev


class RulesTests(unittest.TestCase):
    def test_exhaustive_weighting_and_original_scoring(self):
        with contextlib.redirect_stdout(io.StringIO()):
            archived = runpy.run_path(str(Path(__file__).resolve().parents[1] / "liars_dice_analysis.py"))
        self.assertEqual(len(hand_distribution()), 252)
        self.assertEqual(sum(n for _, n in hand_distribution()), 7776)
        frequencies = {m: [0]*8 for m in ("fly", "zhai")}
        for hand in product(range(1, 7), repeat=5):
            for mode in frequencies:
                count = contribution(hand, 4, mode)
                self.assertEqual(count, archived["fly_count" if mode == "fly" else "zhai_count"](hand))
                frequencies[mode][count] += 1
        self.assertEqual(frequencies["fly"], [1024,2560,2560,1280,320,0,30,2])
        self.assertEqual(frequencies["zhai"], [3125,3125,1250,250,25,0,0,1])
        # Independent binomial oracle before the five-matching-dice bonus.
        for k in range(5):
            self.assertEqual(frequencies["fly"][k], math.comb(5,k)*2**k*4**(5-k))
            self.assertEqual(frequencies["zhai"][k], math.comb(5,k)*5**(5-k))

    def test_edge_cases_and_sensitivity(self):
        self.assertEqual(contribution((1,1,4,4,4), 4, "fly"), 6)
        self.assertEqual(contribution((1,1,4,4,4), 4, "zhai"), 3)
        self.assertEqual(contribution((1,1,4,4,4), 4, "zhai", Rules(zhai_mixed_bonus=True)), 6)
        for face in range(1,7):
            self.assertEqual(contribution((face,)*5, face, "fly"), 7)
            self.assertEqual(contribution((face,)*5, face, "zhai"), 7)
        self.assertEqual(contribution((1,)*5, 4, "fly"), 7)
        self.assertEqual(contribution((1,)*5, 4, "fly", Rules(all_ones_wild_seven=False)), 6)
        self.assertEqual(contribution((1,)*5, 4, "zhai"), 0)
        self.assertEqual(contribution((1,1,2,2,2), 1, "fly"), 2)
        for bad in ((1,)*4, (0,1,2,3,4), (True,2,3,4,5)):
            with self.assertRaises(ValueError):
                contribution(bad,4,"fly")

    def test_action_edges_acyclic_and_exhaustive(self):
        game = Game()
        for i, last in enumerate(game.bids):
            for j, bid in enumerate(game.bids):
                legal = j in game.actions((i,))
                if last.mode == bid.mode:
                    expected = bid.quantity > last.quantity or (bid.quantity == last.quantity and bid.face > last.face)
                else:
                    expected = bid.quantity >= last.quantity + (-1 if last.mode == "fly" else 2)
                self.assertEqual(legal, expected)
                if legal:
                    self.assertGreater(bid.rank, last.rank)
            self.assertIn(-1, game.actions((i,)))
        self.assertNotIn(-1, game.actions(()))
        self.assertTrue(all(game.bids[a].quantity >= 3 for a in game.actions(())))
        i = game.bids.index(Bid(3,6,"fly"))
        self.assertIn(game.bids.index(Bid(2,1,"zhai")), game.actions((i,)))
        i = game.bids.index(Bid(3,1,"zhai"))
        self.assertNotIn(game.bids.index(Bid(4,6,"fly")), game.actions((i,)))
        self.assertIn(game.bids.index(Bid(5,1,"fly")), game.actions((i,)))
        other = Game(Rules(face_one=False, opening_zhai=False, quantity_floor=3))
        self.assertTrue(all(b.face != 1 and b.quantity >= 3 for b in other.bids))
        self.assertTrue(all(other.bids[a].mode == "fly" for a in other.actions(())))

    def test_terminal_seats_and_information(self):
        game = Game()
        strong = game.hands.index((4,)*5)
        weak = game.hands.index((2,)*5)
        bid = game.bids.index(Bid(14,4,"fly"))
        self.assertEqual(game.payoff((bid,), (strong,strong), 1), 1)
        self.assertEqual(game.payoff((bid,), (weak,strong), 1), -1)
        self.assertEqual(game.payoff((bid,), (strong,strong), 0), -1)
        self.assertNotEqual(game.key(0,strong,(1,2)), game.key(0,strong,(3,2)))

    def test_complexity_dynamic_program_against_enumeration(self):
        class Small:
            bids = (Bid(3,1,"fly"), Bid(4,1,"fly"), Bid(5,1,"fly"))

            def actions(self, history):
                return tuple(range(3)) if not history else tuple([-1]+list(range(history[-1]+1,3)))
        result = complexity(Small())
        self.assertEqual(result["public_decision_histories"], "8")
        self.assertEqual(result["maximum_bids_before_challenge"],3)

    def test_action_abstraction_expands_in_full_game(self):
        full, abstract = Game(), Adjacent()
        self.assertEqual(len(abstract.actions(())),12)
        for history in [()]+[(a,) for a in range(len(full.bids))]:
            subset = abstract.actions(history)
            self.assertTrue(set(subset) <= set(full.actions(history)))
            for a in subset:
                if a == -1:
                    continue
                bid = full.bids[a]
                self.assertFalse(any(full.bids[b].mode == bid.mode and full.bids[b].face == bid.face
                                     and full.bids[b].quantity < bid.quantity
                                     for b in full.actions(history) if b != -1))
        solver = Solver(abstract)
        expanded = expand_policy(solver,full)(0,0,())
        self.assertAlmostEqual(sum(expanded),1)
        self.assertEqual(sum(p > 0 for p in expanded),12)
        # An opponent's omitted jump remains a valid full-game input history.
        jump = full.bids.index(Bid(10,4,"fly"))
        self.assertAlmostEqual(sum(expand_policy(solver,full)(1,0,(jump,))),1)

    def test_response_bound_is_not_an_upper_bound(self):
        rows = {f"b{i}_solver_seat{seat}": {"games":2000,"ev_p0": -.9 if seat == 0 else .9}
                for i in range(4) for seat in (0,1)}
        result = lower_bound(rows)
        self.assertGreater(result["nashconv_lower_bound_95_familywise"],1.6)
        self.assertIsNone(result["exploitability_upper_bound"])


class SolverTests(unittest.TestCase):
    def test_importance_average_includes_zero_target_support_hands(self):
        game = OneFace(4)
        expected_regret, expected_average = [0.,0.], [0.,0.]

        class ScriptedRNG:
            def __init__(self, path):
                self.path = iter(path)

            def choices(self, population, weights):
                return [next(self.path)]

        my_type = 2
        policy = [.75,.25]
        correct = [0.,0.]
        for opp, prior in enumerate(PRIOR):
            opening = [0.,1.] if opp == 0 else [.8,.2]
            sampled_open3 = .95*opening[0]+.05/2
            a0 = -game.payoff((3,), (opp,my_type),1)
            a1 = -game.payoff((3,4), (opp,my_type),0)
            mean = policy[0]*a0+policy[1]*a1
            for a, utility in enumerate((a0,a1)):
                correct[a] += prior*opening[0]*(utility-mean)
            for path, chance in (((0,0),sampled_open3*.6),
                                 ((0,1,0),sampled_open3*.4), ((1,0),1-sampled_open3)):
                solver = Solver(game)
                solver.infos[(0,opp,())] = Info(array('d',opening),array('d',[0,0]))
                solver.infos[(1,my_type,(3,))] = Info(array('d',policy),array('d',[0,0]))
                solver.rng = ScriptedRNG(path)
                solver.episode(1,(opp,my_type))
                node = solver.infos[(1,my_type,(3,))]
                for a in range(2):
                    expected_regret[a] += prior*chance*(node.regret[a]-policy[a])
                    expected_average[a] += prior*chance*node.average[a]
        for a in range(2):
            self.assertAlmostEqual(expected_regret[a],correct[a])
            self.assertAlmostEqual(expected_average[a],policy[a])

    def test_action_conditioning_and_zero_support(self):
        game = OneFace(4)

        def signalling(p,t,h):
            return [1.0,0.0] if t < 3 else [0.0,1.0]
        weights = posterior(game,1,(3,),signalling)
        self.assertAlmostEqual(sum(weights),1)
        self.assertTrue(all(weights[t] == 0 for t in range(3,7)))
        self.assertAlmostEqual(weights[0], PRIOR[0]/sum(PRIOR[:3]))
        # Own type0 + opponent type0/1/2: opening3 is always false.
        self.assertAlmostEqual(challenge_ev(game,1,0,(3,),signalling),1)
        prior_ev = challenge_ev(game,1,0,(3,),lambda p,t,h:[.5,.5])
        self.assertLess(prior_ev,1)
        with self.assertRaises(ValueError):
            posterior(game,1,(3,),lambda p,t,h:[0.,1.])
        with self.assertRaises(ValueError):
            posterior(game,1,(4,3),signalling)
        with self.assertRaises(ValueError):
            challenge_ev(game,0,0,(3,),signalling)

    def test_outcome_estimator_matches_exact_expectation(self):
        # Enumerate chance and ALL sampled trajectories with frozen uniform
        # initial policies. This checks prefix/tail importance factors directly.
        game = OneFace(4)
        expected = [0.0, 0.0]

        class ScriptedRNG:
            def __init__(self, choices):
                self.script = iter(choices)

            def choices(self, population, weights):
                return [next(self.script)]

        my_type = 2
        for opp, probability in enumerate(PRIOR):
            for path, chance in (((0,0),.25), ((0,1,0),.25), ((1,0),.5)):
                solver = Solver(game)
                solver.rng = ScriptedRNG(path)
                solver.episode(1, (opp,my_type))
                node = solver.infos.get((1,my_type,(3,)))
                if node:
                    for a in range(2):
                        expected[a] += probability*chance*node.regret[a]
        action_values = [sum(p*(-game.payoff((3,), (t,my_type), 1)) for t,p in enumerate(PRIOR)),
                         sum(p*(-game.payoff((3,4), (t,my_type), 0)) for t,p in enumerate(PRIOR))]
        mean = sum(action_values)/2
        for a in range(2):
            self.assertAlmostEqual(expected[a], .5*(action_values[a]-mean))

    def test_exact_br_analytic_forced_game(self):
        game = OneFace(3)
        result = evaluate(game, lambda p,t,h:[1.0])
        truth = sum(p*q for a,p in zip(VALUES,PRIOR) for b,q in zip(VALUES,PRIOR) if a+b >= 3)
        self.assertAlmostEqual(result["ev_p0"], 2*truth-1)
        self.assertAlmostEqual(result["nashconv"], 0)

    def test_br_against_enumerated_small_pure_plans(self):
        game = OneFace(4)
        # Responder faces opening 3, then call or raise4 (always challenged).
        # Opening player's action depends on own type, which updates the belief.
        def policy(p,t,h):
            if not h:
                return [.9 if t < 3 else .1, .1 if t < 3 else .9]
            return [1/len(game.actions(h))]*len(game.actions(h))
        result = evaluate(game, policy)
        best0 = best1 = 0
        for me, pm in enumerate(PRIOR):
            options0, options1 = [], []
            for opening in (3,4):
                val = 0
                for opp, po in enumerate(PRIOR):
                    if opening == 4:
                        v = game.payoff((4,), (me,opp), 1)
                    else:
                        v = .5*game.payoff((3,), (me,opp), 1)+.5*game.payoff((3,4), (me,opp), 0)
                    val += po*v
                options0.append(val)
            best0 += pm*max(options0)
            # Enumerate all responder plans for this own type (call/raise at 3).
            for call in (True,False):
                val = 0
                for opp, po in enumerate(PRIOR):
                    open3, open4 = policy(0,opp,())
                    v3 = -game.payoff((3,), (opp,me), 1) if call else -game.payoff((3,4), (opp,me), 0)
                    val += po*(open3*v3-open4*game.payoff((4,), (opp,me), 1))
                options1.append(val)
            best1 += pm*max(options1)
        self.assertAlmostEqual(result["br0"], best0)
        self.assertAlmostEqual(result["br1"], best1)

    def test_convergence_against_exact_small_game(self):
        game = OneFace(5)
        exact = ExactCFR(game)
        exact.train(500)
        reference = evaluate(game,exact.policy)
        self.assertLess(reference["nashconv"], .005)
        sampled = Solver(game,seed=42)
        sampled.train(40000)
        result = evaluate(game,sampled.policy)
        self.assertLess(result["nashconv"], .06)
        self.assertLess(abs(result["ev_p0"]-reference["ev_p0"]), .03)
        self.assertGreaterEqual(result["gain0"], -1e-12)
        self.assertGreaterEqual(result["gain1"], -1e-12)

    def test_budget_invalid_inputs_and_unseen_fallback(self):
        game = OneFace(5)
        for exp in (0,-1,1.1):
            with self.assertRaises(ValueError):
                Solver(game, exploration=exp)
            with self.assertRaises(ValueError):
                Solver(game, opponent_exploration=exp)
        solver = Solver(game,max_infos=1)
        self.assertEqual(solver.policy(0,0,()), [1/3]*3)
        with self.assertRaises(MemoryError):
            solver.train(10)
        with self.assertRaises(ValueError):
            evaluate(game,lambda p,t,h:[float("nan")]*len(game.actions(h)))

    def test_full_game_smoke_no_invalid_policy_or_moves(self):
        game = Game()
        solver = Solver(game,seed=7)
        solver.train(20)
        rng = random.Random(11)
        for _ in range(20):
            hands, history = game.sample(rng), ()
            for _ in range(200):
                player = len(history)%2
                s = solver.policy(player,hands[player],history)
                self.assertAlmostEqual(sum(s),1)
                self.assertTrue(all(math.isfinite(p) and p >= 0 for p in s))
                action = rng.choices(game.actions(history),weights=s)[0]
                if action == -1:
                    self.assertIn(game.payoff(history,hands,player),(-1,1))
                    break
                history += (action,)
            else:
                self.fail("Game did not terminate")


if __name__ == "__main__":
    unittest.main()
