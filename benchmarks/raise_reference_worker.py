"""Pinned upstream raise trainer, isolated from every product module/policy."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference_worker import COMMIT, VENDOR, verify_reference


def decoded_sizes(values):
    """Optional exact rational configuration, interpreted without product imports."""
    out = []
    for value in values:
        if isinstance(value, dict):
            if (set(value) != {'numerator', 'denominator'}
                    or any(type(v) is not int or not 0 < v <= 100_000_000 for v in value.values())):
                raise ValueError('Invalid exact reference fraction')
            value = Fraction(value['numerator'], value['denominator'])
        out.append(value)
    return out


def run(config, iterations):
    verify_reference()
    sys.path.insert(0, str(VENDOR))
    from algorithms.naive_eval import exploitability_naive
    from algorithms.vector_cfr import VectorCFRConfig, VectorCFRTrainer
    from games.river_holdem import RiverHoldemConfig, RiverHoldemGame, card_str

    required = {'board', 'pot', 'stack', 'bet_sizes', 'raise_sizes', 'include_all_in', 'max_raises', 'players'}
    if set(config) != required or config['include_all_in'] is not False or config['max_raises'] != 2:
        raise ValueError('Explicit one-additional-raise upstream configuration required')
    players = config['players']
    game = RiverHoldemGame(RiverHoldemConfig(
        board=config['board'], pot=config['pot'], stacks=(config['stack'],)*2,
        bet_sizes=decoded_sizes(config['bet_sizes']), oop_first_raises=decoded_sizes(config['raise_sizes']),
        ip_first_raises=decoded_sizes(config['raise_sizes']),
        include_all_in=False, max_raises=2,
        ranges=tuple(p['hands'] for p in players), range_weights=tuple(p['weights'] for p in players)))
    trainer = VectorCFRTrainer(game, VectorCFRConfig(use_plus=True, linear_weighting=True, alternating=True, use_naive_eval=True))
    checkpoints, completed = [], 0
    started = time.perf_counter()
    for target in sorted({n for n in (100, 500, 1000, iterations) if n <= iterations}):
        trainer.run(target-completed)
        profile = trainer.average_strategy_profile()
        checkpoints.append({'iterations': target, 'raw_average_exploitability_cents': exploitability_naive(game, profile)})
        completed = target
    if any(n == 'poker_spot' or n.startswith('poker_spot.') for n in sys.modules):
        raise RuntimeError('Product code entered independent trainer')
    for name in ('algorithms.vector_cfr', 'algorithms.naive_eval', 'games.river_holdem'):
        if VENDOR.resolve() not in Path(sys.modules[name].__file__).resolve().parents:
            raise ValueError('Reference module was shadowed')
    return {'reference_commit': COMMIT, 'product_modules_loaded': False, 'config': config, 'iterations': iterations,
            'seconds': time.perf_counter()-started, 'checkpoints': checkpoints,
            'players': [{'hands': [''.join(card_str(c) for c in h.cards) for h in game.hands[p]],
                         'weights': list(game.hand_weights[p]),
                         'profile': {k: {'actions': actions, 'strategy': matrix} for k, (actions, matrix) in profile[p].items()}}
                        for p in (0, 1)]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations', type=int, default=4000)
    args = parser.parse_args()
    if not 20 <= args.iterations <= 10000:
        parser.error('Reference iteration bound is 20–10,000')
    print(json.dumps(run(json.load(sys.stdin), args.iterations), allow_nan=False))
