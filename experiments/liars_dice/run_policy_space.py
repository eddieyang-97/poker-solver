"""Exact-chance policy-population expansion with heuristic Bayesian responses."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from finite_family import Family, exact_matrix, solve_matrix
from game import Game
from guidance import ProbabilityGuide
from policy_space import BayesianComponent, PopulationMixture, PriorComponent, exact_pair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--iterations', type=int, default=100000)
    parser.add_argument('--tremble', type=float, default=.02)
    parser.add_argument('--max-nodes', type=int, default=100000)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'outputs/policy-space.json')
    args = parser.parse_args()
    if min(args.rounds, args.iterations, args.max_nodes) < 1 or not 0 < args.tremble <= 1:
        parser.error('Positive budgets and tremble in (0,1] required')
    start, cpu = time.perf_counter(), time.process_time()
    base = Path(__file__).parent
    game = Game()
    guide = ProbabilityGuide(game)
    family = Family(game, guide)
    components = [PriorComponent(family, i) for i in range(len(family.configurations))]
    descriptions = [{'type':'prior', 'challenge':c, 'aspiration':a} for c, a in family.configurations]
    matrix, denominator = exact_matrix(family)
    result = {'source_base':subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'source_hash_format':'sha256-lf-normalized',
              'source_sha256':{p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                               for p in sorted(base.rglob('*.py'))},
              'python':platform.python_version(), 'platform':platform.platform(),
              'rules':asdict(game.rules), 'arguments':vars(args) | {'output':str(args.output)},
              'private_deals_per_pair':len(game.prior)**2, 'payoff_denominator':denominator,
              'components':descriptions, 'rounds':[], 'certified_equilibrium':False,
              'full_game_exploitability_upper_bound':None, 'status':'running'}

    def save():
        result['total_wall_seconds'] = time.perf_counter()-start
        result['total_cpu_seconds'] = time.process_time()-cpu
        result['payoff_numerators'] = matrix.tolist()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')

    try:
        for iteration in range(args.rounds+1):
            round_start, round_cpu = time.perf_counter(), time.process_time()
            report = solve_matrix(matrix/denominator, (args.iterations,))[-1]
            mix = PopulationMixture(game, components, report['mixture0'], report['mixture1'])
            # Same predeclared construction each round; no observed deal fitting.
            parameters = [(t, a) for t in (.4, .6) for a in (None, .8)]
            candidates = [BayesianComponent(game, guide, mix, t, a, args.tremble) for t, a in parameters]
            k, m = len(components), len(candidates)
            rows, columns = np.zeros((m, k), dtype=np.int64), np.zeros((k, m), dtype=np.int64)
            maximum_nodes, maximum_bids, pairs = 0, 0, 0

            def pair(a, b):
                nonlocal maximum_nodes, maximum_bids, pairs
                value, stats = exact_pair(game, guide, a, b, args.max_nodes)
                maximum_nodes = max(maximum_nodes, stats['public_nodes'])
                maximum_bids = max(maximum_bids, stats['maximum_bids'])
                pairs += 1
                return value

            for i, candidate in enumerate(candidates):
                for j, existing in enumerate(components):
                    rows[i, j], columns[j, i] = pair(candidate, existing), pair(existing, candidate)
            values0 = rows @ np.array(report['mixture1'])/denominator
            values1 = -np.array(report['mixture0']) @ columns/denominator
            lower = max(0., float(values0.max()+values1.max()))
            record = {'round':iteration, 'population_size':k, 'restricted_equilibrium':report,
                      'response_parameters':[{'threshold':t, 'aspiration':a, 'tremble':args.tremble} for t, a in parameters],
                      'response_row_numerators':rows.tolist(), 'response_column_numerators':columns.tolist(),
                      'response_values_player0':values0.tolist(), 'response_values_player1':values1.tolist(),
                      'full_game_nashconv_lower_bound':lower,
                      'full_game_exploitability_lower_bound':lower/2,
                      'full_game_exploitability_upper_bound':None,
                      'exact_pairs_evaluated':pairs, 'maximum_pair_public_nodes':maximum_nodes,
                      'maximum_bids':maximum_bids}
            result['rounds'].append(record)
            if iteration < args.rounds:
                block = np.array([[pair(a, b) for b in candidates] for a in candidates], dtype=np.int64)
                matrix = np.block([[matrix, columns], [rows, block]])
                # Every new reference is a snapshot of the PRE-expansion mixture.
                components.extend(candidates)
                descriptions.extend({'type':'bayesian', 'reference_round':iteration,
                                     'challenge':t, 'aspiration':a, 'tremble':args.tremble} for t, a in parameters)
            record['exact_pairs_evaluated'] = pairs
            record['wall_seconds'], record['cpu_seconds'] = time.perf_counter()-round_start, time.process_time()-round_cpu
            save()
            print(json.dumps({'round':iteration, 'population':k, 'family_gap':report['family_nashconv'],
                              'full_game_nashconv_lower_bound':lower, 'wall_seconds':record['wall_seconds']}), flush=True)
        result['status'] = 'completed'
    except (RuntimeError, MemoryError) as error:
        result['status'], result['failure'] = 'incomplete', str(error)
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
