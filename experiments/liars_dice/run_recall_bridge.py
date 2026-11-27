"""Matched-CPU comparison with all private hands and ten retained bids."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from recall_bridge import (
    BRIDGE_QUANTITIES, MAX_ARRAY_BYTES, MAX_STATES, RECALLS, BridgeEvaluator, BridgeGame, BridgeLayout, BridgeTrainer,
)
from run_fixed_strategy import peak_memory
from run_stratified_chance import BASE, SOURCES, digest
from run_stratified_holdout import BLOCK_SIZE, MAX_BLOCKS, MAX_TRAIN_WALL, OrderedDraws, advance

SEEDS = (490161, 490162, 490163)
TARGETS = (1, 3, 7)
METHODS = ('iid', 'profile')


def profile_sampler(game):
    return OrderedDraws(game, sorted(range(len(game.hands)), key=game.counts.__getitem__))


def checkpoint(evaluator, trainer, target, cpu, wall, key, archive):
    policy = trainer.freeze()
    data = policy.data.astype('<f8')
    if target == TARGETS[-1]:
        archive[key] = data
    visited = np.count_nonzero(trainer.visits, axis=1)
    seen_mass = (trainer.visits > 0) @ np.asarray(trainer.game.prior)
    seen_rows, all_rows = [0, 0], [0, 0]
    for i, seat in enumerate(trainer.layout.players):
        width = len(trainer.layout.graph.actions[i])
        if width > 1:
            lo, hi = trainer.layout.offsets[i:i+2]
            reach = trainer.average[lo:hi].reshape(-1, width)
            seen_rows[seat] += int(np.any(reach > 0, axis=1).sum())
            all_rows[seat] += len(reach)
    started = time.process_time()
    score = evaluator.evaluate(policy)
    return {'target_cpu': target, 'training_cpu': cpu, 'training_wall': wall, 'blocks': trainer.iterations,
            'score': score, 'evaluation_cpu': time.process_time()-started, 'policy_sha256': digest(data.tobytes()),
            'policy': key if target == TARGETS[-1] else None,
            'hand_count': visited.tolist(), 'hand_prior_mass': seen_mass.tolist(),
            'positive_average_rows': seen_rows, 'total_multi_action_rows': all_rows}


def run_curves(game, evaluator, quantity, seed, archive):
    plan = tuple((recall, method) for recall in RECALLS for method in METHODS)
    trainers = {slot: BridgeTrainer(game, slot[0], seed) for slot in plan}
    curves = {slot: [] for slot in plan}
    cpu = dict.fromkeys(plan, 0.)
    wall = cpu.copy()
    sampler = profile_sampler(game)
    rotation = (quantity + seed) % len(plan)
    for target in range(1, TARGETS[-1]+1):
        order = plan[rotation:] + plan[:rotation]
        rotation = (rotation + 1) % len(plan)
        for slot in order:
            draws = sampler if slot[1] == 'profile' else None
            cpu[slot], wall[slot] = advance(trainers[slot], draws, target, cpu[slot], wall[slot])
        if target in TARGETS:
            for slot in plan:
                recall, method = slot
                name = f'q{quantity}_s{seed}_r{recall}_{method}_cpu{target}'
                curves[slot].append(checkpoint(evaluator, trainers[slot], target, cpu[slot], wall[slot], name, archive))
    return [{'quantity': quantity, 'seed': seed, 'recall': recall,
             'methods': {m: curves[recall, m] for m in METHODS}} for recall in RECALLS]


def summarize(curves):
    learning = []
    for recall in RECALLS:
        cases = [curve for curve in curves if curve['recall'] == recall]
        for index, target in enumerate(TARGETS):
            rows = [(c['methods']['iid'][index], c['methods']['profile'][index]) for c in cases]
            ratios = [b['score']['nashconv']/a['score']['nashconv'] for a, b in rows]
            learning.append({
                'recall': recall, 'target_cpu': target, 'median_nc_ratio': median(ratios),
                'min_nc_ratio': min(ratios), 'max_nc_ratio': max(ratios), 'wins': sum(v < 1 for v in ratios),
                'cases': len(ratios), 'median_blocks_iid': median(a['blocks'] for a, _ in rows),
                'median_blocks_profile': median(b['blocks'] for _, b in rows),
                'median_nc_iid': median(a['score']['nashconv'] for a, _ in rows),
                'median_nc_profile': median(b['score']['nashconv'] for _, b in rows),
                'max_cpu_target_error': max(abs(r['training_cpu']/target-1) for pair in rows for r in pair),
            })
    matched = all(row['max_cpu_target_error'] <= .05 for row in learning)
    richer = all(row['median_nc_ratio'] <= .95 and row['max_nc_ratio'] <= 1.10 and row['wins'] >= 4
                 for row in learning if row['recall'] != 1 and row['target_cpu'] == TARGETS[-1])
    return {'matched_cpu': matched, 'richer_recall_transfer': matched and richer, 'learning': learning}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=BASE/'outputs')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    report = {
        'seeds': SEEDS, 'checkpoints_cpu': TARGETS, 'block_size': BLOCK_SIZE, 'slice_cpu': 1,
        'training_wall_cap': MAX_TRAIN_WALL, 'training_block_cap': MAX_BLOCKS, 'graph_state_cap': MAX_STATES,
        'trainer_array_cap_bytes': MAX_ARRAY_BYTES, 'python': platform.python_version(),
        'platform': platform.platform(), 'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
        'source_sha256_lf': {name: digest((BASE/name).read_bytes().replace(b'\r\n', b'\n'))
                             for name in (*SOURCES, 'run_stratified_holdout.py', 'recall_bridge.py',
                                          'run_recall_bridge.py')},
        'fixtures': [], 'curves': [],
    }
    archive = {}
    for quantity in BRIDGE_QUANTITIES:
        game = BridgeGame(quantity)
        evaluator = BridgeEvaluator(game)
        report['fixtures'].append({
            'quantity': quantity, 'bid_ids': game.selected, 'hands': len(game.hands),
            'hand_weight_sha256': digest(np.asarray(game.weights, dtype='<i8').tobytes()),
            'profile_order': profile_sampler(game).order,
            'state_counts': [len(BridgeLayout(game, r).graph.keys) for r in RECALLS],
        })
        for seed in SEEDS:
            report['curves'].extend(run_curves(game, evaluator, quantity, seed, archive))
            print(f'Finished q{quantity}, seed={seed}', flush=True)
    report['summary'] = summarize(report['curves'])
    path = args.out_dir/'recall-bridge-policies.npz'
    np.savez_compressed(path, **archive)
    report.update(archive=path.name, archive_sha256=digest(path.read_bytes()), peak_process_memory=peak_memory(),
                  wall_seconds=time.perf_counter()-start_wall, cpu_seconds=time.process_time()-start_cpu)
    (args.out_dir/'recall-bridge.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n',
                                                   encoding='utf-8', newline='\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
