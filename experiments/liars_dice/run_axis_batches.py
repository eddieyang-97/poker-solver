"""Frozen-pass cost, trajectory sensitivity, and equal-CPU axis-reduction study."""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import time

import numpy as np

from axis_batches import AxisFixtureTrainer, AxisTrainer
from crossed_batches import BatchFixtureTrainer, BatchTrainer
from game import Game
from guidance import ProbabilityGuide
from one_face import evaluate
from recall_ablation import HouseFixture
from recall_training import RecallPolicy
from run_crossed_batches import coverage
from run_fixed_strategy import peak_memory
from run_recall_ablation import policy_table
from run_recall_training import quality, sampled_payoff

BASE=Path(__file__).resolve().parent
SOURCES=('axis_batches.py','run_axis_batches.py','crossed_batches.py','run_crossed_batches.py',
         'recall_training.py','recall_ablation.py','fixed_strategy.py','game.py','one_face.py',
         'guidance.py','bounded_response.py','run_fixed_strategy.py','run_recall_ablation.py','run_recall_training.py')
SEEDS=(490061,490062,490063)


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def frozen_probe(guard):
    game=Game()
    ref,new=BatchTrainer(game,490061,8,True),AxisTrainer(game,490061,8,True)
    np.random.default_rng(490061).standard_normal(out=ref.regret)
    new.regret[:]=ref.regret
    initial=hashlib.sha256(ref.regret.tobytes()).hexdigest()
    rng=random.Random(490061)
    blocks=[]
    for _ in range(32):
        h=rng.choices(range(252),weights=game.prior,k=16)
        blocks.append((h[:8],h[8:]))
    error=0.
    for hands in blocks[:4]:
        first,second=ref.batch_increments(hands),new.batch_increments(hands)
        for kind in (0,1):
            for a,b in zip(first[kind],second[kind]):
                error=max(error,float(np.max(np.abs(a-b)))/max(1.,float(np.max(np.abs(a)))))
        guard()
    if error>2e-12: raise AssertionError('Frozen full-rule increments differ')
    measured=[]
    for name,t in (('reference',ref),('axis',new),('axis',new),('reference',ref)):
        wall,cpu=time.perf_counter(),time.process_time()
        for hands in blocks: guard();t.batch_increments(hands)
        measured.append({'method':name,'passes':32,'cpu_seconds':time.process_time()-cpu,
                         'wall_seconds':time.perf_counter()-wall})
    ratios=[measured[1]['cpu_seconds']/measured[0]['cpu_seconds'],
            measured[2]['cpu_seconds']/measured[3]['cpu_seconds']]
    for t in (ref,new):
        if hashlib.sha256(t.regret.tobytes()).hexdigest()!=initial: raise AssertionError('Probe mutated policies')
    return {'seed':490061,'sample_blocks':32,'randomized_regret_sha256':initial,
            'maximum_scaled_increment_error':error,'order':'reference / axis / axis / reference',
            'measurements':measured,'axis_over_reference_cpu_ratios':ratios,
            'median_cpu_ratio':float(np.median(ratios)),
            'scope':'frozen full-rule graph passes, excludes step updates, not a quality benchmark'}


def admission(fixtures,traces,probe):
    ratios=[]
    for q,recall,seed in ((q,r,s) for q in (2,3) for r in (2,None) for s in SEEDS):
        scores={r['method']:r['checkpoints'][-1]['full_history_evaluation']['nashconv'] for r in fixtures
                if (r['quantity'],r['recall'],r['seed'])==(q,recall,seed)}
        ratios.append(scores['axis']/max(scores['reference'],1e-15))
    ev=max(abs(t['checkpoints'][-1]['axis']['ev_p0']-t['checkpoints'][-1]['reference']['ev_p0']) for t in traces)
    nc=max(abs(t['checkpoints'][-1]['axis']['nashconv']-t['checkpoints'][-1]['reference']['nashconv']) for t in traces)
    cost=probe['median_cpu_ratio']<=.85
    sensitivity=max(ev,nc)<=.01
    quality_gate=float(np.median(ratios))<=1 and max(ratios)<=1.1
    return {'contract':'frozen CPU median <=0.85; fixed-count endpoint EV/NC drift <=0.01; recall-2/full equal-CPU NC median ratio <=1 and maximum <=1.1',
            'statistical_significance_claim':False,'cost_passed':cost,'sensitivity_passed':sensitivity,
            'quality_passed':quality_gate,'fixture_nc_ratios':ratios,'median_fixture_nc_ratio':float(np.median(ratios)),
            'maximum_fixture_nc_ratio':max(ratios),'fixture_wins':sum(x<1 for x in ratios),
            'maximum_fixed_count_ev_drift':ev,'maximum_fixed_count_nc_drift':nc,
            'passed':bool(cost and sensitivity and quality_gate)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'outputs/axis-batches.json')
    parser.add_argument('--seconds',type=float,default=1800)
    parser.add_argument('--replay-counts',type=Path,help='Replay archived CPU-run iteration counts and admission decision')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0: parser.error('Positive finite guard required')
    replay=json.loads(args.replay_counts.read_text()) if args.replay_counts else None
    report={'status':'running','source_sha256_lf':hashes(),'platform':platform.platform(),
            'python':platform.python_version(),'numpy':np.__version__,'processor':platform.processor(),
            'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS'),'seeds':SEEDS,'batch_size':8,
            'fixed_count_checkpoints':[100,500],'fixture_cpu_budgets':[1,5],'full_cpu_budgets':[15,60],
            'execution_mode':'archived iteration counts' if replay else 'measured training CPU budgets',
            'replay_input_sha256':hashlib.sha256(args.replay_counts.read_bytes()).hexdigest() if replay else None,
            'guard_seconds':args.seconds,'guard_semantics':'between work units, not a hard deadline',
            'fixed_count_runs':[],'fixture_runs':[],'full_runs':[],'certified_equilibrium':False}
    start,cpu=time.perf_counter(),time.process_time()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def guard():
        if time.perf_counter()-start>args.seconds: raise TimeoutError('Study guard reached')
    def save():
        report['wall_seconds'],report['cpu_seconds']=time.perf_counter()-start,time.process_time()-cpu
        report['peak_process_memory']=peak_memory()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def export_fixture(game,policy,name):
        data=json.dumps(policy_table(game,policy),sort_keys=True,separators=(',',':')).encode()+b'\n'
        (args.output.parent/name).write_bytes(data)
        return {'file':name,'sha256':hashlib.sha256(data).hexdigest()}
    def train(t,row,budget,group):
        count=None
        if replay:
            old=next(r for r in replay[group] if all(r.get(k)==row.get(k) for k in ('quantity','recall','seed','method')))
            count=next(c['iterations'] for c in old['checkpoints'] if c['cpu_budget']==budget)
        used=row['checkpoints'][-1]['training_cpu_seconds'] if row['checkpoints'] else 0.
        wall=row['checkpoints'][-1]['training_wall_seconds'] if row['checkpoints'] else 0.
        w,c=time.perf_counter(),time.process_time()
        while (t.iterations<count if count is not None else used+time.process_time()-c<budget): guard();t.step()
        return {'cpu_budget':budget,'iterations':t.iterations,'training_cpu_seconds':used+time.process_time()-c,
                'training_wall_seconds':wall+time.perf_counter()-w,'coverage':coverage(t),'maximum_summed_reach':t.maximum_reach}
    save()
    try:
        report['frozen_probe']=frozen_probe(guard);gc.collect();save();guard()
        print(json.dumps({'frozen_probe':report['frozen_probe']}),flush=True)
        for q in (2,3):
            game=HouseFixture(q)
            for recall in (1,2,None):
                ref,new=BatchFixtureTrainer(game,recall,490061,8,True),AxisFixtureTrainer(game,recall,490061,8,True)
                row={'quantity':q,'recall':recall,'seed':490061,'checkpoints':[]}
                report['fixed_count_runs'].append(row)
                for target in report['fixed_count_checkpoints']:
                    w,c=time.perf_counter(),time.process_time()
                    while ref.iterations<target: guard();ref.step();new.step()
                    record={'iterations':target,'paired_training_cpu_seconds':time.process_time()-c,
                            'paired_training_wall_seconds':time.perf_counter()-w}
                    a,b=ref.freeze(),new.freeze()
                    record['maximum_policy_probability_difference']=float(np.max(np.abs(a.data-b.data)))
                    for name,t in (('reference',a),('axis',b)):
                        record[name]=evaluate(game,t.policy)
                        if target==500:
                            record[name]['policy']=export_fixture(game,t,f'axis-trace-q{q}-m{recall}-{name}-490061.json')
                    if not np.array_equal(ref.visits,new.visits): raise AssertionError('Sample streams differ')
                    row['checkpoints'].append(record)
                    print(json.dumps({'trace':q,'recall':recall,'iterations':target,'probability_difference':record['maximum_policy_probability_difference']}),flush=True)
                    del a,b;save();guard()
                del ref,new;gc.collect()
                for s,seed in enumerate(SEEDS):
                    methods=('reference','axis') if s%2==0 else ('axis','reference')
                    for method in methods:
                        t=(BatchFixtureTrainer if method=='reference' else AxisFixtureTrainer)(game,recall,seed,8,True)
                        row={'quantity':q,'recall':recall,'seed':seed,'method':method,'checkpoints':[]}
                        report['fixture_runs'].append(row)
                        for budget in report['fixture_cpu_budgets']:
                            record=train(t,row,budget,'fixture_runs');frozen=t.freeze()
                            record['full_history_evaluation']=evaluate(game,frozen.policy)
                            if budget==5: record['policy']=export_fixture(game,frozen,f'axis-fixture-q{q}-m{recall}-{method}-{seed}.json')
                            row['checkpoints'].append(record)
                            print(json.dumps({'fixture':q,'recall':recall,'method':method,'seed':seed,'budget':budget,
                                              'iterations':t.iterations,'NC':record['full_history_evaluation']['nashconv']}),flush=True)
                            del frozen;save();guard()
                        del t;gc.collect()
        report['admission']=admission(report['fixture_runs'],report['fixed_count_runs'],report['frozen_probe']);save()
        admitted=replay['admission']['passed'] if replay else report['admission']['passed']
        report['full_pilot_decision']='archived admission replay' if replay else 'admitted' if admitted else 'no-go'
        if admitted:
            game=Game();guide=ProbabilityGuide(game)
            for s,seed in enumerate(SEEDS):
                methods=('reference','axis') if s%2==0 else ('axis','reference')
                for method in methods:
                    t=(BatchTrainer if method=='reference' else AxisTrainer)(game,seed,8,True)
                    row={'method':method,'seed':seed,'array_bytes':t.array_bytes,'checkpoints':[]}
                    report['full_runs'].append(row)
                    for budget in report['full_cpu_budgets']:
                        record=train(t,row,budget,'full_runs');frozen=t.freeze()
                        record['quality']=quality(game,guide,frozen,2000,seed+budget*10000,32)
                        if budget==60:
                            path=args.output.parent/f'axis-full-{method}-{seed}.npz'
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
                        print(json.dumps({'full':method,'seed':seed,'budget':budget,'iterations':t.iterations,
                                          'lower':record['quality']['nashconv_lower'],'upper':record['quality']['nashconv_upper']}),flush=True)
                        del frozen;save();guard()
                    del t;gc.collect()
        if hashes()!=report['source_sha256_lf']: raise RuntimeError('Source changed during study')
        report['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        report['status'],report['failure']='incomplete',f'{type(error).__name__}: {error}'
        raise
    finally:save()


if __name__=='__main__':main()
