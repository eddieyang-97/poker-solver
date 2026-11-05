"""Equal-CPU fixture controls and conditionally admitted full-rule batch pilot."""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

import numpy as np

from conditional_chance import ConditionalFixtureTrainer
from crossed_batches import BatchFixtureTrainer, BatchTrainer
from game import Game
from guidance import ProbabilityGuide
from one_face import evaluate
from recall_ablation import HouseFixture, SampledFixtureCFR
from recall_training import RecallTrainer, RecallPolicy
from run_fixed_strategy import peak_memory
from run_recall_ablation import policy_table
from run_recall_training import quality, sampled_payoff

BASE=Path(__file__).resolve().parent
SOURCES=('crossed_batches.py','run_crossed_batches.py','conditional_chance.py',
         'recall_training.py','recall_ablation.py','fixed_strategy.py','game.py',
         'one_face.py','guidance.py','bounded_response.py','run_fixed_strategy.py',
         'run_recall_ablation.py','run_recall_training.py')
METHODS=('scalar','diagonal8','crossed8','conditional')
SEEDS=(490051,490052,490053)


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def admission(fixtures):
    """Predeclared engineering heuristic, not a statistical/equilibrium test."""
    ratios={m:[] for m in ('diagonal8','crossed8')}
    reuse=[]
    for q in (2,3):
        for recall in (2,None):
            for seed in SEEDS:
                scores={r['method']:r['checkpoints'][-1]['full_history_evaluation']['nashconv']
                        for r in fixtures if r['quantity']==q and r['recall']==recall and r['seed']==seed}
                for m in ratios: ratios[m].append(scores[m]/max(scores['scalar'],1e-15))
                reuse.append(scores['crossed8']/max(scores['diagonal8'],1e-15))
    comparisons={m:{'ratios_to_scalar':v,'median_ratio':float(np.median(v)),
                    'wins':sum(x<1 for x in v)} for m,v in ratios.items()}
    passed=any(r['median_ratio'] <= .8 and r['wins'] >= 9 for r in comparisons.values())
    return {'contract':'At final fixture CPU budget, at least one batch method has median NC/scalar <=0.8 and wins >=9/12 on recall 2/full across both fixtures and all seeds',
            'statistical_significance_claim':False,'comparisons':comparisons,
            'crossed_over_diagonal_ratios':reuse,'crossed_over_diagonal_median':float(np.median(reuse)),
            'passed':passed}


def coverage(trainer):
    return [{'seat':p,'own_private_samples':int(trainer.visits[p].sum()),
             'unseen_types':int((trainer.visits[p]==0).sum()),
             'unseen_prior_mass':float(np.asarray(trainer.game.prior)[trainer.visits[p]==0].sum()),
             'minimum_samples':int(trainer.visits[p].min())} for p in (0,1)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'outputs/crossed-batches.json')
    parser.add_argument('--seconds',type=float,default=1800)
    parser.add_argument('--replay-counts',type=Path,help='Replay archived fixture/full-game iteration counts, not CPU stops')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0: parser.error('Positive finite guard required')
    replay=json.loads(args.replay_counts.read_text()) if args.replay_counts else None
    report={'status':'running','source_sha256_lf':hashes(),'platform':platform.platform(),
            'python':platform.python_version(),'numpy':np.__version__,'processor':platform.processor(),
            'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS'),'seeds':SEEDS,'batch_size':8,
            'fixture_cpu_budgets':[1,5],'full_cpu_budgets':[15,60],
            'execution_mode':'archived iteration counts' if replay else 'measured training CPU budgets',
            'replay_input_sha256':hashlib.sha256(args.replay_counts.read_bytes()).hexdigest() if replay else None,
            'guard_seconds':args.seconds,'guard_semantics':'between work units; not a hard deadline',
            'fixture_runs':[],'full_runs':[],'certified_equilibrium':False}
    start,cpu=time.perf_counter(),time.process_time()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def guard():
        if time.perf_counter()-start > args.seconds: raise TimeoutError('Experiment guard reached')
    def save():
        report['wall_seconds'],report['cpu_seconds']=time.perf_counter()-start,time.process_time()-cpu
        report['peak_process_memory']=peak_memory()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def train(trainer,row,budget,group):
        count=None
        if replay:
            old=next(r for r in replay[group] if all(r.get(k)==row.get(k) for k in ('quantity','recall','seed','method')))
            count=next(c['iterations'] for c in old['checkpoints'] if c['cpu_budget']==budget)
        used=row['checkpoints'][-1]['training_cpu_seconds'] if row['checkpoints'] else 0.
        wall=row['checkpoints'][-1]['training_wall_seconds'] if row['checkpoints'] else 0.
        t,c=time.perf_counter(),time.process_time()
        while (trainer.iterations<count if count is not None else used+time.process_time()-c<budget):
            guard();trainer.step()
        return {'cpu_budget':budget,'iterations':trainer.iterations,
                'training_cpu_seconds':used+time.process_time()-c,'training_wall_seconds':wall+time.perf_counter()-t,
                'coverage':coverage(trainer),'maximum_summed_reach':trainer.maximum_reach}
    save()
    try:
        for q in (2,3):
            game=HouseFixture(q)
            for recall in (1,2,None):
                for s,seed in enumerate(SEEDS):
                    order=METHODS[s:]+METHODS[:s]
                    for method in order:
                        trainer=(SampledFixtureCFR(game,recall,seed) if method=='scalar' else
                                 ConditionalFixtureTrainer(game,recall,seed) if method=='conditional' else
                                 BatchFixtureTrainer(game,recall,seed,8,method=='crossed8'))
                        row={'quantity':q,'recall':recall,'seed':seed,'method':method,
                             'array_bytes':trainer.array_bytes,'public_nodes':len(trainer.layout.graph.keys),'checkpoints':[]}
                        report['fixture_runs'].append(row)
                        for budget in report['fixture_cpu_budgets']:
                            record=train(trainer,row,budget,'fixture_runs')
                            frozen=trainer.freeze()
                            record['full_history_evaluation']=evaluate(game,frozen.policy)
                            if budget==5:
                                name=f'batch-fixture-q{q}-m{recall}-{method}-{seed}.json'
                                data=json.dumps(policy_table(game,frozen),sort_keys=True,separators=(',',':')).encode()+b'\n'
                                (args.output.parent/name).write_bytes(data)
                                record['policy']={'file':name,'sha256':hashlib.sha256(data).hexdigest()}
                            row['checkpoints'].append(record)
                            print(json.dumps({'fixture':q,'recall':recall,'method':method,'seed':seed,'budget':budget,
                                              'iterations':trainer.iterations,'NC':record['full_history_evaluation']['nashconv']}),flush=True)
                            del frozen;save();guard()
                        del trainer;gc.collect()
        report['fixture_admission']=admission(report['fixture_runs']);save();guard()
        # Explicit archived-count replay follows the archived admission decision;
        # it does not assert the new machine passes the equal-CPU heuristic.
        admitted=replay['fixture_admission']['passed'] if replay else report['fixture_admission']['passed']
        report['full_pilot_decision']='archived admission replay' if replay else 'fixture admission passed' if admitted else 'no-go on fixture CPU/quality'
        if admitted:
            game=Game();guide=ProbabilityGuide(game)
            methods=('scalar','diagonal8','crossed8')
            for s,seed in enumerate(SEEDS):
                for method in methods[s:]+methods[:s]:
                    trainer=RecallTrainer(game,seed) if method=='scalar' else BatchTrainer(game,seed,8,method=='crossed8')
                    row={'seed':seed,'method':method,'array_bytes':trainer.array_bytes,'checkpoints':[]}
                    report['full_runs'].append(row)
                    for budget in report['full_cpu_budgets']:
                        record=train(trainer,row,budget,'full_runs')
                        frozen=trainer.freeze()
                        record['quality']=quality(game,guide,frozen,2000,seed+budget*10000,32)
                        if budget==60:
                            path=args.output.parent/f'batch-full-{method}-{seed}.npz'
                            record['policy']=frozen.save(path)
                            restored=RecallPolicy.load(game,path)
                            if not np.array_equal(restored.data,frozen.data): raise AssertionError('Snapshot roundtrip mismatch')
                            del restored
                            record['heldout']=[]
                            for threshold in (.3,.7):
                                opponent=ProbabilityGuide(game,threshold)
                                for seat in (0,1):
                                    first,second=(frozen.policy,opponent.policy) if seat==0 else (opponent.policy,frozen.policy)
                                    record['heldout'].append({'threshold':threshold,'candidate_seat':seat,
                                        **sampled_payoff(game,first,second,seed+3000000+int(threshold*100)+seat,2000)})
                        row['checkpoints'].append(record)
                        print(json.dumps({'full':method,'seed':seed,'budget':budget,'iterations':trainer.iterations,
                                          'lower':record['quality']['nashconv_lower'],'upper':record['quality']['nashconv_upper']}),flush=True)
                        del frozen;save();guard()
                    del trainer;gc.collect()
        if hashes()!=report['source_sha256_lf']: raise RuntimeError('Source changed during study')
        report['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        report['status'],report['failure']='incomplete',f'{type(error).__name__}: {error}'
        raise
    finally:save()


if __name__=='__main__':main()
