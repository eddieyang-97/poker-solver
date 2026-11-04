"""Bounded offline one-bid-recall house-rule experiment and full-history probes."""
import argparse
from dataclasses import asdict
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import time
from types import SimpleNamespace

import numpy as np

from bounded_response import ResponseSearch
from game import Game
from guidance import ProbabilityGuide
from recall_training import RecallPolicy, RecallTrainer
from run_fixed_strategy import peak_memory

BASE = Path(__file__).resolve().parent
FILES = ('recall_training.py','run_recall_training.py','fixed_strategy.py','game.py',
         'guidance.py','bounded_response.py','run_fixed_strategy.py')


def hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in FILES}


def sampled_payoff(game, first, second, seed, games):
    """Fresh deals/actions, scalar raw-dice terminal check, no search values."""
    rng = random.Random(seed)
    total, squares, bids = 0.,0.,0
    for _ in range(games):
        hands = tuple(rng.choices(range(252),weights=game.prior,k=2))
        history = ()
        while True:
            p = len(history)%2
            actions = game.actions(history)
            policy = first if p == 0 else second
            row = policy(p,hands[p],history)
            action = rng.choices(actions,weights=row)[0]
            if action == -1:
                bid = game.bids[history[-1]]
                # Raw scoring, independent of the search's count histograms.
                count = 0
                for h in hands:
                    dice = game.hands[h]
                    target,ones = dice.count(bid.face),dice.count(1)
                    if target == 5: value = 7
                    elif bid.face == 1: value = ones
                    elif bid.mode == 'zhai': value = target
                    elif ones == 5: value = 7
                    elif target+ones == 5: value = 6
                    else: value = target+ones
                    count += value
                winner = 1-p if count >= bid.quantity else p
                payoff = 1 if winner == 0 else -1
                total += payoff; squares += payoff*payoff; bids += len(history)
                break
            history += (action,)
            if len(history) > 150: raise AssertionError('Nonterminating play')
    mean = total/games
    radius = math.sqrt(2*math.log(40)/games)
    return {'seed':seed,'games':games,'ev_p0':mean,'hoeffding95_individual':
            [max(-1,mean-radius),min(1,mean+radius)],'mean_bids':bids/games,
            'not_simultaneous_intervals':True}


def quality(game, guide, policy, games, seed, nodes):
    start,cpu = time.perf_counter(),time.process_time()
    model = SimpleNamespace(target=policy,actions=policy.actions)
    seats = []
    for seat in (0,1):
        search = ResponseSearch(game,guide,model,seat,depth=1,max_nodes=nodes)
        bound = search.solve()
        first,second = (search.policy,policy.policy) if seat == 0 else (policy.policy,search.policy)
        sample = sampled_payoff(game,first,second,seed+seat,games)
        observed = sample['ev_p0']*(1 if seat == 0 else -1)
        radius = math.sqrt(2*math.log(40)/games)
        # Diagnostic statistically permitted misses are retained, never dropped.
        seats.append({**bound,'independent_scalar_replay':sample,
                      'replay_matches_lower_within_individual95':abs(observed-bound['lower']) <= radius})
    return {'seats':seats,'nashconv_lower':max(0.,sum(s['lower'] for s in seats)),
            'nashconv_upper':min(2.,sum(s['upper'] for s in seats)),
            'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,
            'arithmetic':'float64 structural bounds, not formal interval certificates',
            'responder':'full-history depth-one continuation search; every legal action, bounded own nodes'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds',type=int,nargs='+',default=[490011,490012,490013])
    parser.add_argument('--checkpoints',type=int,nargs='+',default=[1000,5000])
    parser.add_argument('--games',type=int,default=2000)
    parser.add_argument('--nodes',type=int,default=32)
    parser.add_argument('--seconds',type=float,default=900)
    parser.add_argument('--output',type=Path,default=BASE/'outputs/recall-training.json')
    args = parser.parse_args()
    if (args.checkpoints != sorted(set(args.checkpoints)) or min(args.checkpoints) < 1
            or min(args.games,args.nodes) < 1 or not math.isfinite(args.seconds) or args.seconds <= 0
            or len(set(args.seeds)) != len(args.seeds)):
        parser.error('Positive, ordered checkpoints/budgets and distinct seeds required')
    game = Game(); guide = ProbabilityGuide(game)
    start,cpu = time.perf_counter(),time.process_time()
    result = {'status':'running','source_sha256_lf':hashes(),'rules':asdict(game.rules),
              'platform':platform.platform(),'processor':platform.processor(),
              'python':platform.python_version(),'numpy':np.__version__,
              'seeds':args.seeds,'checkpoints':args.checkpoints,'games':args.games,
              'nodes_per_seat':args.nodes,'seconds_guard':args.seconds,
              'guard_semantics':'checked between iterations and major evaluations; not a hard deadline',
              'controls':[],'runs':[],'certified_equilibrium':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        result['wall_seconds'],result['cpu_seconds'] = time.perf_counter()-start,time.process_time()-cpu
        result['peak_process_memory'] = peak_memory()
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    def guard():
        if time.perf_counter()-start > args.seconds: raise TimeoutError('Experiment time guard reached')
    save()
    try:
        trainer = RecallTrainer(game)
        uniform = trainer.freeze(); del trainer
        result['controls'].append({'name':'uniform','quality':quality(game,guide,uniform,args.games,491000,args.nodes)})
        del uniform; gc.collect(); save(); guard()
        # Explicit probability-only control with the same evaluation budget.
        class Prior:
            def policy(self,p,h,history): return guide.policy(p,h,history)
            def actions(self,p,history):
                chosen = guide._choices(history[-1] if history else None)
                return {a:(chosen == a).astype(float) for a in np.unique(chosen)}
        result['controls'].append({'name':'prior_probability_50','quality':quality(game,guide,Prior(),args.games,492000,args.nodes)})
        save(); guard()
        for seed in args.seeds:
            trainer = RecallTrainer(game,seed)
            run = {'seed':seed,'array_bytes':trainer.array_bytes,'checkpoints':[],'completed_iterations':0}
            result['runs'].append(run)
            train_wall=train_cpu=0.
            for target in args.checkpoints:
                t,c = time.perf_counter(),time.process_time()
                while trainer.iterations < target:
                    guard(); trainer.step()
                train_wall += time.perf_counter()-t; train_cpu += time.process_time()-c
                frozen = trainer.freeze()
                coverage = [{'seat':p,'unseen_types':int((trainer.visits[p] == 0).sum()),
                             'unseen_prior_mass':float(np.asarray(game.prior)[trainer.visits[p] == 0].sum()),
                             'minimum_samples':int(trainer.visits[p].min()),'visits':trainer.visits[p].tolist()} for p in (0,1)]
                record = {'iterations':target,'training_wall_seconds':train_wall,'training_cpu_seconds':train_cpu,
                          'maximum_summed_reach':trainer.maximum_reach,'coverage':coverage,
                          'quality':quality(game,guide,frozen,args.games,seed+1000000+target*10,args.nodes)}
                run['checkpoints'].append(record); run['completed_iterations'] = target
                if target == args.checkpoints[-1]:
                    path = args.output.parent/f'recall-policy-{seed}.npz'
                    record['snapshot'] = frozen.save(path)
                    restored = RecallPolicy.load(game,path)
                    if not np.array_equal(restored.data,frozen.data): raise AssertionError('Snapshot roundtrip mismatch')
                    del restored
                # Fixed training-independent probability controls, both seats.
                if target == args.checkpoints[-1]:
                    heldout = []
                    for threshold in (.3,.7):
                        opponent = ProbabilityGuide(game,threshold)
                        for seat in (0,1):
                            first,second = (frozen.policy,opponent.policy) if seat == 0 else (opponent.policy,frozen.policy)
                            heldout.append({'threshold':threshold,'candidate_seat':seat,
                                **sampled_payoff(game,first,second,seed+2000000+int(threshold*100)+seat,args.games)})
                    record['heldout'] = heldout
                print(json.dumps({'seed':seed,'iterations':target,'lower':record['quality']['nashconv_lower'],
                                  'upper':record['quality']['nashconv_upper'],'training_cpu':train_cpu}),flush=True)
                del frozen; save(); guard()
            del trainer; gc.collect()
        if hashes() != result['source_sha256_lf']: raise RuntimeError('Source changed during run')
        result['status'] = 'completed'
    except (Exception,KeyboardInterrupt) as error:
        result['status'],result['failure'] = 'incomplete',f'{type(error).__name__}: {error}'
        raise
    finally: save()


if __name__ == '__main__': main()
