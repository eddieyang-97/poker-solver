"""Run only the pinned independent implementation in a separate process.

Accept the upstream CLI's JSON configuration and emit its ordered strategy dump,
raw exploitability checkpoints and training costs. No product code is imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tracemalloc

VENDOR = Path(__file__).resolve().parent / 'vendor' / 'noambrown'
COMMIT = '6a10442877ffc8fd28af93e16e279b9bbdd97b2a'


def verify_reference():
    manifest = json.loads((VENDOR / 'provenance.json').read_text())
    if manifest['commit'] != COMMIT:
        raise ValueError('Unexpected reference version')
    for name, expected in manifest['sha256_lf'].items():
        content = (VENDOR / name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f'Reference source changed: {name}')


def run(config, iterations, fast_eval=False):
    verify_reference()
    sys.path.insert(0, str(VENDOR))
    from algorithms.naive_eval import exploitability_naive
    from algorithms.vector_cfr import VectorCFRConfig, VectorCFRTrainer
    from games.river_holdem import RiverHoldemConfig, RiverHoldemGame, card_str

    for name in ('algorithms.vector_cfr', 'algorithms.vector_eval', 'algorithms.naive_eval', 'games.river_holdem'):
        if VENDOR.resolve() not in Path(sys.modules[name].__file__).resolve().parents:
            raise ValueError('Reference import was shadowed')
    allowed = {'board', 'pot', 'stack', 'bet_sizes', 'include_all_in', 'max_raises', 'players'}
    if set(config) != allowed or len(config['players']) != 2:
        raise ValueError('Explicit upstream configuration required')
    players = config['players']
    game = RiverHoldemGame(RiverHoldemConfig(
        board=config['board'], pot=config['pot'], stacks=(config['stack'],)*2,
        bet_sizes=config['bet_sizes'], include_all_in=config['include_all_in'],
        max_raises=config['max_raises'],
        ranges=tuple(player['hands'] for player in players),
        range_weights=tuple(player['weights'] for player in players)))
    trainer = VectorCFRTrainer(game, VectorCFRConfig(
        use_plus=True, linear_weighting=True, alternating=True, use_naive_eval=not fast_eval))
    checkpoints = []
    completed = 0
    seconds = 0.0
    peak = 0
    targets = sorted({n for n in (25, 50, 100, 200, 400, 800, 1600, iterations) if n <= iterations})
    for target in targets:
        tracemalloc.start()
        start = time.perf_counter()
        trainer.run(target-completed)
        seconds += time.perf_counter()-start
        _, allocation = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak = max(peak, allocation)
        completed = target
        profile = trainer.average_strategy_profile()
        checkpoints.append({'iterations': target, 'raw_exploitability': exploitability_naive(game, profile)})
    exported = []
    for side in (0, 1):
        exported.append({
            'hands': [''.join(card_str(c) for c in h.cards) for h in game.hands[side]],
            'weights': list(game.hand_weights[side]),
            'profile': {key: {'actions': actions, 'strategy': matrix}
                        for key, (actions, matrix) in profile[side].items()}})
    if any(name == 'poker_spot' or name.startswith('poker_spot.') for name in sys.modules):
        raise RuntimeError('Product modules loaded in independent worker')
    return {'reference_commit': COMMIT, 'pid': os.getpid(), 'product_modules_loaded': False,
            'config': config, 'iterations': iterations, 'use_naive_eval': not fast_eval,
            'checkpoints': checkpoints, 'players': exported,
            'training_cost': {'seconds': seconds, 'python_peak_bytes': peak}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--iterations', type=int, default=4000)
    parser.add_argument('--fast-eval', action='store_true', help='Reproduce the upstream fast-path failure')
    args = parser.parse_args()
    if not 20 <= args.iterations <= 100000:
        parser.error('Iterations outside benchmark budget')
    config = json.loads(args.config.read_text() if args.config else sys.stdin.read())
    print(json.dumps(run(config, args.iterations, args.fast_eval), allow_nan=False))


if __name__ == '__main__':
    main()
