"""Held-out ordering and matched-training-CPU study of crossed CFR blocks."""
import argparse
import json
import os
from pathlib import Path
import platform
import random
from statistics import median
import time

import numpy as np

from axis_batches import AxisFixtureTrainer
from game import Bid, hand_distribution
from one_face import evaluate
from recall_ablation import HouseFixture
from run_fixed_strategy import peak_memory
from run_stratified_chance import BASE, SOURCES, digest
from stratified_chance import StratifiedHands

FIXTURES = ('q2', 'q3', 'q2-face6')
RECALLS = (1, 2, None)
SEEDS = (490141, 490142)
ORDER_SEED = 490140
FROZEN_SEED = 490143
MOMENT_SEEDS = (490151, 490152, 490153, 490154)
MOMENT_BLOCKS = 64
BLOCK_SIZE = 8
CHECKPOINTS = (1., 2.5, 5.)
CPU_SLICE = .5
MAX_BLOCKS = 32768
MAX_TRAIN_WALL = 45.
METHODS = ('iid', 'profile', 'zhai-first', 'permuted')


class ThirdFaceFixture(HouseFixture):
    """q2 plus a legal 3 fly face-six bid, with lossless retained-bid profiles."""

    def __init__(self):
        base = HouseFixture(2)
        self.full = base.full
        self.zhai_quantity = base.zhai_quantity
        self.selected = (*base.selected, self.full.bids.index(Bid(3, 6, 'fly')))
        self.bids = tuple(self.full.bids[a] for a in self.selected)
        profiles = [tuple(row[a] for a in self.selected) for row in self.full.counts]
        self.hands = self.counts = tuple(sorted(set(profiles)))
        indices = {profile: i for i, profile in enumerate(self.hands)}
        self.projection = tuple(indices[profile] for profile in profiles)
        self.weights = [0] * len(self.hands)
        for index, (_, weight) in zip(self.projection, hand_distribution(), strict=True):
            self.weights[index] += weight
        self.prior = tuple(weight / 7776 for weight in self.weights)
        self._legal = {}
        for last in (None, *range(len(self.bids))):
            legal = self.full.actions(() if last is None else (self.selected[last],))
            opens = [] if last is None else [-1]
            self._legal[last] = tuple(opens + [i for i, a in enumerate(self.selected) if a in legal])


def fixture(name):
    if name == 'q2-face6':
        return ThirdFaceFixture()
    return HouseFixture({'q2': 2, 'q3': 3}[name])


def hand_orders(game):
    ids = list(range(len(game.hands)))
    zhai = [i for i, b in enumerate(game.bids) if b.mode == 'zhai']
    shuffled = ids.copy()
    random.Random(ORDER_SEED).shuffle(shuffled)
    zhai_first = sorted(ids, key=lambda i: tuple(game.counts[i][a] for a in zhai))
    return {'profile': ids, 'zhai-first': zhai_first, 'permuted': shuffled}


class OrderedDraws:
    def __init__(self, game, order):
        self.order = order
        self.sampler = StratifiedHands([game.weights[i] for i in order], BLOCK_SIZE)

    def __call__(self, rng):
        return tuple([self.order[i] for i in row] for row in self.sampler.deal(rng))


def iid_draw(game, rng):
    rows = rng.choices(range(len(game.hands)), weights=game.prior, k=2*BLOCK_SIZE)
    return rows[:BLOCK_SIZE], rows[BLOCK_SIZE:]


def budget_record(trainer, name, target, cpu, wall, arrays):
    policy = trainer.freeze()
    arrays[name] = policy.data.astype('<f8')
    return {'target_cpu': target, 'training_cpu': cpu, 'training_wall': wall,
            'blocks': trainer.iterations,
            'distinct_hands_seen': np.count_nonzero(trainer.visits, axis=1).tolist(),
            'policy': name, 'policy_sha256': digest(arrays[name].tobytes()),
            'score': evaluate(trainer.game, policy.policy)}


def advance(trainer, sampler, target, cpu, wall):
    start_cpu, start_wall = time.process_time(), time.perf_counter()
    elapsed = 0.
    while cpu + elapsed < target:
        if trainer.iterations >= MAX_BLOCKS or wall + time.perf_counter() - start_wall >= MAX_TRAIN_WALL:
            raise RuntimeError(f'CPU checkpoint {target:g}s stopped at {trainer.iterations} blocks, '
                               f'{cpu + elapsed:.3f}s CPU and {wall + time.perf_counter() - start_wall:.3f}s wall')
        trainer.step(None if sampler is None else sampler(trainer.rng))
        elapsed = time.process_time() - start_cpu
    return cpu + elapsed, wall + time.perf_counter() - start_wall


def learning_curves(game, samplers, label, recall, seed, arrays):
    trainers = {method: AxisFixtureTrainer(game, recall, seed, BLOCK_SIZE, True) for method in METHODS}
    cpu = dict.fromkeys(METHODS, 0.)
    wall = cpu.copy()
    rows = {method: [] for method in METHODS}
    rotation = seed % len(METHODS)
    for step in range(1, round(CHECKPOINTS[-1] / CPU_SLICE) + 1):
        target = step * CPU_SLICE
        order = METHODS[rotation:] + METHODS[:rotation]
        rotation = (rotation + 1) % len(METHODS)
        for method in order:
            cpu[method], wall[method] = advance(trainers[method], samplers[method], target, cpu[method], wall[method])
        if target in CHECKPOINTS:
            for method in METHODS:
                key = f'{label}_r{recall}_s{seed}_{method}_cpu{target:g}'
                rows[method].append(budget_record(trainers[method], key, target, cpu[method], wall[method], arrays))
    return {'fixture': label, 'recall': recall, 'seed': seed, 'methods': rows}


def dense_increments(trainer, hands):
    """Measure actual scattered vectors, including covariance between repeated rows."""
    delta, average, _, _ = trainer.batch_increments(hands)
    n = len(trainer.game.hands)
    layout = trainer.layout
    result = np.zeros((2, layout.entries))
    for i, seat in enumerate(layout.players):
        a, b = layout.offsets[i:i+2]
        block = result[:, a:b].reshape(2, n, -1)
        np.add.at(block[0], hands[seat], delta[i])
        np.add.at(block[1], hands[seat], average[i])
    return result


def frozen_block_stats(trainer, sampler, seed, blocks=MOMENT_BLOCKS):
    rng = random.Random(seed)
    mean = np.zeros((2, trainer.layout.entries))
    ss = np.zeros_like(mean)
    unique = np.zeros(2, dtype=int)
    pairs = 0
    for count in range(1, blocks+1):
        hands = iid_draw(trainer.game, rng) if sampler is None else sampler(rng)
        support = [len(set(row)) for row in hands]
        unique += support
        pairs += support[0] * support[1]
        values = dense_increments(trainer, hands)
        change = values - mean
        mean += change / count
        ss += change * (values - mean)
    # Trace of the unbiased sample covariance in each seat's table coordinates.
    trace = np.zeros((2, 2))
    for i, seat in enumerate(trainer.layout.players):
        a, b = trainer.layout.offsets[i:i+2]
        trace[:, seat] += ss[:, a:b].sum(axis=1) / (blocks - 1)
    return {'seed': seed, 'blocks': blocks, 'regret_trace_by_seat': trace[0].tolist(),
            'average_trace_by_seat': trace[1].tolist(),
            'unique_hands_by_seat': (unique / blocks).tolist(), 'unique_pairs': pairs / blocks}


def frozen_study(game, samplers, label, recall, arrays):
    trainer = AxisFixtureTrainer(game, recall, FROZEN_SEED, BLOCK_SIZE, True)
    for _ in range(128):
        trainer.step()
    key = f'{label}_r{recall}_frozen_regrets'
    arrays[key] = trainer.regret.astype('<f8')
    return {'fixture': label, 'recall': recall, 'regret_table': key, 'warmup_blocks': trainer.iterations,
            'regret_sha256': digest(arrays[key].tobytes()),
            'methods': {method: [frozen_block_stats(trainer, samplers[method], seed) for seed in MOMENT_SEEDS]
                        for method in METHODS}}


def summary(curves, diagnostics):
    learning, moments = [], []
    for recall in RECALLS:
        cases = [c for c in curves if c['recall'] == recall]
        frozen = [d for d in diagnostics if d['recall'] == recall]
        for method in METHODS[1:]:
            for index, target in enumerate(CHECKPOINTS):
                matched = [(c['fixture'], *(c['methods'][m][index] for m in ('iid', method))) for c in cases]
                ratios = [y['score']['nashconv']/x['score']['nashconv'] for _, x, y in matched]
                learning.append({
                    'recall': recall, 'method': method, 'target_cpu': target,
                    'median_nc_ratio': median(ratios), 'min_nc_ratio': min(ratios), 'max_nc_ratio': max(ratios),
                    'wins': sum(r < 1 for r in ratios), 'cases': len(ratios),
                    'holdout_wins': sum(y['score']['nashconv'] < x['score']['nashconv']
                                        for f, x, y in matched if f == 'q2-face6'),
                    'median_cpu_ratio': median(y['training_cpu']/x['training_cpu'] for _, x, y in matched),
                    'max_cpu_relative_error': max(abs(r['training_cpu']/target-1)
                                                  for _, x, y in matched for r in (x, y)),
                })
            matched_moments = [(a, b) for d in frozen
                               for a, b in zip(d['methods']['iid'], d['methods'][method], strict=True)]
            moments.append({
                'recall': recall, 'method': method, 'cases': len(matched_moments),
                'median_regret_trace_ratio': median(sum(b['regret_trace_by_seat'])/sum(a['regret_trace_by_seat'])
                                                     for a, b in matched_moments),
                'median_average_trace_ratio': median(sum(b['average_trace_by_seat'])/sum(a['average_trace_by_seat'])
                                                      for a, b in matched_moments),
                'mean_unique_pairs_iid': sum(a['unique_pairs'] for a, _ in matched_moments)/len(matched_moments),
                'mean_unique_pairs': sum(b['unique_pairs'] for _, b in matched_moments)/len(matched_moments),
            })
    supported = all(row['median_nc_ratio'] < 1 and row['wins'] >= 4 and row['holdout_wins'] == 2
                    for row in learning if row['recall'] != 1 and row['target_cpu'] == CHECKPOINTS[-1])
    matched_cpu = all(row['max_cpu_relative_error'] <= .05 for row in learning)
    return {'matched_cpu': matched_cpu, 'robust_fixture_improvement': matched_cpu and supported,
            'learning': learning, 'frozen': moments}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=BASE/'outputs')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    report = {
        'fixtures': {}, 'curves': [], 'diagnostics': [], 'seeds': SEEDS,
        'moment_seeds': MOMENT_SEEDS, 'frozen_seed': FROZEN_SEED, 'order_seed': ORDER_SEED,
        'checkpoints_cpu': CHECKPOINTS, 'block_size': BLOCK_SIZE, 'training_wall_cap': MAX_TRAIN_WALL,
        'training_block_cap': MAX_BLOCKS, 'cpu_slice': CPU_SLICE,
        'python': platform.python_version(), 'platform': platform.platform(), 'numpy': np.__version__,
        'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
        'source_sha256_lf': {n: digest((BASE/n).read_bytes().replace(b'\r\n', b'\n'))
                             for n in (*SOURCES, 'run_stratified_holdout.py')},
    }
    arrays = {}
    for label in FIXTURES:
        game = fixture(label)
        orders = hand_orders(game)
        samplers = {'iid': None, **{m: OrderedDraws(game, order) for m, order in orders.items()}}
        report['fixtures'][label] = {'bid_ids': game.selected, 'profiles': len(game.hands), 'orders': orders,
                                     'weights': game.weights}
        for recall in RECALLS:
            report['diagnostics'].append(frozen_study(game, samplers, label, recall, arrays))
            for seed in SEEDS:
                report['curves'].append(learning_curves(game, samplers, label, recall, seed, arrays))
            print(f'Finished {label}, recall={recall}', flush=True)
    report['summary'] = summary(report['curves'], report['diagnostics'])
    path = args.out_dir/'stratified-holdout-policies.npz'
    np.savez_compressed(path, **arrays)
    report.update(archive=path.name, archive_sha256=digest(path.read_bytes()), peak_process_memory=peak_memory(),
                  wall_seconds=time.perf_counter()-start_wall, cpu_seconds=time.process_time()-start_cpu)
    (args.out_dir/'stratified-holdout.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n',
                                                       encoding='utf-8', newline='\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
