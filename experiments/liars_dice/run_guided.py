"""Guidance/control-variate ablation under confirmed rules; no GTO assertion."""
import argparse
from dataclasses import asdict
import gc
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
import tracemalloc

from game import Game
from guidance import ProbabilityGuide, PosteriorResponse
from mccfr import Solver
from one_face import OneFace, evaluate
from run_research import bot_policy, matches
from summarize import lower_bound


VARIANTS = ('uniform', 'baseline_only', 'guided', 'guided_baseline')


def construct(game, guide, variant, seed, max_infos):
    if variant not in VARIANTS:
        raise ValueError("Unknown predeclared variant")
    warm = variant.startswith('guided')
    return Solver(game,seed=seed,max_infos=max_infos,
                  initial_policy=guide.policy if warm else None,initial_regret=5 if warm else 0,
                  baseline=guide.baseline if 'baseline' in variant else None)


def exact_sample_moments(game, policy, baseline=None, update=0):
    """Exact first/second moments of frozen one-episode root estimator.

    Enumerates chance and sampling paths, no learning/drift or normality claim.
    Includes chance variance. Deliberately bounded to tiny independently evaluable games.
    """
    if not isinstance(game,OneFace) or game.maximum > 5 or update not in (0,1):
        raise ValueError("Moment oracle is restricted to the one-face 3..5 fixture")

    def walk(history,hands):
        player = len(history)%2
        actions = game.actions(history)
        s = policy(player,hands[player],history)
        epsilon = .6 if player == update else .05
        sampling = [(1-epsilon)*p+epsilon/len(s) for p in s]
        b = baseline(player,hands[player],history) if baseline else [0.]*len(s)
        if player != update:
            b = [-v for v in b]
        center = sum(p*v for p,v in zip(s,b))
        mean, second = 0., 0.
        for i, action in enumerate(actions):
            if action == -1:
                child = game.payoff(history,hands,player)*(1 if update == 0 else -1)
                child_mean, child_second = child, child*child
            else:
                child_mean, child_second = walk(history+(action,),hands)
            factor = s[i]/sampling[i]
            conditional_mean = center+factor*(child_mean-b[i])
            conditional_variance = factor*factor*max(0.,child_second-child_mean*child_mean)
            mean += sampling[i]*conditional_mean
            second += sampling[i]*(conditional_mean**2+conditional_variance)
        return mean,second

    mean,second = 0.,0.
    for t0,p0 in enumerate(game.prior):
        for t1,p1 in enumerate(game.prior):
            m,s = walk((),(t0,t1))
            mean += p0*p1*m
            second += p0*p1*s
    return {'mean':mean,'second_moment':second,'variance':max(0.,second-mean*mean)}


def toy_study(seeds, checkpoints):
    game = OneFace(5)
    guide = ProbabilityGuide(game)
    uniform = lambda p,t,h:[1/len(game.actions(h))]*len(game.actions(h))
    moments = []
    for label,policy in (('uniform',uniform),('probability_only',guide.policy)):
        true_ev = evaluate(game,policy)['ev_p0']
        for baseline in (False,True):
            for update in (0,1):
                measured = exact_sample_moments(game,policy,guide.baseline if baseline else None,update)
                if abs(measured['mean']-true_ev*(1 if update == 0 else -1)) > 1e-12:
                    raise AssertionError("Sampled estimator mean does not match independent evaluation")
                moments.append({'policy':label,'baseline':baseline,'updater':update,**measured})
    runs = []
    for variant in VARIANTS:
        for seed in seeds:
            solver = construct(game,guide,variant,seed,100000)
            for target in checkpoints:
                solver.train(target-solver.iterations)
                runs.append({'variant':variant,'seed':seed,'iterations':target,
                             **evaluate(game,solver.policy)})
    return {'frozen_exact_moments':moments,'convergence':runs}


def evaluate_full(game,guide,solver,seed,games,adaptive_games):
    result = {}
    uniform = lambda p,t,h:[1/len(game.actions(h))]*len(game.actions(h))
    bots = {'uniform':uniform,**{f'probability_{int(t*100)}':bot_policy(game,guide.truth,t)
                                for t in (.3,.5,.7)}}
    for name,bot in bots.items():
        for seat in (0,1):
            policies = (solver.policy,bot) if seat == 0 else (bot,solver.policy)
            result[f'{name}_solver_seat{seat}'] = matches(game,policies,seed+100000+seat,games,solver)
    result['selfplay'] = matches(game,(solver.policy,solver.policy),seed+200000,games,solver)
    # Predeclared stronger tests: same frozen target model, posterior thresholds
    # different from the prior-only bots; fresh evaluation seeds, no training.
    for threshold in (.4,.6):
        response = PosteriorResponse(game,solver,guide,threshold=threshold)
        for seat in (0,1):
            policies = (solver.policy,response.policy) if seat == 0 else (response.policy,solver.policy)
            result[f'posterior_{int(threshold*100)}_solver_seat{seat}'] = matches(
                game,policies,seed+300000+seat,adaptive_games,solver)
        if response.zero_support:
            raise AssertionError("Frozen target generated zero-support evidence")
    return result


def full_study(variant,seed,args):
    wall_start, cpu_start = time.perf_counter(),time.process_time()
    game = Game()
    guide = ProbabilityGuide(game)
    solver = construct(game,guide,variant,seed,args.max_infos)
    status = 'completed_budget'
    checkpoints = []
    tracemalloc.start()
    try:
        for target in args.checkpoints:
            solver.train(target-solver.iterations)
            checkpoints.append({'iterations':target,'infos':len(solver.infos),
                                'cpu_seconds':time.process_time()-cpu_start,
                                'wall_seconds':time.perf_counter()-wall_start})
    except MemoryError as error:
        status = str(error)
    _,peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    training_wall, training_cpu = time.perf_counter()-wall_start,time.process_time()-cpu_start
    eval_wall, eval_cpu = time.perf_counter(),time.process_time()
    results = evaluate_full(game,guide,solver,seed,args.games,args.adaptive_games)
    bound = lower_bound(results)
    examples = []
    for hand in ((1,1,4,4,4),(2,3,4,4,4),(2,3,4,5,6),(1,1,1,1,1)):
        index = game.hands.index(tuple(sorted(hand)))
        ranked = sorted(zip(game.actions(()),solver.policy(0,index,())),key=lambda x:-x[1])[:3]
        examples.append({'hand':hand,'root_visits':solver.infos.get(game.key(0,index,())).visits
                         if game.key(0,index,()) in solver.infos else 0,
                         'top_openings':[{'bid':asdict(game.bids[a]),'p':p} for a,p in ranked]})
    return {'variant':variant,'seed':seed,'rules':asdict(game.rules),
            'requested_iterations':args.checkpoints[-1],'completed_iterations':solver.iterations,
            'status':status,'checkpoints':checkpoints,'infos':len(solver.infos),
            'initial_regret':solver.initial_regret,'exploration':solver.exploration,
            'opponent_exploration':solver.opponent_exploration,
            'training_wall_seconds':training_wall,'training_cpu_seconds':training_cpu,
            'training_traced_peak_bytes':peak,'max_prefix_importance':solver.max_importance,
            'max_value_estimate':solver.max_value_estimate,
            'evaluation_wall_seconds':time.perf_counter()-eval_wall,
            'evaluation_cpu_seconds':time.process_time()-eval_cpu,
            'matches':results,'response_lower_bound':bound,'examples':examples,
            'certified_equilibrium':False,'exploitability_upper_bound':None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds',type=int,nargs='+',default=[761245,42])
    parser.add_argument('--variants',choices=VARIANTS,nargs='+',default=list(VARIANTS))
    parser.add_argument('--checkpoints',type=int,nargs='+',default=[1000,10000])
    parser.add_argument('--games',type=int,default=2000)
    parser.add_argument('--adaptive-games',type=int,default=1000)
    parser.add_argument('--max-infos',type=int,default=200000)
    parser.add_argument('--toy-only',action='store_true')
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'outputs/guided.json')
    args = parser.parse_args()
    if (min(args.games,args.adaptive_games,args.max_infos,*args.checkpoints) < 1
            or args.checkpoints != sorted(set(args.checkpoints))):
        parser.error('Positive budgets and increasing unique checkpoints required')
    root = Path(__file__).parent
    result = {'source_base':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'source_hash_format':'sha256-lf-normalized',
              'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                               for p in sorted(root.rglob('*.py'))},
              'python':platform.python_version(),'platform':platform.platform(),
              'arguments':vars(args)|{'output':str(args.output)},
              'toy':toy_study(args.seeds,[1000,10000,100000]),'full':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)

    def save():
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    save()
    if args.toy_only:
        return
    for variant in args.variants:
        for seed in args.seeds:
            print(f'training {variant} seed={seed}',flush=True)
            result['full'].append(full_study(variant,seed,args))
            save()
            gc.collect()
    # Pure guide is an explicit untrained control; do not attribute its benefit to CFR.
    print('evaluating untrained probability guide',flush=True)
    game = Game()
    guide = ProbabilityGuide(game)
    solver = construct(game,guide,'guided',args.seeds[0],args.max_infos)
    results = evaluate_full(game,guide,solver,args.seeds[0]+400000,args.games,args.adaptive_games)
    result['untrained_probability_control'] = {'matches':results,'response_lower_bound':lower_bound(results)}
    save()
    print(f'wrote {args.output}',flush=True)


if __name__ == '__main__':
    main()
