from itertools import product
import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from axis_batches import AxisFixtureTrainer, AxisTrainer, pair_average
from crossed_batches import BatchFixtureTrainer, BatchTrainer
from game import Game
from recall_ablation import HouseFixture, ExactFixtureCFR
from recall_training import RecallPolicy
from one_face import evaluate
from run_axis_batches import admission


class AxisBatchTests(unittest.TestCase):
    def test_axis_aggregation_matches_explicit_pair_sums(self):
        rng=np.random.default_rng(490061)
        for k,crossed,p in product((1,2,3,8,32),(False,True),(0,1)):
            d=k*k if crossed else k
            raw=rng.normal(size=(7,d))
            expected=np.zeros((k,7))
            pairs=product(range(k),repeat=2) if crossed else ((i,i) for i in range(k))
            for j,pair in enumerate(pairs): expected[pair[p]]+=raw[:,j]/d
            np.testing.assert_allclose(pair_average(raw,p,k,crossed),expected,atol=2e-14,rtol=1e-13)

    def test_fixture_passes_match_reference_with_duplicate_hands(self):
        for q,recall,k,crossed in product((2,3),(1,2,None),(1,3,8),(False,True)):
            game=HouseFixture(q)
            ref=BatchFixtureTrainer(game,recall,490061,k,crossed)
            new=AxisFixtureTrainer(game,recall,490061,k,crossed)
            values=np.random.default_rng(490061).normal(size=ref.regret.shape)
            ref.regret[:]=values;new.regret[:]=values
            hands=(tuple((0,25,25,55)[i%4] for i in range(k)),tuple((55,55,0,25)[i%4] for i in range(k)))
            first,second=ref.batch_increments(hands),new.batch_increments(hands)
            for kind in (0,1):
                for a,b in zip(first[kind],second[kind]): np.testing.assert_allclose(a,b,atol=2e-12,rtol=2e-12)
            self.assertEqual(first[2:],second[2:])
            new.step(hands)
            for p in (0,1):
                np.testing.assert_array_equal(new.visits[p],np.bincount(hands[p],minlength=56))

    def test_nonuniform_exact_expected_updates(self):
        game=HouseFixture(3)
        game.hands=tuple(game.hands[i] for i in (0,55))
        game.counts=[game.counts[i] for i in (0,55)]
        game.prior=(.7,.3)
        for recall in (1,2,None):
            new=AxisFixtureTrainer(game,recall,490061,2,True)
            exact=ExactFixtureCFR(game,recall)
            new.regret[:]=np.random.default_rng(490061).normal(size=new.regret.shape)
            for i,r in enumerate(exact.regrets):
                r[:]=new.regret[new.layout.offsets[i]:new.layout.offsets[i+1]].reshape(2,-1)
            target=exact.increments(exact.current())
            means=[np.zeros_like(new.regret) for _ in range(2)]
            for samples in product(range(2),repeat=4):
                hands=(samples[:2],samples[2:]);weight=np.prod([game.prior[h] for h in samples])
                result=new.batch_increments(hands)
                for kind in (0,1):
                    for i,p in enumerate(new.layout.players):
                        rows=means[kind][new.layout.offsets[i]:new.layout.offsets[i+1]].reshape(2,-1)
                        np.add.at(rows,np.asarray(hands[p]),weight*result[kind][i])
            for kind in (0,1):
                expected=np.concatenate([r.ravel() for r in target[kind]])
                np.testing.assert_allclose(means[kind],expected,atol=2e-12,rtol=0)

    def test_full_rule_frozen_pass_and_invalid_input_before_mutation(self):
        game=Game()
        ref=BatchTrainer(game,490061,8,True)
        new=AxisTrainer(game,490061,8,True)
        ref.regret[:]=np.random.default_rng(490061).normal(size=ref.regret.shape)
        new.regret[:]=ref.regret
        hands=((0,17,17,55,100,100,251,251),(251,251,100,55,17,17,0,0))
        first,second=ref.batch_increments(hands),new.batch_increments(hands)
        for kind in (0,1):
            for a,b in zip(first[kind],second[kind]): np.testing.assert_allclose(a,b,atol=1e-8,rtol=2e-12)
        before=new.regret.copy()
        with self.assertRaises(ValueError): new.step(((True,)*8,(0,)*8))
        np.testing.assert_array_equal(new.regret,before)
        self.assertEqual(new.iterations,0)

    def test_admission_fails_closed_on_cost_sensitivity_and_quality(self):
        fixtures=[]
        for q,r,s in product((2,3),(2,None),(490061,490062,490063)):
            for method in ('reference','axis'):
                fixtures.append({'quantity':q,'recall':r,'seed':s,'method':method,
                                 'checkpoints':[{'full_history_evaluation':{'nashconv':.1}}]})
        traces=[{'checkpoints':[{'reference':{'ev_p0':0.,'nashconv':.1},'axis':{'ev_p0':0.,'nashconv':.1}}]}]
        probe={'median_cpu_ratio':.85}
        self.assertTrue(admission(fixtures,traces,probe)['passed'])
        probe['median_cpu_ratio']=.851
        self.assertFalse(admission(fixtures,traces,probe)['passed'])
        probe['median_cpu_ratio']=.85
        traces[0]['checkpoints'][0]['axis']['ev_p0']=.011
        self.assertFalse(admission(fixtures,traces,probe)['passed'])
        traces[0]['checkpoints'][0]['axis']['ev_p0']=0.
        fixtures[-1]['checkpoints'][0]['full_history_evaluation']['nashconv']=.112
        self.assertFalse(admission(fixtures,traces,probe)['passed'])
        for row in fixtures:
            if row['method']=='axis': row['checkpoints'][0]['full_history_evaluation']['nashconv']=.101
        self.assertFalse(admission(fixtures,traces,probe)['passed'])

    def test_recorded_study_policies_and_source_fingerprints(self):
        base=Path(__file__).resolve().parents[1]
        report=json.loads((base/'outputs/axis-batches.json').read_text())
        self.assertEqual(report['status'],'completed')
        for name,h in report['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        games={q:HouseFixture(q) for q in (2,3)}
        def check_table(game,artifact,expected):
            path=base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            table=json.loads(path.read_text())
            score=evaluate(game,lambda p,t,h:table[','.join(map(str,h))][t])
            for k,v in score.items(): self.assertAlmostEqual(v,expected[k],places=11)
        self.assertEqual(len(report['fixed_count_runs']),6)
        self.assertEqual({(r['quantity'],r['recall']) for r in report['fixed_count_runs']},
                         set(product((2,3),(1,2,None))))
        for run in report['fixed_count_runs']:
            self.assertEqual([c['iterations'] for c in run['checkpoints']],[100,500])
            record=run['checkpoints'][-1]
            for method in ('reference','axis'):
                check_table(games[run['quantity']],record[method]['policy'],record[method])
        self.assertEqual(len(report['fixture_runs']),36)
        self.assertEqual({(r['quantity'],r['recall'],r['seed'],r['method']) for r in report['fixture_runs']},
                         set(product((2,3),(1,2,None),(490061,490062,490063),('reference','axis'))))
        for run in report['fixture_runs']:
            self.assertEqual([c['cpu_budget'] for c in run['checkpoints']],[1,5])
            for c in run['checkpoints']:
                for seat in c['coverage']: self.assertEqual(seat['own_private_samples'],8*c['iterations'])
            record=run['checkpoints'][-1]
            check_table(games[run['quantity']],record['policy'],record['full_history_evaluation'])
        self.assertEqual(len(report['full_runs']),6 if report['admission']['passed'] else 0)
        if report['full_runs']:
            self.assertEqual({(r['method'],r['seed']) for r in report['full_runs']},
                             set(product(('reference','axis'),(490061,490062,490063))))
        game=Game()
        for run in report['full_runs']:
            self.assertEqual([c['cpu_budget'] for c in run['checkpoints']],[15,60])
            for c in run['checkpoints']:
                for seat in c['coverage']: self.assertEqual(seat['own_private_samples'],8*c['iterations'])
            artifact=run['checkpoints'][-1]['policy'];path=base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            loaded=RecallPolicy.load(game,path)
            self.assertEqual(hashlib.sha256(loaded.data.astype('<f8').tobytes()).hexdigest(),artifact['probabilities_sha256'])


if __name__=='__main__': unittest.main()
