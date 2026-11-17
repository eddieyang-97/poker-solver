"""Matched count and recall study of stratified versus IID crossed blocks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from axis_batches import AxisFixtureTrainer
from one_face import evaluate
from recall_ablation import HouseFixture
from run_fixed_strategy import peak_memory
from stratified_chance import StratifiedHands

BASE = Path(__file__).resolve().parent
SEEDS = (490131, 490132, 490133)
BUDGETS = (256, 1024, 2048)
SOURCES = ('run_stratified_chance.py', 'stratified_chance.py', 'axis_batches.py', 'crossed_batches.py',
           'recall_ablation.py', 'recall_training.py', 'fixed_strategy.py', 'game.py', 'one_face.py',
           'run_fixed_strategy.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run_pair(game, recall, seed, arrays):
    trainers = {m: AxisFixtureTrainer(game, recall, seed, 8, True) for m in ('iid', 'stratified')}
    sampler = StratifiedHands(game.weights, 8)
    records = {m: [] for m in trainers}
    cpu = dict.fromkeys(trainers, 0.)
    wall = cpu.copy()
    for index, budget in enumerate(BUDGETS):
        order = list(trainers)
        if (seed + index) % 2:
            order.reverse()
        for method in order:
            trainer = trainers[method]
            w, c = time.perf_counter(), time.process_time()
            while trainer.iterations < budget:
                trainer.step(sampler.deal(trainer.rng) if method == 'stratified' else None)
            cpu[method] += time.process_time()-c
            wall[method] += time.perf_counter()-w
            policy = trainer.freeze()
            key = f'q{game.zhai_quantity}_r{recall}_s{seed}_{method}_b{budget}'
            arrays[key] = policy.data.astype('<f8')
            records[method].append({'blocks': budget, 'training_cpu': cpu[method], 'training_wall': wall[method],
                                    'policy': key, 'policy_sha256': digest(arrays[key].tobytes()),
                                    'score': evaluate(game, policy.policy)})
    return {'quantity': game.zhai_quantity, 'recall': recall, 'seed': seed, 'methods': records}


def summarize(pairs):
    rows = []
    for recall in (1, 2, None):
        group = [p for p in pairs if p['recall'] == recall]
        for index, budget in enumerate(BUDGETS):
            ratios, costs = [], []
            for pair in group:
                iid, strat = [pair['methods'][m][index] for m in ('iid', 'stratified')]
                ratios.append(strat['score']['nashconv']/iid['score']['nashconv'])
                costs.append(strat['training_cpu']/iid['training_cpu'])
            rows.append({'recall': recall, 'blocks': budget, 'median_nc_ratio': median(ratios),
                         'min_nc_ratio': min(ratios), 'max_nc_ratio': max(ratios),
                         'wins': sum(v < 1 for v in ratios), 'cases': len(group),
                         'median_cpu_ratio': median(costs)})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=BASE/'outputs')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    w, c = time.perf_counter(), time.process_time()
    report = {'seeds': SEEDS, 'block_size': 8, 'checkpoints': BUDGETS, 'python': platform.python_version(),
              'platform': platform.platform(), 'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: digest((BASE/n).read_bytes().replace(b'\r\n', b'\n')) for n in SOURCES},
              'pairs': []}
    arrays = {}
    for q in (2, 3):
        game = HouseFixture(q)
        for recall in (1, 2, None):
            for seed in SEEDS:
                report['pairs'].append(run_pair(game, recall, seed, arrays))
            print(f'Finished q={q}, recall={recall}', flush=True)
    report['summary'] = summarize(report['pairs'])
    path = args.out_dir/'stratified-chance-policies.npz'
    np.savez_compressed(path, **arrays)
    report.update(archive=path.name, archive_sha256=digest(path.read_bytes()), wall_seconds=time.perf_counter()-w,
                  cpu_seconds=time.process_time()-c, peak_process_memory=peak_memory())
    (args.out_dir/'stratified-chance.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n',
                                                      encoding='utf-8', newline='\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
