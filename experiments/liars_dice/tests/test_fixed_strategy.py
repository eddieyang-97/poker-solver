from pathlib import Path
import hashlib
import json
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixed_strategy import GraphCFR, PublicGraph, TinyDudo, normalize, tree_increments
from game import Game
from one_face import evaluate
from recall_inventory import inventory


class FixedStrategyTests(unittest.TestCase):
    def test_frozen_graph_matches_complete_tree_updates(self):
        game = TinyDudo(3)
        rng = np.random.default_rng(490001)
        for recall in (None, 1, 2):
            solver = GraphCFR(game, recall)
            policies = [normalize(rng.random(r.shape)) for r in solver.regrets]
            # Include exact zeros and opponent-unreachable but counterfactually
            # reachable histories, not just a full-support randomized profile.
            policies[0][:] = 0
            policies[0][:, 0] = 1
            dag = solver.increments(policies)
            tree = tree_increments(game, solver.graph, policies)
            for actual, expected in zip(dag[:2], tree[:2]):
                for a,b in zip(actual,expected):
                    np.testing.assert_allclose(a,b,rtol=0,atol=2e-13)
            self.assertAlmostEqual(dag[2],tree[2],places=13)
            # Repeated updates must also freeze all nodes until the pass ends.
            for _ in range(4):
                dr, da, _ = tree_increments(game,solver.graph,solver.current())
                expected = [r+d for r,d in zip(solver.regrets,dr)]
                expected_average = [a+d for a,d in zip(solver.averages,da)]
                solver.step()
                for a,b in zip(solver.regrets,expected):
                    np.testing.assert_allclose(a,b,rtol=0,atol=2e-13)
                for a,b in zip(solver.averages,expected_average):
                    np.testing.assert_allclose(a,b,rtol=0,atol=2e-13)

    def test_full_recall_training_reduces_exact_exploitability(self):
        game = TinyDudo(2)
        solver = GraphCFR(game)
        initial = evaluate(game,solver.policy)['nashconv']
        for _ in range(300):
            solver.step()
        result = evaluate(game,solver.policy)
        self.assertLess(result['nashconv'], .08)
        self.assertLess(result['nashconv'],initial/5)

    def test_inventory_independent_graph_enumeration_and_budgets(self):
        game = Game()
        report = inventory(game)
        for m, row in zip((1,2),report['rows']):
            graph = PublicGraph(game,m)
            self.assertEqual(row['public_states_with_seat'],len(graph.keys))
            self.assertEqual(row['action_entries'],252*sum(map(len,graph.actions)))
        self.assertEqual(report['reachable_bids'],150)
        self.assertEqual([r['infosets'] for r in report['rows']], [75600,5631192,277716852])
        for kwargs in ({'recall':0},{'max_states':0}):
            with self.assertRaises(ValueError):
                PublicGraph(TinyDudo(),**kwargs)
        with self.assertRaises(MemoryError):
            PublicGraph(TinyDudo(),max_states=2)
        with self.assertRaises(MemoryError):
            GraphCFR(TinyDudo(),max_bytes=1)
        with self.assertRaises(ValueError):
            GraphCFR(game)

    def test_tiny_rules_and_own_information(self):
        game = TinyDudo(3)
        self.assertEqual(game.actions(()),tuple(range(6)))
        self.assertEqual(game.actions((5,)),(-1,))
        # Highest face wild; wild-face claim counts only actual wilds.
        self.assertEqual(game.payoff((3,), (0,2),1),1.)  # two face ones
        self.assertEqual(game.payoff((5,), (0,2),1),-1.)  # two face threes
        solver = GraphCFR(game,1)
        self.assertEqual(solver.graph.key(0,(0,3)),solver.graph.key(0,(1,3)))
        self.assertNotEqual(solver.graph.key(0,(0,3)),solver.graph.key(1,(3,)))
        with self.assertRaises(ValueError):
            solver.policy(1,0,())

    def test_recorded_independent_policy_replay(self):
        # Always runs in ordinary CI without OpenSpiel. This replays retained
        # external outputs, not a claim that CI retrains the external reference.
        base = Path(__file__).resolve().parents[1]
        receipt = json.loads((base/'outputs/fixed-strategy.json').read_text())
        self.assertEqual(receipt['status'],'completed')
        self.assertEqual(receipt['external_reference']['version'],'2.0.2')
        for name, expected in receipt['source_sha256_lf'].items():
            actual = hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            self.assertEqual(actual,expected,name)
        case = next(c for c in receipt['cases'] if c['sides'] == 3)
        game = TinyDudo(3)
        for trainer in case['trainers']:
            record = trainer['evaluation']
            table = record['full_history_policy_table']
            self.assertEqual(hashlib.sha256(json.dumps(table,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                             record['policy_sha256'])
            def policy(player,hand,history):
                key = str(hand+1)+''.join(f' {a//3+1}-{a%3+1}' for a in history)
                row = dict(table[key])
                return [row[6 if a == -1 else a] for a in game.actions(history)]
            result = evaluate(game,policy)
            for name, expected in record['tuple_tree'].items():
                self.assertAlmostEqual(result[name],expected,places=11)
            self.assertAlmostEqual(result['nashconv'],record['openspiel_nashconv'],places=11)
            self.assertAlmostEqual(result['ev_p0'],record['openspiel_ev_p0'],places=11)


if __name__ == '__main__':
    unittest.main()
