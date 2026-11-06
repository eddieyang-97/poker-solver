"""Same-target response budget/allocation study on all six retained #58 targets."""
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

from bounded_response import ResponseSearch
from game import Game
from guidance import ProbabilityGuide
from ordered_response import OrderedResponseSearch, response_envelope
from recall_training import RecallPolicy
from response_refinement import CachedRecallModel, ResponsePlan, ReplayLimit, exact_response_value, game_tag
from run_fixed_strategy import peak_memory
from run_recall_training import sampled_payoff

BASE=Path(__file__).resolve().parent
SOURCES=('run_response_refinement.py','response_refinement.py','ordered_response.py','bounded_response.py',
         'game.py','one_face.py','guidance.py','recall_training.py','fixed_strategy.py',
         'run_fixed_strategy.py','run_recall_training.py','calibrate_response_refinement.py')
SCHEDULE=(('base32',1,32,'legacy'),('breadth128',1,128,'legacy'),
          ('legacy128',2,128,'legacy'),('priority128',2,128,'priority'))


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'outputs/response-refinement.json')
    parser.add_argument('--seconds',type=float,default=1800)
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0: parser.error('Positive finite guard required')
    source=BASE/'outputs/axis-batches.json'
    receipt=json.loads(source.read_text())
    targets=sorted(receipt['full_runs'],key=lambda r:(r['seed'],r['method']))
    if {(r['method'],r['seed']) for r in targets}!={(m,s) for m in ('axis','reference') for s in (490061,490062,490063)} or len(targets)!=6:
        raise ValueError('Exactly all six retained #58 target policies required')
    calibration=BASE/'outputs/response-calibration.json'
    report={'status':'running','source_sha256_lf':hashes(),'platform':platform.platform(),
            'python':platform.python_version(),'numpy':np.__version__,'processor':platform.processor(),
            'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS'),'target_receipt_sha256_lf':
                hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
            'calibration_receipt_sha256_lf':hashlib.sha256(calibration.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
            'schedule':SCHEDULE,'sampling_games_per_seat':2000,'exact_replay_limits':{'nodes':200000,'seconds':10},
            'guard_seconds':args.seconds,'guard_semantics':'between search/replay work units, not a hard process deadline',
            'targets':[],'certified_equilibrium':False,'new_training':False}
    start,cpu=time.perf_counter(),time.process_time()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def guard():
        if time.perf_counter()-start>args.seconds: raise TimeoutError('Response study guard reached')
    def save():
        report['wall_seconds'],report['cpu_seconds']=time.perf_counter()-start,time.process_time()-cpu
        report['peak_process_memory']=peak_memory()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def analyse(row):
        checkpoint=row['checkpoints'][-1];artifact=checkpoint['policy'];path=BASE/'outputs'/artifact['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=artifact['sha256']: raise ValueError('Target file fingerprint changed')
        game=Game();guide=ProbabilityGuide(game);target=RecallPolicy.load(game,path)
        if hashlib.sha256(target.data.astype('<f8').tobytes()).hexdigest()!=artifact['probabilities_sha256']:
            raise ValueError('Target probability fingerprint changed')
        model=CachedRecallModel(target)
        result={'method':row['method'],'seed':row['seed'],'training_cpu_budget':checkpoint['cpu_budget'],
                'training_iterations':checkpoint['iterations'],'target':artifact,'game':game_tag(game),
                'cache_public_keys':len(model.entries),'cache_probability_views':sum(len(e) for e in model.entries),'stages':[]}
        report['targets'].append(result);save()
        incumbents={}
        for index,(label,depth,budget,algorithm) in enumerate(SCHEDULE):
            stage={'label':label,'algorithm':algorithm,'depth':depth,'max_nodes_per_seat':budget,
                   'target_file_sha256':artifact['sha256'],'target_probabilities_sha256':artifact['probabilities_sha256'],
                   'game':game_tag(game),'incumbent_stage':None if index==0 else 'base32' if index==1 else 'breadth128','seats':[]}
            result['stages'].append(stage)
            for seat in (0,1):
                guard();w,c=time.perf_counter(),time.process_time()
                cls=ResponseSearch if algorithm=='legacy' else OrderedResponseSearch
                search=cls(game,guide,model,seat,depth,budget,incumbent=incumbents.get(seat))
                bound=search.solve()
                record={**bound,'search_wall_seconds':time.perf_counter()-w,'search_cpu_seconds':time.process_time()-c,
                        'retained_decision_nodes':len(search.decisions),'retained_bound_nodes':len(search.bounds)}
                if label=='base32':
                    old=checkpoint['quality']['seats'][seat]
                    error=max(abs(bound[k]-old[k]) for k in ('lower','upper'))
                    record['historical_baseline_error']=error
                    if error>1e-10: raise AssertionError('Historical same-target baseline changed')
                if label in ('base32','breadth128'): incumbents[seat]=search
                plan=ResponsePlan.from_search(search,artifact['probabilities_sha256'])
                output=args.output.parent/f'response-plan-{row["method"]}-{row["seed"]}-{label}-seat{seat}.json'
                record['plan']=plan.save(output)
                restored=ResponsePlan.load(game,output,artifact['probabilities_sha256'])
                for h,choices in plan.decisions.items():
                    if not np.array_equal(choices,restored.decisions[h]): raise AssertionError('Response plan roundtrip changed choices')
                guard()
                try:
                    replay=exact_response_value(game,target,restored,node_limit=200000,seconds=10)
                    record['exact_replay']={'status':'completed',**replay,'lower_error':abs(replay['value']-bound['lower'])}
                    if abs(replay['value']-bound['lower'])>1e-10: raise AssertionError('Independent exact lower realization mismatch')
                except ReplayLimit as error:
                    record['exact_replay']={'status':'budget_exceeded','reason':str(error),'stats':error.stats,
                                            'wall_seconds':error.wall_seconds,'cpu_seconds':error.cpu_seconds}
                first,second=(restored.policy,target.policy) if seat==0 else (target.policy,restored.policy)
                sample=sampled_payoff(game,first,second,490071+row['seed']+10000*index+seat,2000)
                observed=sample['ev_p0']*(1 if seat==0 else -1)
                radius=math.sqrt(2*math.log(40)/2000)
                record['independent_scalar_replay']=sample
                record['replay_matches_lower_within_individual95']=abs(observed-bound['lower'])<=radius
                stage['seats'].append(record)
                print(json.dumps({'method':row['method'],'seed':row['seed'],'stage':label,'seat':seat,
                                  'lower':bound['lower'],'upper':bound['upper'],'search_cpu':record['search_cpu_seconds'],
                                  'exact':record['exact_replay']['status']}),flush=True)
                del restored,plan,search;gc.collect();save();guard()
            stage['nashconv_lower']=max(0.,sum(s['lower'] for s in stage['seats']))
            stage['nashconv_upper']=min(2.,sum(s['upper'] for s in stage['seats']))
            stage['width']=stage['nashconv_upper']-stage['nashconv_lower']
            result['envelope']=response_envelope(result['stages'],artifact['sha256'])
            save()
        if hashlib.sha256(target.data.astype('<f8').tobytes()).hexdigest()!=artifact['probabilities_sha256']:
            raise AssertionError('Frozen target changed during analysis')
    save()
    try:
        for row in targets:
            analyse(row);gc.collect();save();guard()
        if hashes()!=report['source_sha256_lf']: raise RuntimeError('Source changed during response study')
        report['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        report['status'],report['failure']='incomplete',f'{type(error).__name__}: {error}'
        raise
    finally:save()


if __name__=='__main__':main()
