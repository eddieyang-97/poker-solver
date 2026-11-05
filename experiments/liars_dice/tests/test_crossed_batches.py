from itertools import product, permutations
import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crossed_batches import BatchFixtureTrainer, BatchTrainer
from recall_ablation import HouseFixture, ExactFixtureCFR
from recall_training import RecallTrainer, RecallPolicy
from game import Game
from one_face import evaluate
from run_crossed_batches import admission


def dense(trainer, hands, result):
    """Scatter sample rows into hand-labelled update vectors, retaining duplicates."""
    arrays = []
    for kind in (0,1):
        out = np.zeros_like(trainer.regret)
        for i,p in enumerate(trainer.layout.players):
            rows = out[trainer.layout.offsets[i]:trainer.layout.offsets[i+1]].reshape(len(trainer.game.hands),-1)
            np.add.at(rows,np.asarray(hands[p]),result[kind][i])
        arrays.append(out)
    return arrays


def randomize(*trainers):
    values = np.random.default_rng(490051).normal(size=trainers[0].regret.shape)
    for t in trainers: t.regret[:] = values


class CrossedBatchTests(unittest.TestCase):
    def test_singleton_matches_original_and_full_rule_pair_average(self):
        game=Game()
        old=RecallTrainer(game,490051)
        new=BatchTrainer(game,490051,1)
        randomize(old,new)
        hands=(17,251)
        old.step(hands);new.step(((hands[0],),(hands[1],)))
        np.testing.assert_allclose(new.regret,old.regret,atol=1e-10,rtol=1e-12)
        np.testing.assert_allclose(new.average,old.average,atol=1e-10,rtol=1e-12)
        np.testing.assert_array_equal(new.visits,old.visits)
        cross=BatchTrainer(game,490051,3)
        cross.regret[:]=old.regret
        hands=((17,17,251),(0,251,0))
        result=dense(cross,hands,cross.batch_increments(hands))
        target=[np.zeros_like(old.regret) for _ in range(2)]
        for a in hands[0]:
            for b in hands[1]:
                paired=old.increments((a,b))
                for kind in (0,1):
                    for i,p in enumerate(old.layout.players):
                        old.layout.row(target[kind],i,(a,b)[p])[:] += paired[kind][i]/9
        for a,b in zip(result,target): np.testing.assert_allclose(a,b,atol=1e-10,rtol=1e-12)

    def test_crossed_is_average_of_all_diagonal_permutations(self):
        game=HouseFixture(3)
        for recall in (1,2,None):
            cross=BatchFixtureTrainer(game,recall,490051,3,True)
            diagonal=BatchFixtureTrainer(game,recall,490051,3,False)
            randomize(cross,diagonal)
            hands=((0,25,25),(55,0,55))
            result=dense(cross,hands,cross.batch_increments(hands))
            expected=[np.zeros_like(cross.regret) for _ in range(2)]
            for perm in permutations(range(3)):
                shuffled=(hands[0],tuple(hands[1][i] for i in perm))
                rows=dense(diagonal,shuffled,diagonal.batch_increments(shuffled))
                for k in (0,1): expected[k]+=rows[k]/6
            for a,b in zip(result,expected): np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)
            before=cross.regret.copy()
            cross.step(hands)
            np.testing.assert_allclose(cross.regret,before+result[0],atol=1e-12,rtol=0)
            np.testing.assert_allclose(cross.average,result[1],atol=1e-12,rtol=0)
            np.testing.assert_array_equal(cross.visits[0,[0,25]],[1,2])
            np.testing.assert_array_equal(cross.visits[1,[0,55]],[1,2])

    def test_exhaustive_nonuniform_expectations_and_trace_variance(self):
        game=HouseFixture(3)
        game.hands=tuple(game.hands[i] for i in (0,55))
        game.counts=[game.counts[i] for i in (0,55)]
        game.prior=(.7,.3)
        for recall in (1,2,None):
            diagonal=BatchFixtureTrainer(game,recall,490051,2,False)
            cross=BatchFixtureTrainer(game,recall,490051,2,True)
            exact=ExactFixtureCFR(game,recall)
            randomize(diagonal,cross)
            for i,r in enumerate(exact.regrets):
                r[:]=cross.regret[cross.layout.offsets[i]:cross.layout.offsets[i+1]].reshape(2,-1)
            target=exact.increments(exact.current())
            expected=[np.concatenate([r.ravel() for r in target[k]]) for k in (0,1)]
            means=[[np.zeros_like(cross.regret) for _ in range(2)] for _ in range(2)]
            moments=[0.,0.]
            for samples in product(range(2),repeat=4):
                hands=(samples[:2],samples[2:])
                weight=np.prod([game.prior[h] for h in samples])
                for method,t in enumerate((diagonal,cross)):
                    rows=dense(t,hands,t.batch_increments(hands))
                    for k in (0,1): means[method][k]+=weight*rows[k]
                    moments[method]+=weight*float(rows[0]@rows[0])
            for m in means:
                for a,b in zip(m,expected): np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)
            self.assertLessEqual(moments[1],moments[0]+1e-12)
            self.assertLess(moments[1],moments[0]-1e-6)

    def test_seed_replay_validation_and_unsampled_rows(self):
        game=HouseFixture(2)
        a,b=(BatchFixtureTrainer(game,2,490051,4,True) for _ in range(2))
        for _ in range(10): a.step();b.step()
        np.testing.assert_array_equal(a.regret,b.regret)
        np.testing.assert_array_equal(a.average,b.average)
        self.assertEqual(int(a.visits.sum()),80)
        for i,p in enumerate(a.layout.players):
            rows=a.regret[a.layout.offsets[i]:a.layout.offsets[i+1]].reshape(len(game.hands),-1)
            self.assertTrue((rows[a.visits[p]==0]==0).all())
        before=a.regret.copy()
        for hands in (((True,0,0,0),(0,0,0,0)),((0,),(0,)),((0,0,0,1000),(0,0,0,0))):
            with self.assertRaises(ValueError): a.step(hands)
        np.testing.assert_array_equal(a.regret,before)
        for size in (True,0,33):
            with self.assertRaises(ValueError): BatchFixtureTrainer(game,1,490051,size)
        with self.assertRaises(ValueError): BatchFixtureTrainer(game,1,490051,4,1)

    def test_recorded_cpu_study_policies_and_provenance(self):
        base=Path(__file__).resolve().parents[1]
        report=json.loads((base/'outputs/crossed-batches.json').read_text())
        self.assertEqual(report['status'],'completed')
        for name,h in report['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        profile=json.loads((base/'outputs/batch-profile.json').read_text())
        for name,h in profile['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        expected={(q,r,s,m) for q in (2,3) for r in (1,2,None) for s in (490051,490052,490053)
                  for m in ('scalar','diagonal8','crossed8','conditional')}
        self.assertEqual(len(report['fixture_runs']),72)
        self.assertEqual({(r['quantity'],r['recall'],r['seed'],r['method']) for r in report['fixture_runs']},expected)
        games={q:HouseFixture(q) for q in (2,3)}
        for run in report['fixture_runs']:
            self.assertEqual([c['cpu_budget'] for c in run['checkpoints']],[1,5])
            for c in run['checkpoints']:
                for seat in c['coverage']:
                    self.assertEqual(seat['own_private_samples'],c['iterations']*(8 if run['method'].endswith('8') else 1))
            record=run['checkpoints'][-1]
            path=base/'outputs'/record['policy']['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['policy']['sha256'])
            table=json.loads(path.read_text())
            score=evaluate(games[run['quantity']],lambda p,t,h:table[','.join(map(str,h))][t])
            for k,v in score.items(): self.assertAlmostEqual(v,record['full_history_evaluation'][k],places=11)
        self.assertEqual(len(report['full_runs']),9 if report['fixture_admission']['passed'] else 0)
        if report['full_runs']:
            self.assertEqual({(r['method'],r['seed']) for r in report['full_runs']},
                             {(m,s) for m in ('scalar','diagonal8','crossed8') for s in (490051,490052,490053)})
        game=Game()
        for run in report['full_runs']:
            self.assertEqual([c['cpu_budget'] for c in run['checkpoints']],[15,60])
            for c in run['checkpoints']:
                for seat in c['coverage']:
                    self.assertEqual(seat['own_private_samples'],c['iterations']*(8 if run['method'].endswith('8') else 1))
            artifact=run['checkpoints'][-1]['policy'];path=base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            loaded=RecallPolicy.load(game,path)
            self.assertEqual(hashlib.sha256(loaded.data.astype('<f8').tobytes()).hexdigest(),artifact['probabilities_sha256'])

    def test_fixture_admission_requires_both_cost_quality_conditions(self):
        rows=[]
        crossed=[]
        for q,r,s in product((2,3),(2,None),(490051,490052,490053)):
            for method in ('scalar','diagonal8','crossed8'):
                score={'nashconv':1.}
                rows.append({'quantity':q,'recall':r,'seed':s,'method':method,
                             'checkpoints':[{'full_history_evaluation':score}]})
                if method=='crossed8': crossed.append(score)
        self.assertFalse(admission(rows)['passed'])
        for score in crossed[:8]: score['nashconv']=.7
        self.assertFalse(admission(rows)['passed'])  # Good median, too few wins.
        crossed[8]['nashconv']=.7
        self.assertTrue(admission(rows)['passed'])
        for score in crossed: score['nashconv']=.9
        self.assertFalse(admission(rows)['passed'])  # Every win, insufficient gain.


if __name__=='__main__': unittest.main()
