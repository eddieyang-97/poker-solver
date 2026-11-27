"""Matched-CPU comparison of linear averaging and noisy regret clipping."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import time

import numpy as np

from recall_bridge import BRIDGE_QUANTITIES, BridgeEvaluator, BridgeGame
from regret_updates import VARIANTS, RegretUpdateTrainer
from run_fixed_strategy import peak_memory
from run_recall_bridge import profile_sampler
from run_stratified_chance import BASE, SOURCES, digest
from run_stratified_holdout import BLOCK_SIZE, MAX_BLOCKS, MAX_TRAIN_WALL, advance

SEEDS = (490171, 490172)
RECALLS = (1, 2)
TARGETS = (3, 7, 15)
SLICE = 1


def record(trainer, evaluator, name, target, cpu, wall, archive):
    policy = trainer.freeze()
    table = policy.data.astype('<f8')
    if target == TARGETS[-1]:
        archive[name] = table
    return {'target_cpu': target, 'training_cpu': cpu, 'training_wall': wall, 'blocks': trainer.iterations,
            'policy_sha256': digest(table.tobytes()),
            'policy': name if target == TARGETS[-1] else None, 'score': evaluator.evaluate(policy)}


def run_curves(game, evaluator, q, seed, archive):
    sampler = profile_sampler(game)
    slots = tuple((recall, variant) for recall in RECALLS for variant in VARIANTS)
    trainers = {slot: RegretUpdateTrainer(game, slot[0], seed, slot[1], BLOCK_SIZE) for slot in slots}
    cpu = dict.fromkeys(slots, 0.)
    wall = cpu.copy()
    rows = {slot: [] for slot in slots}
    start = (q + seed) % len(slots)
    for target in range(SLICE, TARGETS[-1]+1, SLICE):
        offset = (start + target - 1) % len(slots)
        for slot in slots[offset:] + slots[:offset]:
            cpu[slot], wall[slot] = advance(trainers[slot], sampler, target, cpu[slot], wall[slot])
        if target in TARGETS:
            for slot in slots:
                recall, variant = slot
                name = f'q{q}_s{seed}_r{recall}_{variant}_cpu{target}'
                rows[slot].append(record(trainers[slot], evaluator, name, target, cpu[slot], wall[slot], archive))
    return [{'quantity': q, 'seed': seed, 'recall': recall, 'variants': {v: rows[recall, v] for v in VARIANTS}}
            for recall in RECALLS]


def summarize(curves):
    summaries = []
    for recall in RECALLS:
        cases = [case for case in curves if case['recall'] == recall]
        for index, target in enumerate(TARGETS):
            for variant, control in (('signed-linear', 'signed-uniform'), ('plus-linear', 'signed-uniform'),
                                     ('plus-linear', 'signed-linear')):
                pairs = [(case['variants'][variant][index], case['variants'][control][index]) for case in cases]
                ratios = [a['score']['nashconv']/b['score']['nashconv'] for a, b in pairs]
                summaries.append({
                    'recall': recall, 'target_cpu': target, 'variant': variant, 'control': control,
                    'median_nc_ratio': median(ratios), 'max_nc_ratio': max(ratios), 'min_nc_ratio': min(ratios),
                    'wins': sum(r < 1 for r in ratios), 'cases': len(ratios),
                    'median_nc': median(a['score']['nashconv'] for a, _ in pairs),
                    'median_control_nc': median(b['score']['nashconv'] for _, b in pairs),
                    'median_blocks': median(a['blocks'] for a, _ in pairs),
                    'median_control_blocks': median(b['blocks'] for _, b in pairs),
                    'max_cpu_target_error': max(abs(row['training_cpu']/target-1) for pair in pairs for row in pair),
                })
    matched = all(r['max_cpu_target_error'] <= .05 for r in summaries)
    passes = {v: matched and all(r['median_nc_ratio'] <= .95 and r['max_nc_ratio'] <= 1.10 and r['wins'] >= 3
                                 for r in summaries if r['variant'] == v and r['control'] == 'signed-uniform'
                                 and r['target_cpu'] == TARGETS[-1])
              for v in VARIANTS[1:]}
    return {'matched_cpu': matched, 'passes_fixture_criterion': passes, 'learning': summaries}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=BASE/'outputs')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    report = {
        'seeds': SEEDS, 'recalls': RECALLS, 'targets_cpu': TARGETS, 'slice_cpu': SLICE, 'block_size': BLOCK_SIZE,
        'training_wall_cap': MAX_TRAIN_WALL, 'training_block_cap': MAX_BLOCKS, 'variants': VARIANTS,
        'python': platform.python_version(), 'platform': platform.platform(), 'numpy': np.__version__,
        'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
        'source_sha256_lf': {n: digest((BASE/n).read_bytes().replace(b'\r\n', b'\n'))
                             for n in (*SOURCES, 'run_stratified_holdout.py', 'recall_bridge.py',
                                       'run_recall_bridge.py', 'regret_updates.py', 'run_regret_updates.py')},
        'fixtures': [], 'curves': [],
    }
    policies = {}
    for q in BRIDGE_QUANTITIES:
        game = BridgeGame(q)
        evaluator = BridgeEvaluator(game)
        report['fixtures'].append({'quantity': q, 'bid_ids': game.selected, 'hand_order': profile_sampler(game).order})
        for seed in SEEDS:
            report['curves'].extend(run_curves(game, evaluator, q, seed, policies))
            print(f'Finished q{q}, seed={seed}', flush=True)
    report['summary'] = summarize(report['curves'])
    path = args.out_dir/'regret-updates-policies.npz'
    np.savez_compressed(path, **policies)
    report.update(archive=path.name, archive_sha256=digest(path.read_bytes()), peak_process_memory=peak_memory(),
                  wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu)
    (args.out_dir/'regret-updates.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n',
                                                     encoding='utf-8', newline='\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
