"""Matched exact/sampled learning curves and recall ablations; no full-game claim."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from one_face import evaluate
from recall_ablation import HouseFixture, ExactFixtureCFR, SampledFixtureCFR
from run_fixed_strategy import peak_memory

BASE = Path(__file__).resolve().parent
SOURCES = ('recall_ablation.py','run_recall_ablation.py','recall_training.py',
           'fixed_strategy.py','game.py','one_face.py','run_fixed_strategy.py')


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def policy_table(game, solver):
    # FULL public histories, even for a policy whose own key forgets them.
    result = {}
    def walk(h):
        result[','.join(map(str,h))] = [list(map(float,solver.policy(len(h)%2,t,h))) for t in range(len(game.hands))]
        for a in game.actions(h):
            if a != -1: walk(h+(a,))
    walk(())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoints',type=int,nargs='+',default=[1000,5000,20000])
    parser.add_argument('--seeds',type=int,nargs='+',default=[490021,490022,490023])
    parser.add_argument('--seconds',type=float,default=1200)
    parser.add_argument('--output',type=Path,default=BASE/'outputs/recall-ablation.json')
    args = parser.parse_args()
    if args.checkpoints != sorted(set(args.checkpoints)) or min(args.checkpoints) < 1 or args.seconds <= 0:
        parser.error('Positive sorted checkpoints and time guard required')
    report = {'status':'running','source_sha256_lf':hashes(),
              'platform':platform.platform(),'processor':platform.processor(),
              'python':platform.python_version(),'numpy':np.__version__,
              'checkpoints':args.checkpoints,'sampled_seeds':args.seeds,
              'arithmetic':'exact chance enumeration/evaluation in float64, not rational/interval certification',
              'scope':'two action-restricted single-round house games; no full-game exploitability bound',
              'guard_semantics':'between iterations and evaluations; not a hard deadline','fixtures':[]}
    start,cpu = time.perf_counter(),time.process_time()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        report['wall_seconds'],report['cpu_seconds'] = time.perf_counter()-start,time.process_time()-cpu
        report['peak_process_memory'] = peak_memory()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def guard():
        if time.perf_counter()-start > args.seconds: raise TimeoutError('Ablation time guard exceeded')
    save()
    try:
        for q in (2,3):
            game = HouseFixture(q)
            fixture = {'zhai_quantity':q,'selected_bids':[vars(b) for b in game.bids],
                       'types':len(game.hands),'integer_weights_out_of_7776':game.weights,
                       'profiles':game.hands,'projection_from_252':game.projection,'runs':[]}
            report['fixtures'].append(fixture)
            for recall in (1,2,None):
                for seed in (None,*args.seeds):
                    solver = ExactFixtureCFR(game,recall) if seed is None else SampledFixtureCFR(game,recall,seed)
                    graph = solver.graph if seed is None else solver.layout.graph
                    run = {'method':'exact_deals' if seed is None else 'sampled_deals',
                           'recall':recall,'seed':seed,'public_nodes':len(graph.keys),
                           'table_or_estimated_array_bytes':solver.estimated_array_bytes if seed is None else solver.array_bytes,
                           'completed_iterations':0,'checkpoints':[]}
                    fixture['runs'].append(run)
                    wall=cpu_time=0.
                    for checkpoint in args.checkpoints:
                        t,c = time.perf_counter(),time.process_time()
                        while solver.iterations < checkpoint:
                            guard();solver.step()
                        wall += time.perf_counter()-t;cpu_time += time.process_time()-c
                        candidate = solver if seed is None else solver.freeze()
                        score = evaluate(game,candidate.policy)
                        row = {'iterations':checkpoint,'training_wall_seconds':wall,
                               'training_cpu_seconds':cpu_time,'full_history_evaluation':score}
                        if seed is not None:
                            row['coverage'] = [{'seat':p,'unseen_types':int((solver.visits[p] == 0).sum()),
                                'unseen_prior_mass':float(np.asarray(game.prior)[solver.visits[p] == 0].sum())} for p in (0,1)]
                        if checkpoint == args.checkpoints[-1]:
                            table = policy_table(game,candidate)
                            data = json.dumps(table,sort_keys=True,separators=(',',':')).encode()
                            name = f'ablation-q{q}-m{recall}-{seed}.json'
                            (args.output.parent/name).write_bytes(data+b'\n')
                            row['policy'] = {'file':name,'sha256':hashlib.sha256(data+b'\n').hexdigest()}
                        run['completed_iterations'] = checkpoint
                        run['checkpoints'].append(row)
                        print(json.dumps({'q':q,'recall':recall,'seed':seed,'iterations':checkpoint,
                                          'nashconv':score['nashconv']}),flush=True)
                        save();guard()
                    del solver
        if hashes() != report['source_sha256_lf']: raise RuntimeError('Source changed during run')
        report['status'] = 'completed'
    except (Exception,KeyboardInterrupt) as error:
        report['status'],report['failure'] = 'incomplete',f'{type(error).__name__}: {error}'
        raise
    finally: save()


if __name__ == '__main__': main()
