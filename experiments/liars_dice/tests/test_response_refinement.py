from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bounded_response import ResponseSearch
from game import Game, Rules
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from recall_ablation import HouseFixture, SampledFixtureCFR
from recall_training import RecallTrainer, RecallPolicy
from response_refinement import CachedRecallModel, ResponsePlan, ReplayLimit, exact_response_value, raw_columns
from ordered_response import OrderedResponseSearch, response_envelope


def fixture(maximum=7):
    game=OneFace(maximum)
    # OneFace's numeric bids supply the monotonic rank required by graph layout.
    game.rank=lambda action:action
    trainer=RecallTrainer(game,490071)
    trainer.average[:]=np.random.default_rng(490071).random(trainer.average.shape)
    target=trainer.freeze()
    digest=hashlib.sha256(target.data.astype('<f8').tobytes()).hexdigest()
    return game,ProbabilityGuide(game),target,digest


class ResponseRefinementTests(unittest.TestCase):
    def test_cache_matches_scalar_rows_and_reference_search(self):
        game,guide,target,_=fixture()
        cache=CachedRecallModel(target)
        for history in ((),(3,),(4,),(3,4),(3,5),(4,5),(3,4,5)):
            p=len(history)%2
            sparse=cache.actions(p,history)
            for j,a in enumerate(game.actions(history)):
                expected=np.array([target.policy(p,h,history)[j] for h in range(len(game.hands))])
                np.testing.assert_array_equal(sparse.get(a,np.zeros(len(expected))),expected)
            with self.assertRaises(TypeError): sparse[-999]=np.ones(len(game.hands))
        self.assertIs(cache.actions(0,(3,5)),cache.actions(0,(4,5)))
        with self.assertRaises(ValueError): cache.actions(1,())
        with self.assertRaises(ValueError): CachedRecallModel(guide)
        with self.assertRaises(ValueError): CachedRecallModel(SampledFixtureCFR(HouseFixture(3),2,490071).freeze())
        for seat in (0,1):
            for budget in (1,8,10000):
                first=ResponseSearch(game,guide,SimpleNamespace(target=target,actions=target.actions),seat,3,budget)
                second=ResponseSearch(game,guide,cache,seat,3,budget)
                a,b=first.solve(),second.solve()
                for key in ('lower','upper'): self.assertAlmostEqual(a[key],b[key],places=13)
                self.assertEqual(set(first.decisions),set(second.decisions))
                for h in first.decisions: np.testing.assert_array_equal(first.decisions[h],second.decisions[h])
        self.assertTrue(any(len(h)>1 for h in second.decisions))

    def test_plan_roundtrip_information_and_rejection(self):
        game,guide,target,digest=fixture()
        search=ResponseSearch(game,guide,CachedRecallModel(target),0,3,8);search.solve()
        plan=ResponsePlan.from_search(search,digest)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plan.json';artifact=plan.save(path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            restored=ResponsePlan.load(game,path,digest)
            for h,row in plan.decisions.items(): np.testing.assert_array_equal(restored.choices(0,h),row)
            with self.assertRaises(ValueError): ResponsePlan.load(game,path,'0'*64)
            with self.assertRaises(ValueError): ResponsePlan.load(OneFace(6),path,digest)
            original=json.loads(path.read_text())
            malformed=json.loads(json.dumps(original));malformed['decisions'].append(malformed['decisions'][0])
            path.write_text(json.dumps(malformed))
            with self.assertRaises(ValueError): ResponsePlan.load(game,path,digest)
            malformed=json.loads(json.dumps(original));malformed['decisions'][0]['choices'][0]=-1
            path.write_text(json.dumps(malformed))
            with self.assertRaises(ValueError): ResponsePlan.load(game,path,digest)
        with self.assertRaises(ValueError): plan.policy(0,True,())
        with self.assertRaises(ValueError): plan.choices(1,(3,))
        with self.assertRaises(ValueError): ResponsePlan(game,True,{},digest)
        # Completion is public/own-hand only, including off-target histories.
        for h in ((3,5),(4,6)):
            chosen=plan.choices(0,h)
            self.assertTrue(np.isin(chosen,game.actions(h)).all())

    def test_independent_exact_replay_matches_tree_and_search(self):
        for maximum in (3,5,7):
            game,guide,target,digest=fixture(maximum)
            model=CachedRecallModel(target)
            exact=evaluate(game,target.policy)
            for seat in (0,1):
                incumbent=None
                for depth,budget in ((1,1),(2,8),(4,10000)):
                    search=ResponseSearch(game,guide,model,seat,depth,budget,incumbent=incumbent)
                    bound=search.solve();plan=ResponsePlan.from_search(search,digest)
                    replay=exact_response_value(game,target,plan)
                    profile=lambda p,t,h:(plan.policy if p==seat else target.policy)(p,t,h)
                    independent=evaluate(game,profile)['ev_p0']*(1 if seat==0 else -1)
                    self.assertAlmostEqual(replay['value'],independent,places=12)
                    self.assertAlmostEqual(replay['value'],bound['lower'],places=12)
                    self.assertLessEqual(bound['lower'],exact[f'br{seat}']+1e-12)
                    self.assertGreaterEqual(bound['upper'],exact[f'br{seat}']-1e-12)
                    incumbent=search
                self.assertAlmostEqual(bound['lower'],exact[f'br{seat}'],places=12)
                self.assertAlmostEqual(bound['upper'],exact[f'br{seat}'],places=12)

    def test_raw_scoring_and_exact_replay_limits(self):
        for rules in (Rules(),Rules(all_ones_wild_seven=False),Rules(zhai_mixed_bonus=True),
                      Rules(face_one=False,all_ones_wild_seven=False,zhai_mixed_bonus=True,quantity_floor=3)):
            game=Game(rules);columns,_=raw_columns(game)
            np.testing.assert_array_equal(np.array([columns[a] for a in range(len(game.bids))]).T,game.counts)
        game,guide,target,digest=fixture()
        search=ResponseSearch(game,guide,CachedRecallModel(target),0,1,1);search.solve()
        plan=ResponsePlan.from_search(search,digest)
        with self.assertRaises(ReplayLimit): exact_response_value(game,target,plan,node_limit=1)
        for kwargs in ({'node_limit':True},{'seconds':float('nan')},{'seconds':0}):
            with self.assertRaises(ValueError): exact_response_value(game,target,plan,**kwargs)
        other=ResponsePlan(game,0,{},'0'*64)
        with self.assertRaises(ValueError): exact_response_value(game,target,other)

    def test_ordered_refinement_preserves_bounds_and_realization(self):
        game,guide,target,digest=fixture()
        model=CachedRecallModel(target);optimal=evaluate(game,target.policy)
        for seat in (0,1):
            base=ResponseSearch(game,guide,model,seat,1,8);baseline=base.solve()
            for budget in (1,4,10000):
                search=OrderedResponseSearch(game,guide,model,seat,4,budget,incumbent=base)
                bound=search.solve();plan=ResponsePlan.from_search(search,digest)
                replay=exact_response_value(game,target,plan)
                self.assertGreaterEqual(bound['lower'],baseline['lower']-1e-12)
                self.assertLessEqual(bound['upper'],baseline['upper']+1e-12)
                self.assertLessEqual(bound['lower'],optimal[f'br{seat}']+1e-12)
                self.assertGreaterEqual(bound['upper'],optimal[f'br{seat}']-1e-12)
                self.assertAlmostEqual(replay['value'],bound['lower'],places=12)
                self.assertLessEqual(bound['stats']['expanded_own_nodes'],budget)
            self.assertAlmostEqual(bound['lower'],optimal[f'br{seat}'],places=12)
            self.assertAlmostEqual(bound['upper'],optimal[f'br{seat}'],places=12)

    def test_same_target_envelope_and_incompatible_records(self):
        def stage(label,values,digest='a'*64):
            return {'label':label,'target_file_sha256':digest,'target_probabilities_sha256':'c'*64,'game':{'kind':'test'},
                    'seats':[{'seat':s,'lower':lo,'upper':hi,'plan':{'file':f'{label}-{s}'}} for s,(lo,hi) in enumerate(values)]}
        stages=[stage('first',((.2,.8),(.3,.9))),stage('second',((.4,.85),(.25,.7)))]
        result=response_envelope(stages,'a'*64)
        self.assertAlmostEqual(result['nashconv_lower'],.7)
        self.assertAlmostEqual(result['nashconv_upper'],1.5)
        self.assertEqual(result['seats'][0]['lower_plan']['file'],'second-0')
        self.assertEqual(result['seats'][1]['lower_plan']['file'],'first-1')
        with self.assertRaises(ValueError): response_envelope(stages,'b'*64)
        with self.assertRaises(ValueError): response_envelope([stage('bad',((.8,.2),(.3,.9)))],'a'*64)
        mixed=[stage('first',((.2,.8),(.3,.9))),stage('second',((.4,.85),(.25,.7)))]
        mixed[1]['game']={'kind':'other'}
        with self.assertRaises(ValueError): response_envelope(mixed,'a'*64)
        with self.assertRaises(ArithmeticError): response_envelope([stage('impossible',((-.8,-.7),(-.9,-.8)))],'a'*64)

    def test_recorded_targets_plans_and_provenance(self):
        base=Path(__file__).resolve().parents[1]
        report=json.loads((base/'outputs/response-refinement.json').read_text())
        calibration=json.loads((base/'outputs/response-calibration.json').read_text())
        self.assertEqual(report['status'],'completed')
        self.assertEqual(calibration['status'],'completed')
        for receipt in (report,calibration):
            for name,h in receipt['source_sha256_lf'].items():
                self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        self.assertEqual(hashlib.sha256((base/'outputs/axis-batches.json').read_bytes().replace(b'\r\n',b'\n')).hexdigest(),report['target_receipt_sha256_lf'])
        self.assertEqual(hashlib.sha256((base/'outputs/response-calibration.json').read_bytes().replace(b'\r\n',b'\n')).hexdigest(),report['calibration_receipt_sha256_lf'])
        self.assertEqual(len(report['targets']),6)
        self.assertEqual({(r['method'],r['seed']) for r in report['targets']},
                         {(m,s) for m in ('axis','reference') for s in (490061,490062,490063)})
        for row in report['targets']:
            game=Game();artifact=row['target'];path=base/'outputs'/artifact['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
            target=RecallPolicy.load(game,path)
            self.assertEqual(hashlib.sha256(target.data.astype('<f8').tobytes()).hexdigest(),artifact['probabilities_sha256'])
            self.assertEqual([s['label'] for s in row['stages']],['base32','breadth128','legacy128','priority128'])
            for stage in row['stages']:
                self.assertEqual([s['seat'] for s in stage['seats']],[0,1])
                for record in stage['seats']:
                    self.assertLessEqual(record['stats']['expanded_own_nodes'],stage['max_nodes_per_seat'])
                    p=base/'outputs'/record['plan']['file']
                    self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),record['plan']['sha256'])
                    restored=ResponsePlan.load(game,p,artifact['probabilities_sha256'])
                    self.assertEqual(restored.seat,record['seat'])
                    if record['exact_replay']['status']=='completed':
                        self.assertAlmostEqual(record['exact_replay']['value'],record['lower'],places=10)
                    else: self.assertEqual(record['exact_replay']['status'],'budget_exceeded')
                    if row['method']=='axis' and row['seed']==490061 and stage['label']=='base32' and record['seat']==0:
                        replay=exact_response_value(game,target,restored,seconds=20)
                        self.assertAlmostEqual(replay['value'],record['lower'],places=10)
            expected=response_envelope(row['stages'],artifact['sha256'])
            self.assertEqual(row['envelope'],expected)
        for record in calibration['runs']:
            if 'plan' in record:
                p=base/'outputs'/record['plan']['file']
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),record['plan']['sha256'])


if __name__=='__main__': unittest.main()
