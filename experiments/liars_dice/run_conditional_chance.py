"""Conditional-chance validation, fixture learning and equal-CPU full-game pilot."""
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import numpy as np

from conditional_chance import ConditionalFixtureTrainer,ConditionalTrainer
from game import Game
from guidance import ProbabilityGuide
from one_face import evaluate
from recall_ablation import HouseFixture,SampledFixtureCFR,ExactFixtureCFR
from recall_training import RecallTrainer,RecallPolicy
from run_fixed_strategy import peak_memory
from run_recall_ablation import policy_table
from run_recall_training import quality,sampled_payoff

BASE = Path(__file__).resolve().parent
SOURCES = ('conditional_chance.py','run_conditional_chance.py','recall_training.py',
           'recall_ablation.py','fixed_strategy.py','game.py','one_face.py','guidance.py',
           'bounded_response.py','run_fixed_strategy.py','run_recall_ablation.py','run_recall_training.py')


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def variance_check(recall):
    game = HouseFixture(3)
    old,new,exact = SampledFixtureCFR(game,recall,490041),ConditionalFixtureTrainer(game,recall,490041),ExactFixtureCFR(game,recall)
    rng = np.random.default_rng(490041)
    for i,r in enumerate(exact.regrets):
        r[:] = rng.normal(size=r.shape)
        for h in range(56):
            old.layout.row(old.regret,i,h)[:] = r[h]
            new.layout.row(new.regret,i,h)[:] = r[h]
    expected = exact.increments(exact.current())
    norm = sum(float((r*r).sum()) for r in expected[0])
    moments = [0.,0.]
    means = [[np.zeros_like(r) for r in exact.regrets] for _ in range(2)]
    cached = {h:new.increments((h,h)) for h in range(56)}
    start,cpu = time.perf_counter(),time.process_time()
    for a in range(56):
        for b in range(56):
            row = old.increments((a,b));w=game.prior[a]*game.prior[b]
            for i,p in enumerate(old.layout.players):
                own=(a,b)[p]
                moments[0] += w*float(row[0][i]@row[0][i])
                moments[1] += w*float(cached[own][0][i]@cached[own][0][i])
                for kind in (0,1): means[kind][i][own] += w*cached[own][kind][i]
    error = max(float(np.max(np.abs(a-b))) for aa,bb in zip(means,expected[:2]) for a,b in zip(aa,bb))
    variance = [max(0.,m-norm) for m in moments]
    if error > 1e-11 or variance[1] > variance[0]+1e-11: raise AssertionError('Conditional expectation/variance mismatch')
    timing = {}
    for label,trainer in (('paired',old),('conditional',new)):
        c=time.process_time()
        for _ in range(100): trainer.increments((25,40))
        timing[label]=(time.process_time()-c)/100
    return {'recall':recall,'fixed_table_seed':490041,'private_pairs':3136,'maximum_mean_error':error,
            'paired_regret_trace_variance':variance[0],'conditional_regret_trace_variance':variance[1],
            'variance_ratio':variance[1]/variance[0], 'cpu_seconds_per_frozen_pass':timing,
            'variance_times_cpu_ratio':variance[1]*timing['conditional']/(variance[0]*timing['paired']),
            'scope':'fixed randomized policies, not learned-policy variance or convergence proof',
            'enumeration_wall_seconds':time.perf_counter()-start,'enumeration_cpu_seconds':time.process_time()-cpu}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'outputs/conditional-chance.json')
    parser.add_argument('--seconds',type=float,default=1500)
    parser.add_argument('--replay-counts',type=Path,help='Reproduce archived full-game iteration counts instead of machine-dependent CPU stops')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0: parser.error('Finite positive guard required')
    replay = json.loads(args.replay_counts.read_text()) if args.replay_counts else None
    report={'status':'running','source_sha256_lf':hashes(),'platform':platform.platform(),
            'python':platform.python_version(),'numpy':np.__version__,'processor':platform.processor(),
            'seeds':[490041,490042,490043],'fixture_checkpoints':[1000,5000],
            'full_cpu_budgets':[15,60],'guard_seconds':args.seconds,
            'execution_mode':'archived iteration counts' if replay else 'measured training CPU budgets',
            'replay_input_sha256':hashlib.sha256(args.replay_counts.read_bytes()).hexdigest() if replay else None,
            'guard_semantics':'between iterations/evaluations, not a hard deadline',
            'variance_checks':[],'fixtures':[],'full_game':[],'certified_equilibrium':False,
            'baseline_ablation_sha256_lf':hashlib.sha256((BASE/'outputs/recall-ablation.json').read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
    start,cpu=time.perf_counter(),time.process_time()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        report['wall_seconds'],report['cpu_seconds']=time.perf_counter()-start,time.process_time()-cpu
        report['peak_process_memory']=peak_memory()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def guard():
        if time.perf_counter()-start > args.seconds: raise TimeoutError('Experiment guard reached')
    save()
    try:
        for recall in (1,2,None):
            report['variance_checks'].append(variance_check(recall));save();guard()
        game=HouseFixture(3)
        for recall in (1,2,None):
            for seed in report['seeds']:
                trainer=ConditionalFixtureTrainer(game,recall,seed)
                row={'recall':recall,'seed':seed,'checkpoints':[]}
                report['fixtures'].append(row)
                wall=cpu_time=0.
                for target in report['fixture_checkpoints']:
                    t,c=time.perf_counter(),time.process_time()
                    while trainer.iterations < target: guard();trainer.step()
                    wall+=time.perf_counter()-t;cpu_time+=time.process_time()-c
                    frozen=trainer.freeze()
                    record={'iterations':target,'training_wall_seconds':wall,'training_cpu_seconds':cpu_time,
                            'full_history_evaluation':evaluate(game,frozen.policy)}
                    if target == 5000:
                        data=json.dumps(policy_table(game,frozen),sort_keys=True,separators=(',',':')).encode()+b'\n'
                        name=f'conditional-fixture-m{recall}-{seed}.json'
                        (args.output.parent/name).write_bytes(data)
                        record['policy']={'file':name,'sha256':hashlib.sha256(data).hexdigest()}
                    row['checkpoints'].append(record)
                    print(json.dumps({'fixture':3,'recall':recall,'seed':seed,'iterations':target,
                                      'NC':record['full_history_evaluation']['nashconv'],'cpu':cpu_time}),flush=True)
                    save();guard()
                del trainer,frozen;gc.collect()
        game=Game();guide=ProbabilityGuide(game)
        # Measured correctness/cost admission, not an asserted strategy-quality gate.
        probe=ConditionalTrainer(game,490040)
        c=time.process_time()
        for _ in range(20):probe.step()
        report['pilot_admission']={'cpu_per_step':(time.process_time()-c)/20,'array_bytes':probe.array_bytes,
                                  'gate':'correctness passed; measured step <=0.25 CPU seconds'}
        del probe;gc.collect();save()
        if report['pilot_admission']['cpu_per_step'] > .25 and not replay:
            report['pilot_admission']['decision']='no-go on measured cost'
        else:
            report['pilot_admission']['decision']='explicit archived-count replay' if replay else 'bounded pilot admitted; quality unknown'
            for method in ('paired','conditional'):
                for seed in report['seeds']:
                    trainer=(RecallTrainer if method=='paired' else ConditionalTrainer)(game,seed)
                    row={'method':method,'seed':seed,'checkpoints':[],'array_bytes':trainer.array_bytes}
                    report['full_game'].append(row)
                    used=0.;wall=0.
                    for budget in report['full_cpu_budgets']:
                        count=None
                        if replay:
                            archived=next(r for r in replay['full_game'] if r['method']==method and r['seed']==seed)
                            count=next(r['iterations'] for r in archived['checkpoints'] if r['cpu_budget']==budget)
                        t,c=time.perf_counter(),time.process_time()
                        while (trainer.iterations < count if count is not None else used+time.process_time()-c < budget):
                            guard();trainer.step()
                        used+=time.process_time()-c;wall+=time.perf_counter()-t
                        frozen=trainer.freeze()
                        record={'cpu_budget':budget,'iterations':trainer.iterations,'training_cpu_seconds':used,
                                'training_wall_seconds':wall,'quality':quality(game,guide,frozen,2000,seed+budget*10000,32),
                                'coverage':[{'seat':p,'unseen_types':int((trainer.visits[p]==0).sum()),
                                    'unseen_prior_mass':float(np.asarray(game.prior)[trainer.visits[p]==0].sum())} for p in (0,1)]}
                        if budget==60:
                            path=args.output.parent/f'conditional-full-{method}-{seed}.npz'
                            record['policy']=frozen.save(path)
                            restored=RecallPolicy.load(game,path)
                            if not np.array_equal(restored.data,frozen.data): raise AssertionError('Snapshot mismatch')
                            del restored
                            heldout=[]
                            for threshold in (.3,.7):
                                opponent=ProbabilityGuide(game,threshold)
                                for seat in (0,1):
                                    first,second=(frozen.policy,opponent.policy) if seat==0 else (opponent.policy,frozen.policy)
                                    heldout.append({'threshold':threshold,'candidate_seat':seat,
                                        **sampled_payoff(game,first,second,seed+3000000+int(threshold*100)+seat,2000)})
                            record['heldout']=heldout
                        row['checkpoints'].append(record)
                        print(json.dumps({'full':method,'seed':seed,'budget':budget,'iterations':trainer.iterations,
                                          'lower':record['quality']['nashconv_lower'],'upper':record['quality']['nashconv_upper']}),flush=True)
                        del frozen;save();guard()
                    del trainer;gc.collect()
        if hashes()!=report['source_sha256_lf']: raise RuntimeError('Source changed during run')
        report['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        report['status'],report['failure']='incomplete',f'{type(error).__name__}: {error}'
        raise
    finally:save()


if __name__=='__main__':main()
