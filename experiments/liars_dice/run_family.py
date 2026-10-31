"""Exact restricted-family equilibrium and held-out full-game response tests."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

from finite_family import Family, Mixture, MixtureResponse, exact_matrix, solve_matrix
from game import Bid, Game
from beliefs import posterior, challenge_ev
from guidance import ProbabilityGuide
from prior_control import exact_prior_value
from run_research import matches, bot_policy
from summarize import lower_bound


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--games',type=int,default=5000)
    parser.add_argument('--adaptive-games',type=int,default=2000)
    parser.add_argument('--seed',type=int,default=900001)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'outputs/family.json')
    args = parser.parse_args()
    if min(args.games,args.adaptive_games) < 1:
        parser.error('Positive game counts required')
    start,cpu_start = time.perf_counter(),time.process_time()
    game = Game()
    guide = ProbabilityGuide(game)
    family = Family(game,guide)
    numerators,denominator = exact_matrix(family)
    prior_index = family.configurations.index((.5,None))
    prior = exact_prior_value(game,guide)
    expected_numerator = prior['p0_win_weight']-prior['p0_loss_weight']
    if int(numerators[prior_index,prior_index]) != expected_numerator:
        raise AssertionError('Vectorized matrix disagrees with scalar full-game prior enumeration')
    construction_wall,construction_cpu = time.perf_counter()-start,time.process_time()-cpu_start
    checkpoints = solve_matrix(numerators/denominator)
    mix = Mixture(family,checkpoints[-1]['mixture0'],checkpoints[-1]['mixture1'])
    result = {'source_base':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'source_hash_format':'sha256-lf-normalized',
              'source_sha256':{str(p.relative_to(Path(__file__).parent)):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                               for p in sorted(Path(__file__).parent.rglob('*.py'))},
              'python':platform.python_version(),'platform':platform.platform(),
              'rules':asdict(game.rules),'configurations':[{'challenge':c,'aspiration':a} for c,a in family.configurations],
              'private_deals_per_policy_pair':len(game.prior)**2,
              'policy_pairs':len(family.configurations)**2,'payoff_denominator':denominator,
              'payoff_numerators':numerators.tolist(),'matrix_wall_seconds':construction_wall,
              'matrix_cpu_seconds':construction_cpu,'matrix_solver_checkpoints':checkpoints,
              'exact_prior_control_ev':prior['ev_p0'],'family_choice_table_bytes':family.choices.nbytes,
              'matches':{},'certified_equilibrium':False,'full_game_exploitability_upper_bound':None}
    uniform = lambda p,t,h:[1/len(game.actions(h))]*len(game.actions(h))
    bots = {'uniform':uniform,**{f'probability_{int(t*100)}':bot_policy(game,guide.truth,t) for t in (.3,.5,.7)}}
    for name,bot in bots.items():
        for seat in (0,1):
            policies = (mix.policy,bot) if seat == 0 else (bot,mix.policy)
            result['matches'][f'{name}_solver_seat{seat}'] = matches(game,policies,args.seed+seat,args.games)
    result['matches']['selfplay'] = matches(game,(mix.policy,mix.policy),args.seed+100,args.games)
    for threshold in (.4,.6):
        response = MixtureResponse(game,mix,guide,threshold=threshold)
        for seat in (0,1):
            policies = (mix.policy,response.policy) if seat == 0 else (response.policy,mix.policy)
            result['matches'][f'posterior_{int(threshold*100)}_solver_seat{seat}'] = matches(
                game,policies,args.seed+200+seat,args.adaptive_games)
        if response.zero_support:
            raise AssertionError('Mixture generated zero-support evidence')
    result['full_game_response_lower_bound'] = lower_bound(result['matches'])
    bid = game.bids.index(Bid(5,4,'fly'))
    conditioned = posterior(game,1,(bid,),mix.policy)
    illustrations = []
    for hand in ((1,1,2,3,5),(2,3,4,4,4),(2,2,3,5,6)):
        index = game.hands.index(hand)
        own = guide.counts[index,bid]
        truth = float(((own+guide.counts[:,bid]) >= 5) @ conditioned)
        ev = challenge_ev(game,1,index,(bid,),mix.policy)
        if abs(ev-(1-2*truth)) > 1e-12:
            raise AssertionError('Independent conditioning and terminal utility disagree')
        illustrations.append({'own_hand':hand,'bid':asdict(game.bids[bid]),
                              'prior_truth':float(guide.truth[index,bid]),'conditioned_truth':truth,
                              'conditioned_challenge_ev':ev})
    result['conditioning_illustration'] = {
        'opponent_model':'player0 frozen finite-family mixture, not a human population model',
        'opening_probability':float(mix.likelihood(0,(),bid) @ guide.prior),
        'examples':illustrations}
    result['total_wall_seconds'] = time.perf_counter()-start
    result['total_cpu_seconds'] = time.process_time()-cpu_start
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'family_gap':checkpoints[-1]['family_nashconv'],
                      'family_value':checkpoints[-1]['value'],
                      'full_game_response_lower_bound':result['full_game_response_lower_bound'],
                      'wall_seconds':result['total_wall_seconds']},indent=2))


if __name__ == '__main__':
    main()
