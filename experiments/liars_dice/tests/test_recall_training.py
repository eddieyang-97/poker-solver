from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fixed_strategy import GraphCFR, TinyDudo
from game import Game
from recall_training import RecallPolicy, RecallTrainer
from one_face import OneFace, evaluate
from guidance import ProbabilityGuide
from bounded_response import ResponseSearch


class RecallTrainingTests(unittest.TestCase):
    def test_chance_expectation_matches_exact_graph(self):
        game = TinyDudo(3)
        # Nonuniform chance is essential: house-rule multiset probabilities
        # differ greatly, so a uniform-only estimator test is insufficient.
        game.prior = (.6,.3,.1)
        sampled, exact = RecallTrainer(game), GraphCFR(game,1)
        rng = np.random.default_rng(490101)
        for i in range(len(exact.regrets)):
            exact.regrets[i][:] = rng.normal(size=exact.regrets[i].shape)
            for h in range(3):
                sampled.layout.row(sampled.regret,i,h)[:] = exact.regrets[i][h]
        dr, da, ev = exact.increments(exact.current())
        accumulated = [np.zeros_like(r) for r in exact.regrets]
        average = [np.zeros_like(r) for r in exact.regrets]
        root = 0.
        for a in range(3):
            for b in range(3):
                delta, weights, value, _ = sampled.increments((a,b))
                chance = game.prior[a]*game.prior[b]
                root += chance*value
                for i,p in enumerate(sampled.layout.players):
                    accumulated[i][(a,b)[p]] += chance*delta[i]
                    average[i][(a,b)[p]] += chance*weights[i]
        for actual,expected in ((accumulated,dr),(average,da)):
            for a,b in zip(actual,expected):
                np.testing.assert_allclose(a,b,atol=1e-13,rtol=0)
        self.assertAlmostEqual(root,ev,places=13)

    def test_seed_replay_and_only_sampled_own_rows_change(self):
        a,b = RecallTrainer(TinyDudo(3),17),RecallTrainer(TinyDudo(3),17)
        for _ in range(30):
            a.step(); b.step()
        np.testing.assert_array_equal(a.regret,b.regret)
        np.testing.assert_array_equal(a.average,b.average)
        before = a.average.copy()
        a.step((0,1))
        for i,p in enumerate(a.layout.players):
            for hand in range(3):
                if hand != (0,1)[p]:
                    np.testing.assert_array_equal(a.layout.row(before,i,hand),a.layout.row(a.average,i,hand))
        with self.assertRaises(MemoryError):
            RecallTrainer(TinyDudo(3),max_bytes=1)
        with self.assertRaises(ValueError):
            a.step((0,9))

    def test_full_rule_snapshot_legality_identity_and_detachment(self):
        game = Game()
        trainer = RecallTrainer(game,490101)
        for _ in range(4): trainer.step()
        policy = trainer.freeze()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'policy.npz'
            receipt = policy.save(path)
            loaded = RecallPolicy.load(game,path)
            np.testing.assert_array_equal(policy.data,loaded.data)
            self.assertGreater(receipt['bytes'],0)
            with self.assertRaises(ValueError):
                RecallPolicy.load(Game(replace(game.rules,opening_zhai=False)),path)
        seen,stack = {},[()]
        while stack:
            history = stack.pop()
            player = len(history)%2
            key = policy.layout.graph.key(player,history)
            if key in seen: continue
            seen[key] = history
            stack.extend(history+(a,) for a in game.actions(history) if a != -1)
        self.assertEqual(set(seen),set(policy.layout.graph.keys))
        for (player,_),history in seen.items():
            rows = policy.actions(player,history)
            self.assertEqual(set(rows),set(game.actions(history)))
            self.assertTrue(np.allclose(sum(rows.values()),1))
        row = policy.policy(0,0,())
        row[:] = 0
        self.assertAlmostEqual(policy.policy(0,0,()).sum(),1)

    def test_fresh_full_history_responses_bound_and_realize(self):
        class RankedOneFace(OneFace):
            def rank(self,action): return action
        game = RankedOneFace(5)
        trainer = RecallTrainer(game,490102)
        for _ in range(100): trainer.step()
        frozen = trainer.freeze()
        guide = ProbabilityGuide(game)
        exact = evaluate(game,frozen.policy)
        model = SimpleNamespace(target=frozen,actions=frozen.actions)
        for seat in (0,1):
            search = ResponseSearch(game,guide,model,seat,depth=3,max_nodes=1000)
            bound = search.solve()
            self.assertAlmostEqual(bound['lower'],exact[f'br{seat}'],places=11)
            self.assertAlmostEqual(bound['upper'],exact[f'br{seat}'],places=11)
            def policy(p,t,h): return (search if p == seat else frozen).policy(p,t,h)
            realized = evaluate(game,policy)['ev_p0']*(1 if seat == 0 else -1)
            self.assertAlmostEqual(realized,bound['lower'],places=11)

    def test_recorded_snapshots_and_provenance(self):
        base = Path(__file__).resolve().parents[1]
        receipt = json.loads((base/'outputs/recall-training.json').read_text())
        self.assertEqual(receipt['status'],'completed')
        self.assertEqual(len(receipt['runs']),3)
        for name,expected in receipt['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),expected)
        game = Game()
        for run in receipt['runs']:
            record = run['checkpoints'][-1]
            artifact = record['snapshot']
            path = base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            policy = RecallPolicy.load(game,path)
            self.assertEqual(hashlib.sha256(policy.data.astype('<f8').tobytes()).hexdigest(),artifact['probabilities_sha256'])
            self.assertEqual(run['completed_iterations'],5000)
            self.assertGreater(record['quality']['nashconv_lower'],1)


if __name__ == '__main__': unittest.main()
