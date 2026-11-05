from pathlib import Path
import hashlib
import json
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conditional_chance import ConditionalFixtureTrainer, ConditionalTrainer
from recall_ablation import HouseFixture, SampledFixtureCFR, ExactFixtureCFR
from game import Game
from one_face import evaluate
from recall_training import RecallPolicy


def small_fixture():
    game = HouseFixture(3)
    indices = (0,25,55)
    game.hands = tuple(game.hands[i] for i in indices)
    game.counts = [game.counts[i] for i in indices]
    game.prior = (.6,.3,.1)
    return game


class ConditionalChanceTests(unittest.TestCase):
    def test_conditional_means_variance_and_exact_expectation(self):
        game = small_fixture()
        for recall in (1,2,None):
            old = SampledFixtureCFR(game,recall,490041)
            new = ConditionalFixtureTrainer(game,recall,490041)
            exact = ExactFixtureCFR(game,recall)
            rng = np.random.default_rng(490041)
            for i,r in enumerate(exact.regrets):
                r[:] = rng.normal(size=r.shape)
                for h in range(3):
                    old.layout.row(old.regret,i,h)[:] = r[h]
                    new.layout.row(new.regret,i,h)[:] = r[h]
            expected = exact.increments(exact.current())
            means = [[np.zeros_like(r) for r in exact.regrets] for _ in range(2)]
            second_old=second_new=0.
            conditional = {h:new.increments((h,h)) for h in range(3)}
            paired_cache = {(a,b):old.increments((a,b)) for a in range(3) for b in range(3)}
            for a in range(3):
                for b in range(3):
                    paired = paired_cache[a,b]
                    result = new.increments((a,b))
                    for i,p in enumerate(new.layout.players):
                        own = (a,b)[p]
                        # E[paired update | own] equals the conditional update.
                        for kind in (0,1):
                            target = sum(game.prior[t]*paired_cache[(own,t) if p == 0 else (t,own)][kind][i]
                                         for t in range(3))
                            np.testing.assert_allclose(result[kind][i],target,atol=2e-12,rtol=0)
                            np.testing.assert_allclose(result[kind][i],conditional[own][kind][i],atol=2e-12,rtol=0)
                            means[kind][i][own] += game.prior[a]*game.prior[b]*result[kind][i]
                        second_old += game.prior[a]*game.prior[b]*float(paired[0][i]@paired[0][i])
                        second_new += game.prior[a]*game.prior[b]*float(result[0][i]@result[0][i])
            for kind in (0,1):
                for actual,target in zip(means[kind],expected[kind]):
                    np.testing.assert_allclose(actual,target,atol=2e-12,rtol=0)
            self.assertLessEqual(second_new,second_old+1e-12)
            self.assertLess(second_new,second_old-1e-6)

    def test_seeded_updates_and_full_rule_terminal_vectors(self):
        game = Game()
        first,second = ConditionalTrainer(game,490041),ConditionalTrainer(game,490041)
        for _ in range(2): first.step();second.step()
        np.testing.assert_array_equal(first.regret,second.regret)
        np.testing.assert_array_equal(first.average,second.average)
        hands=(0,251)
        fast = first.increments(hands)
        # Same conditional calculation, but force scalar game.payoff terminals.
        class Scalar:
            def __getattr__(self,name):
                if name == 'counts': raise AttributeError(name)
                return getattr(game,name)
        first.game = Scalar()
        slow = first.increments(hands)
        for kind in (0,1):
            for a,b in zip(fast[kind],slow[kind]):
                np.testing.assert_allclose(a,b,atol=1e-8,rtol=1e-12)
        with self.assertRaises(ValueError): second.increments((True,0))

    def test_recorded_policies_and_source_provenance(self):
        base=Path(__file__).resolve().parents[1]
        report=json.loads((base/'outputs/conditional-chance.json').read_text())
        self.assertEqual(report['status'],'completed')
        for name,h in report['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        self.assertEqual(len(report['variance_checks']),3)
        for r in report['variance_checks']:
            self.assertLess(r['maximum_mean_error'],1e-11)
            self.assertLessEqual(r['conditional_regret_trace_variance'],r['paired_regret_trace_variance'])
        self.assertEqual(len(report['fixtures']),9)
        game=HouseFixture(3)
        for run in report['fixtures']:
            self.assertEqual([r['iterations'] for r in run['checkpoints']],[1000,5000])
            record=run['checkpoints'][-1]
            path=base/'outputs'/record['policy']['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['policy']['sha256'])
            table=json.loads(path.read_text())
            score=evaluate(game,lambda p,t,h:table[','.join(map(str,h))][t])
            for k,v in score.items(): self.assertAlmostEqual(v,record['full_history_evaluation'][k],places=11)
        self.assertEqual(len(report['full_game']),6)
        self.assertEqual({(r['method'],r['seed']) for r in report['full_game']},
                         {(m,s) for m in ('paired','conditional') for s in (490041,490042,490043)})
        game=Game()
        for run in report['full_game']:
            self.assertEqual([r['cpu_budget'] for r in run['checkpoints']],[15,60])
            artifact=run['checkpoints'][-1]['policy'];path=base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            loaded=RecallPolicy.load(game,path)
            self.assertEqual(hashlib.sha256(loaded.data.astype('<f8').tobytes()).hexdigest(),artifact['probabilities_sha256'])


if __name__ == '__main__': unittest.main()
