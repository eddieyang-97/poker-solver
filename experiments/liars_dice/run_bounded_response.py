"""Reproduce continuation response bounds and independently replay their policies."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from bounded_response import PopulationModel, ResponseSearch
from finite_family import Family
from game import Game
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from policy_space import BayesianComponent, PopulationMixture, PriorComponent, exact_pair


def population_at(receipt, generation, game=None, guide=None):
    game = Game() if game is None else game
    guide = ProbabilityGuide(game) if guide is None else guide
    prior_count = receipt['rounds'][0]['population_size']
    specs = receipt['components']
    family = Family(game, guide, tuple((s['challenge'], s['aspiration']) for s in specs[:prior_count]))
    components = [PriorComponent(family, i) for i in range(prior_count)]
    for index in range(generation+1):
        row = receipt['rounds'][index]
        if len(components) != row['population_size']:
            raise ValueError('Recorded population ancestry is inconsistent')
        weights = row['deployed_mixture']
        target = PopulationMixture(game, components, weights['mixture0'], weights['mixture1'])
        if index < generation:
            components.extend(BayesianComponent(game, guide, target, s['challenge'], s['aspiration'], s['tremble'])
                              for s in specs if s.get('reference_round') == index)
    return game, guide, target


def deployment_value(game, guide, target, search):
    seat = search.seat
    terms, total = [], 0.
    for index in np.flatnonzero(target.weights[1-seat] > 0):
        component = target.components[index]
        first, second = (search, component) if seat == 0 else (component, search)
        numerator, stats = exact_pair(game, guide, first, second)
        own_value = numerator/(7776**2)*(1 if seat == 0 else -1)
        weight = float(target.weights[1-seat, index])
        total += weight*own_value
        terms.append({'opponent_component':int(index), 'root_weight':weight,
                      'payoff_numerator_p0':numerator, 'payoff_denominator':7776**2, **stats})
    return total, terms


def toy_checks():
    rows = []
    for maximum in (3, 5, 7):
        game = OneFace(maximum)
        guide = ProbabilityGuide(game)
        family = Family(game, guide, ((.3, None), (.7, .2), (.5, .95)))
        target = PopulationMixture(game, [PriorComponent(family, i) for i in range(3)], [.2, .3, .5], [.4, .1, .5])
        exact = evaluate(game, target.policy)
        for depth in (1, 2, 4):
            for budget in (1, 8, 10000):
                for seat in (0, 1):
                    search = ResponseSearch(game, guide, PopulationModel(target), seat, depth, budget)
                    bound = search.solve()
                    policy = lambda p, t, h:(search.policy if p == seat else target.policy)(p, t, h)
                    realized = evaluate(game, policy)['ev_p0']*(1 if seat == 0 else -1)
                    if (bound['lower'] > exact[f'br{seat}']+1e-12
                            or bound['upper'] < exact[f'br{seat}']-1e-12
                            or abs(realized-bound['lower']) > 1e-12):
                        raise AssertionError('Independent small-game BR/realization check failed')
                    rows.append({'maximum_quantity':maximum, 'exact_best_response':exact[f'br{seat}'],
                                 'independent_realized_value':realized, **bound})
    return rows


def main():
    base = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--population', type=Path, default=base/'outputs/policy-space.json')
    parser.add_argument('--generations', type=int, nargs='+', default=[0, 1, 2])
    parser.add_argument('--depths', type=int, nargs='+', default=[1, 2])
    parser.add_argument('--max-nodes', type=int, default=32)
    parser.add_argument('--output', type=Path, default=base/'outputs/bounded-response.json')
    args = parser.parse_args()
    if min(*args.depths, args.max_nodes) < 1 or min(args.generations) < 0:
        parser.error('Positive search budgets and nonnegative generation indices required')
    source = json.loads(args.population.read_text())
    if max(args.generations) >= len(source['rounds']):
        parser.error('Unavailable population generation')
    start, cpu = time.perf_counter(), time.process_time()
    result = {'source_base':subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'source_hash_format':'sha256-lf-normalized',
              'source_sha256':{p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                               for p in sorted(base.rglob('*.py'))},
              'population_file':str(args.population),
              'population_sha256_lf':hashlib.sha256(args.population.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
              'python':platform.python_version(), 'platform':platform.platform(),
              'arguments':vars(args) | {'output':str(args.output), 'population':str(args.population)},
              'toy_checks':toy_checks(), 'runs':[], 'status':'running', 'certified_equilibrium':False,
              'bound_arithmetic':'float64; structural bounds, not outward-rounded interval certification'}

    def save():
        result['wall_seconds'], result['cpu_seconds'] = time.perf_counter()-start, time.process_time()-cpu
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')

    try:
        for generation in args.generations:
            for depth in args.depths:
                game, guide, target = population_at(source, generation)
                model = PopulationModel(target)
                row = {'generation':generation, 'population_size':len(target.components), 'depth':depth,
                       'max_nodes_per_seat':args.max_nodes, 'seats':[]}
                for seat in (0, 1):
                    step_start, step_cpu = time.perf_counter(), time.process_time()
                    search = ResponseSearch(game, guide, model, seat, depth, args.max_nodes)
                    bound = search.solve()
                    search_wall, search_cpu = time.perf_counter()-step_start, time.process_time()-step_cpu
                    realized, terms = deployment_value(game, guide, target, search)
                    if abs(realized-bound['lower']) > 1e-10:
                        raise AssertionError('Full-rule extracted policy does not realize search lower value')
                    row['seats'].append({**bound, 'search_wall_seconds':search_wall, 'search_cpu_seconds':search_cpu,
                                         'deployment_value':realized, 'deployment_terms':terms,
                                         'replay_wall_seconds':time.perf_counter()-step_start-search_wall,
                                         'replay_cpu_seconds':time.process_time()-step_cpu-search_cpu})
                    print(json.dumps({'generation':generation, 'seat':seat, 'depth':depth,
                                      'lower':bound['lower'], 'upper':bound['upper'], 'search_cpu':search_cpu}), flush=True)
                row['nashconv_lower'] = max(0., sum(s['lower'] for s in row['seats']))
                row['nashconv_upper'] = min(2., sum(s['upper'] for s in row['seats']))
                row['exploitability_lower'], row['exploitability_upper'] = row['nashconv_lower']/2, row['nashconv_upper']/2
                row['model_action_cache'] = model.actions.cache_info()._asdict()
                result['runs'].append(row)
                save()
        result['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        result['status'], result['failure'] = 'incomplete', f'{type(error).__name__}: {error}'
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
