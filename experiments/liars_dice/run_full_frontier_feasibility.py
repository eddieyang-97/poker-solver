"""Bounded fixed-frontier workload on the full rules and frozen policies."""
import argparse
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from frontier_cost import FactoredReply
from game import Game
from guidance import ProbabilityGuide
from recall_training import RecallPolicy
from response_kernels import PreparedClaims
from response_refinement import CachedRecallModel, raw_columns
from run_fixed_strategy import peak_memory
from run_gap_response import BASE, normalized_hash, sha

ARCHIVE = BASE/'outputs/response-refinement.json'
SEED = 490061
METHODS = ('prepared', 'factored')
BLOCKS = 5
MAX_QUERIES = 25000
MATRIX_CAP = 32*1024**2
PAIR_EDGE_CAP = 2_000_000_000
WALL_GUARD = 360
MEMORY_TIMEOUT = 60
TOL = 1e-10
SOURCES = ('run_full_frontier_feasibility.py', 'frontier_cost.py', 'game.py', 'guidance.py',
           'response_refinement.py', 'response_kernels.py', 'recall_training.py', 'fixed_strategy.py',
           'run_fixed_strategy.py', 'run_gap_response.py')
CHECK_HANDS = ((1,1,1,1,1), (2,2,2,2,2), (6,6,6,6,6), (1,1,4,4,4),
               (1,1,1,1,6), (1,2,3,4,5), (2,3,4,5,6), (2,2,2,3,4))


@dataclass(frozen=True)
class Query:
    history: tuple
    mass: np.ndarray
    reach: float
    forced: bool
    prior_stress: bool


def full_paths(graph):
    """Shortest and longest legal full histories for each public suffix/seat."""
    short = {0: ()}
    long = {0: ()}
    for i, children in enumerate(graph.children):
        for action, child in zip(graph.actions[i], children, strict=True):
            if child is None:
                continue
            candidate = short[i]+(action,)
            if child not in short or len(candidate) < len(short[child]):
                short[child] = candidate
            candidate = long[i]+(action,)
            if child not in long or len(candidate) > len(long[child]):
                long[child] = candidate
    return short, long


def query(game, history, mass, stress=False):
    return Query(history, mass, float(mass.sum()), game.actions(history) == (-1,), stress)


def opening_workload(game, model, seat, prior):
    if seat == 0:
        paths = ((bid,) for bid in game.actions(()))
    else:
        paths = ((),)
    entries, zero = [], 0
    for h in paths:
        actions = model.actions(1-seat, h)
        for action in game.actions(h):
            if action == -1:
                continue
            if len(entries)+zero >= MAX_QUERIES:
                raise MemoryError('Opening query cap exceeded')
            mass = prior*actions[action] if action in actions else np.zeros_like(prior)
            if mass.any():
                entries.append(query(game, h+(action,), mass))
            else:
                zero += 1
    return entries, zero


def inventory_workload(game, model, seat, prior):
    graph = model.target.layout.graph
    short, long = full_paths(graph)
    entries, zero = [], 0
    for i, (actor, suffix) in enumerate(graph.keys):
        if actor != seat or not suffix:
            continue
        h = short[i]
        mass = prior.copy()
        for j, action in enumerate(h):
            if j % 2 != seat:
                rows = model.actions(1-seat, h[:j])
                mass *= rows.get(action, 0.)
        if mass.any():
            entries.append(query(game, h, mass))
        else:
            zero += 1
        # Stress each key even if its shortest path has zero target support.
        entries.append(query(game, long[i], prior, stress=True))
    return entries, zero


def describe(game, queries, zero):
    return {'queries': len(queries), 'zero_reach_omitted': zero,
            'prior_stress_queries': sum(q.prior_stress for q in queries),
            'forced_challenge_queries': sum(q.forced for q in queries),
            'maximum_bids': max(len(q.history) for q in queries),
            'maximum_legal_actions': max(len(game.actions(q.history)) for q in queries),
            'min_positive_reach': min(q.reach for q in queries),
            'unique_last_bids': len({q.history[-1] for q in queries}),
            'query_sha256': sha(b''.join(bytes(q.history)+b'\xff'+bytes([q.prior_stress])
                                        +q.mass.astype('<f8').tobytes() for q in queries))}


def values(method, game, guide, model, seat, claims, entries):
    oracle = (FactoredReply(game, model, guide, seat, max_bytes=MATRIX_CAP, max_pair_edges=PAIR_EDGE_CAP)
              if method == 'factored' else None)
    checksum = 0.
    for q in entries:
        if q.forced:
            upper = claims.value(q.history[-1], q.mass, True)
        elif oracle is None:
            upper = np.full(len(q.mass), q.reach)
        else:
            upper = oracle.upper(q.history, q.mass)
        checksum += float(upper.sum())
    return checksum, oracle.resources() if oracle is not None else None


def verify_queries(game, guide, model, seat, claims, workloads):
    """Independent direct action maxima on selected own hands, using raw dice."""
    counts, quantities = raw_columns(game)
    own = [game.hands.index(h) for h in CHECK_HANDS]
    oracle = FactoredReply(game, model, guide, seat, max_bytes=MATRIX_CAP, max_pair_edges=PAIR_EDGE_CAP)

    @lru_cache(maxsize=len(game.bids))
    def challenge_row(action, h):
        target = model.target
        return np.array([target.policy(1-seat, t, h+(action,))[0] for t in range(len(game.hands))])

    @lru_cache(maxsize=len(game.bids))
    def direct(last, h):
        challenge = 1.-2*(counts[last][own, None]+counts[last][None, :] >= quantities[last])
        for a in game.actions(h)[1:]:
            true = counts[a][own, None]+counts[a][None, :] >= quantities[a]
            np.maximum(challenge, np.where(true, 1., 1.-2*challenge_row(a, h)), out=challenge)
        return challenge

    # Index public representatives by last bid. This is valid for this
    # validated one-bid target, while every mass remains history-specific.
    reps = {}
    output = {}
    for label, entries in workloads.items():
        max_error = 0.
        if label == 'inventory':
            oracle = FactoredReply(game, model, guide, seat, max_bytes=MATRIX_CAP, max_pair_edges=PAIR_EDGE_CAP)
        for q in entries:
            last = q.history[-1]
            rep = reps.setdefault(last, q.history)
            lo = claims.value(last, q.mass, True)
            hi = lo if q.forced else oracle.upper(q.history, q.mass)
            error = float(np.max(np.abs(hi[own]-direct(last, rep) @ q.mass)))
            if error > TOL or (hi < lo-TOL).any() or (hi > q.reach+TOL).any():
                raise ArithmeticError('Full-rule frontier check failed')
            max_error = max(max_error, error)
        output[label] = {'independent_value_count': len(entries)*len(own), 'max_abs_error': max_error,
                         'factored_resources': oracle.resources()}
    return output


def cap_probe(game, guide, model, seat, queries):
    out = {}
    # Establish successful narrow queries before stressing the broad frontiers.
    queries = sorted(queries, key=lambda q: len(game.actions(q.history)))
    for name, limits in (('matrix', {'max_bytes': 1024**2}), ('work', {'max_pair_edges': 4_000_000})):
        oracle = FactoredReply(game, model, guide, seat, **limits)
        completed = 0
        for q in queries:
            if q.forced:
                continue
            try:
                oracle.upper(q.history, q.mass)
            except MemoryError as exc:
                out[name] = {'status': 'blocked', 'completed_queries': completed,
                             'history': q.history, 'reason': str(exc), 'resources': oracle.resources()}
                break
            completed += 1
        else:
            raise ArithmeticError(f'{name} stress probe did not exercise its guard')
    return out


def loaded_targets():
    rows = [t for t in json.loads(ARCHIVE.read_text())['targets'] if t['seed'] == SEED]
    if len(rows) != 2 or {t['method'] for t in rows} != {'axis', 'reference'}:
        raise ValueError('Expected the frozen axis/reference target pair')
    for row in rows:
        artifact = row['target']
        path = BASE/'outputs'/artifact['file']
        if sha(path.read_bytes()) != artifact['sha256']:
            raise ValueError('Full-rule target file changed')
        game = Game()
        target = RecallPolicy.load(game, path)
        if sha(target.data.astype('<f8').tobytes()) != artifact['probabilities_sha256']:
            raise ValueError('Full-rule target probabilities changed')
        yield row['method'], artifact, game, ProbabilityGuide(game), CachedRecallModel(target)


def workloads(game, model, seat):
    prior = np.asarray(game.prior)
    return {'opening': opening_workload(game, model, seat, prior),
            'inventory': inventory_workload(game, model, seat, prior)}


def repetitions(method, seat, label):
    if method == 'prepared':
        return (32 if seat == 0 else 2048) if label == 'opening' else 1024
    return (2 if seat == 0 else 16) if label == 'opening' else 12


def memory_worker(method):
    checked = 0
    for _, _, game, guide, model in loaded_targets():
        claims = PreparedClaims(guide)
        for seat in (0, 1):
            for entries, _ in workloads(game, model, seat).values():
                values(method, game, guide, model, seat, claims, entries)
                checked += len(entries)
    return {'process_peak': peak_memory(), 'queries': checked}


def study_target(method, artifact, game, guide, model, guard):
    claims = PreparedClaims(guide)
    seats = []
    for seat in (0, 1):
        parts = workloads(game, model, seat)
        rows = {label: describe(game, entries, zero) for label, (entries, zero) in parts.items()}
        independent = verify_queries(game, guide, model, seat, claims, {k: v[0] for k, v in parts.items()})
        caps = cap_probe(game, guide, model, seat, parts['inventory'][0])
        guard()
        for label, (entries, _) in parts.items():
            repeats = {m: repetitions(m, seat, label) for m in METHODS}
            expected = {m: values(m, game, guide, model, seat, claims, entries)[0] for m in METHODS}
            blocks = []
            for b in range(BLOCKS):
                timings = {}
                for m in (METHODS if b % 2 == 0 else METHODS[::-1]):
                    guard()
                    w, c = time.perf_counter_ns(), time.process_time_ns()
                    for _ in range(repeats[m]):
                        result, _ = values(m, game, guide, model, seat, claims, entries)
                        if result != expected[m]:
                            raise ArithmeticError('Repeated fixed workload changed its checksum')
                    timings[m] = {'cpu_ns': time.process_time_ns()-c, 'wall_ns': time.perf_counter_ns()-w}
                blocks.append(timings)
            rows[label].update(repeats_per_block=repeats, timing_blocks=blocks, checksum=expected,
                               **independent[label])
        seats.append({'seat': seat, 'workloads': rows, 'cap_probes': caps})
    return {'method': method, 'target': artifact, 'seats': seats}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=BASE/'outputs/full-frontier-feasibility.json')
    parser.add_argument('--memory-worker', choices=METHODS)
    args = parser.parse_args()
    if args.memory_worker:
        print(json.dumps(memory_worker(args.memory_worker)), flush=True)
        return
    w, c = time.perf_counter(), time.process_time()
    report = {'status': 'running', 'platform': platform.platform(), 'python': platform.python_version(),
              'numpy': np.__version__, 'openblas_threads': os.getenv('OPENBLAS_NUM_THREADS'),
              'source_sha256_lf': {n: normalized_hash(BASE/n) for n in SOURCES},
              'target_receipt_sha256_lf': normalized_hash(ARCHIVE), 'seed': SEED,
              'limits': {'max_opening_queries': MAX_QUERIES, 'matrix_bytes': MATRIX_CAP,
                         'pair_edges': PAIR_EDGE_CAP, 'wall_guard_seconds': WALL_GUARD,
                         'memory_worker_timeout_seconds': MEMORY_TIMEOUT},
              'timing_blocks': BLOCKS, 'full_game_admission': 'unchanged_no_go', 'targets': []}

    def guard():
        if time.perf_counter()-w > WALL_GUARD:
            raise TimeoutError('Full-rule workload guard exceeded between batches')

    try:
        for method, artifact, game, guide, model in loaded_targets():
            report['targets'].append(study_target(method, artifact, game, guide, model, guard))
        report['isolated_memory'] = {}
        for m in METHODS:
            guard()
            result = subprocess.run([sys.executable, __file__, '--memory-worker', m],
                                    capture_output=True, text=True, check=True, timeout=MEMORY_TIMEOUT)
            report['isolated_memory'][m] = json.loads(result.stdout)
        if {n: normalized_hash(BASE/n) for n in SOURCES} != report['source_sha256_lf']:
            raise RuntimeError('Source changed during study')
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='incomplete', failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.update(wall_seconds=time.perf_counter()-w, cpu_seconds=time.process_time()-c,
                      peak_process_memory=peak_memory())
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
