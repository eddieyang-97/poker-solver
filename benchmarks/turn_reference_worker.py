"""Isolated independently constructed/trained turn game; never imports product."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from benchmarks.reference_worker import COMMIT
from benchmarks.turn_reference import IndependentCFR, IndependentTurnGame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=4000)
    args = parser.parse_args()
    if not 20 <= args.iterations <= 10000:
        parser.error('Reference iterations must be in [20,10000]')
    started, cpu = time.perf_counter(), time.process_time()
    config = json.load(sys.stdin)
    game = IndependentTurnGame(config)
    trainer = IndependentCFR(game)
    checkpoints = trainer.train(args.iterations)
    profile = game.export_profile(trainer.average())
    loaded = sorted(name for name in sys.modules if name == 'poker_spot' or name.startswith('poker_spot.'))
    if loaded:
        raise RuntimeError('Independent worker imported product modules')
    report = {'implementation': 'In-repository independently constructed full-state CFR+ development reference',
              'limitation': 'Not an external audited turn solver or proven gold standard',
              'ranker_commit': COMMIT, 'pid': os.getpid(), 'product_modules_loaded': loaded,
              'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform()},
              'config': config, 'iterations': args.iterations,
              'source_sha256_lf': {p: hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                   for p in ('benchmarks/turn_reference.py', 'benchmarks/turn_reference_worker.py',
                                             'benchmarks/reference_worker.py')},
              'tree': {'concrete_nodes': len(game.records), 'information_sets': len(game.infos),
                       'compatible_deals': len(game.deals), 'initial_joint_mass': game.mass,
                       'river_cards_per_deal': sorted(set(map(len, game.legal_rivers.values()))),
                       'coalesced_public_histories': len(game.coalesced)},
              'checkpoints': checkpoints, 'profile': profile,
              'cost': {'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu}}
    print(json.dumps(report, allow_nan=False))


if __name__ == '__main__':
    main()
