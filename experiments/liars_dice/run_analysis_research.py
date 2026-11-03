"""Exact-state/query feasibility, lossy controls, resource and quality evidence."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

import numpy as np

from bounded_response import ResponseSearch
from finite_family import Family
from game import Game
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from policy_space import BayesianComponent, PopulationMixture, PriorComponent
from run_research import matches
from streaming_analysis import Analyzer, CompiledPopulation, StreamingPolicy, export_snapshot, load_snapshot, canonical
from summarize import complexity


def peak_rss():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)]+[
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                                                    'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                                                    'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel, psapi = ctypes.WinDLL('kernel32'), ctypes.WinDLL('psapi')
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
        return {'bytes':int(counters.PeakWorkingSetSize), 'method':'Windows PeakWorkingSetSize'}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'bytes':int(value*(1 if sys.platform == 'darwin' else 1024)), 'method':'getrusage(RUSAGE_SELF).ru_maxrss'}


def distribution(values):
    return {'samples':len(values), 'median':statistics.median(values), 'p95':float(np.quantile(values, .95)), 'maximum':max(values)}


def corpus(game, policy, seed=460046, games=30):
    rng = random.Random(seed)
    result = []
    for _ in range(games):
        hands, history = game.sample(rng), ()
        while True:
            player = len(history)%2
            result.append((game.hands[hands[player]], player, history))
            action = rng.choices(game.actions(history), weights=policy.policy(player, hands[player], history))[0]
            if action == -1:
                break
            history += (action,)
    return result


def stress_history(game):
    history = ()
    while True:
        bids = [a for a in game.actions(history) if a != -1]
        if not bids:
            return history
        history += (min(bids, key=lambda a:game.bids[a].rank),)


def worker(snapshot):
    start, cpu = time.perf_counter(), time.process_time()
    analyzer = Analyzer(snapshot.read_bytes())
    load_seconds = time.perf_counter()-start
    policy = StreamingPolicy(analyzer._compiled)
    cases = corpus(analyzer.game, policy)
    longest = stress_history(analyzer.game)
    cases.extend([((1, 1, 1, 1, 1), len(longest)%2, longest),
                  ((2, 3, 4, 5, 6), 1, (analyzer.game.bids.index(next(b for b in analyzer.game.bids
                                                                 if b.quantity == 14 and b.face == 1 and b.mode == 'zhai')),))])
    # Corpus generation uses a separate policy cache; timed query cache starts empty.
    analyzer._evaluate.cache_clear()
    latencies, statuses, sizes = [], {}, []
    queries = [(hand, seat, [asdict(analyzer.game.bids[a]) for a in history], analyzer.model_id) for hand, seat, history in cases]
    for query in queries:
        t = time.perf_counter()
        answer = analyzer.analyze(*query)
        latencies.append(time.perf_counter()-t)
        statuses[answer['status']] = statuses.get(answer['status'], 0)+1
        sizes.append(len(canonical(answer)))
    cold_cache = analyzer._evaluate.cache_info()._asdict()
    query = queries[-2]
    reference = analyzer.analyze(*query)
    warm = []
    for _ in range(100):
        t = time.perf_counter()
        answer = analyzer.analyze(*query)
        warm.append(time.perf_counter()-t)
        if answer != reference:
            raise AssertionError('Memoization changed analysis output')
    return {'load_seconds':load_seconds, 'query_seconds':distribution(latencies), 'repeated_stress_query_seconds':distribution(warm),
            'cold_cache':cold_cache, 'final_cache':analyzer._evaluate.cache_info()._asdict(), 'statuses':statuses,
            'maximum_history':len(longest), 'response_bytes':distribution(sizes), 'peak_process_memory':peak_rss(),
            'cpu_seconds':time.process_time()-cpu, 'wall_seconds':time.perf_counter()-start,
            'model_id':analyzer.model_id, 'digest':hashlib.sha256(canonical(reference)).hexdigest()}


class BehavioralModel:
    def __init__(self, policy):
        self.target, self.actions = policy, policy.actions


def toy_abstractions():
    game = OneFace(7)
    guide = ProbabilityGuide(game)
    family = Family(game, guide, ((.3, None), (.7, .2), (.5, .95)))
    priors = [PriorComponent(family, i) for i in range(3)]
    base = PopulationMixture(game, priors, [.2, .3, .5], [.4, .1, .5])
    target = PopulationMixture(game, [*priors, BayesianComponent(game, guide, base, .4, .8)], [.2, .3, .1, .4], [.4, .1, .2, .3])
    compiled = CompiledPopulation(game, guide, target)
    reference = evaluate(game, target.policy)
    reports = {'recursive_reference':reference}
    for label, remember in (('exact_stream', None), ('last_bid', 1), ('last_two', 2)):
        policy = StreamingPolicy(compiled, remember)
        reports[label] = evaluate(game, policy.policy)
    for key in reference:
        if abs(reference[key]-reports['exact_stream'][key]) > 1e-12:
            raise AssertionError('Streaming representation changed small-game strategy/value')
    return reports


def precompute():
    start = time.perf_counter()
    game, guide = Game(), ProbabilityGuide(Game())
    build = time.perf_counter()-start
    t = time.perf_counter()
    views, mapping = np.unique(guide.counts.T, axis=0, return_inverse=True)
    compact = views.astype('uint8').tobytes()+mapping.astype('uint8').tobytes()+guide.quantities.astype('uint8').tobytes()
    compact_seconds = time.perf_counter()-t
    t = time.perf_counter()
    truth = guide.counts[:, None, :]+guide.counts[None, :, :] >= guide.quantities
    packed = np.packbits(truth.ravel(), bitorder='little')
    pack_seconds = time.perf_counter()-t
    timings = {}
    for kind in ('counts', 'packed'):
        t = time.perf_counter()
        for i in range(1000):
            hand, bid = i%252, i%168
            if kind == 'counts':
                answer = guide.counts[hand, bid]+guide.counts[:, bid] >= guide.quantities[bid]
            else:
                indices = (hand*252+np.arange(252))*168+bid
                answer = (packed[indices//8] >> (indices%8)) & 1
            if not np.array_equal(answer, truth[hand, :, bid]):
                raise AssertionError('Packed/direct truth mismatch')
        timings[kind] = (time.perf_counter()-t)/1000
    reachable, pending = set(game.actions(())), list(game.actions(()))
    while pending:
        for action in game.actions((pending.pop(),)):
            if action != -1 and action not in reachable:
                reachable.add(action)
                pending.append(action)
    return {**complexity(game), 'syntactic_bids':len(game.bids), 'reachable_bids':len(reachable),
            'distinct_views':len(views), 'view_bytes':views.astype('uint8').nbytes,
            'compact_score_payload_bytes':len(compact), 'compact_sha256':hashlib.sha256(compact).hexdigest(),
            'truth_bytes':truth.nbytes, 'packed_truth_bytes':packed.nbytes,
            'packed_sha256':hashlib.sha256(packed.tobytes()).hexdigest(), 'model_math_build_seconds':build,
            'compact_build_seconds':compact_seconds, 'packed_build_seconds':pack_seconds,
            'mean_query_seconds_including_equality_check':timings,
            'ordered_chance_mass':7776**2, 'persistence_decision':'retain compact policy JSON; recompute rule tables; full truth table not persisted'}


def history_collisions(compiled):
    policy = StreamingPolicy(compiled)
    cases = corpus(compiled.game, policy, seed=460047, games=300)
    by_last, examples = {}, []
    for _, seat, history in cases:
        if not history or history in by_last.get((seat, history[-1]), {}):
            continue
        state = policy.state(history)
        if not state.supported[seat]:
            continue
        posterior = state.posterior[seat]
        group = by_last.setdefault((seat, history[-1]), {})
        for previous, old in group.items():
            distance = float(np.abs(old-posterior).sum())
            if distance < .05:
                continue
            bid = history[-1]
            truth = (compiled.guide.counts[:, bid, None]+compiled.guide.counts[None, :, bid]
                     >= compiled.game.bids[bid].quantity)
            old_ev, new_ev = 1-2*(truth @ old), 1-2*(truth @ posterior)
            hand = int(np.argmax(np.abs(new_ev-old_ev)))
            examples.append({'hero_seat':seat, 'hero_hand':compiled.game.hands[hand],
                             'histories':[[asdict(compiled.game.bids[a]) for a in h] for h in (previous, history)],
                             'posterior_l1':distance, 'challenge_evs':[float(old_ev[hand]), float(new_ev[hand])]})
            break
        group[history] = posterior.copy()
        if len(examples) == 3:
            break
    if len(examples) < 2:
        raise AssertionError('Need two supported same-last-bid collision examples')
    return examples


def main():
    base = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--snapshot', type=Path, default=base/'outputs/analysis-model.json')
    parser.add_argument('--output', type=Path, default=base/'outputs/analysis-research.json')
    parser.add_argument('--games', type=int, default=1000)
    parser.add_argument('--cold-samples', type=int, default=5)
    args = parser.parse_args()
    if min(args.games, args.cold_samples) < 1:
        parser.error('Positive sample sizes required')
    if args.worker:
        print(json.dumps(worker(args.snapshot), allow_nan=False))
        return
    start, cpu = time.perf_counter(), time.process_time()
    source = json.loads((base/'outputs/policy-space.json').read_text())
    snapshot = export_snapshot(source)
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot.write_bytes(snapshot)
    report = {'source_base':subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'source_sha256_lf':{p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                  for p in sorted(base.rglob('*.py'))},
              'python':platform.python_version(), 'platform':platform.platform(), 'processor':platform.processor(),
              'seed':460046, 'games_per_seat':args.games, 'snapshot_bytes':len(snapshot),
              'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(), 'precompute':precompute(),
              'toy_abstractions':toy_abstractions(), 'cold_workers':[], 'full_game':[], 'status':'running'}
    def save():
        report['wall_seconds'], report['parent_cpu_seconds'] = time.perf_counter()-start, time.process_time()-cpu
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    try:
        for _ in range(args.cold_samples):
            t = time.perf_counter()
            output = subprocess.check_output([sys.executable, __file__, '--worker', '--snapshot', str(args.snapshot)], text=True)
            item = json.loads(output)
            item['process_wall_seconds'] = time.perf_counter()-t
            report['cold_workers'].append(item)
        for generation in (0, 1, 2):
            game, guide, target, model_id = load_snapshot(snapshot, generation)
            compiled = CompiledPopulation(game, guide, target)
            if generation == 2:
                report['same_last_bid_examples'] = history_collisions(compiled)
            for label, remember in (('exact_stream', None), ('last_bid', 1), ('last_two', 2)):
                policy = StreamingPolicy(compiled, remember)
                row = {'generation':generation, 'model_id':model_id, 'representation':label, 'seats':[]}
                for seat in (0, 1):
                    t = time.perf_counter()
                    search = ResponseSearch(game, guide, BehavioralModel(policy), seat, depth=1, max_nodes=32)
                    bound = search.solve()
                    policies = (search.policy, policy.policy) if seat == 0 else (policy.policy, search.policy)
                    replay = matches(game, policies, 460046+generation*20+seat, args.games)
                    row['seats'].append({**bound, 'held_out_replay':replay, 'wall_seconds':time.perf_counter()-t})
                row['nashconv_lower'] = max(0., sum(s['lower'] for s in row['seats']))
                row['nashconv_upper'] = min(2., sum(s['upper'] for s in row['seats']))
                row['cached_states'] = policy.state.cache_info()._asdict()
                row['state_array_bytes'] = compiled.state().array_bytes()
                report['full_game'].append(row)
                print(json.dumps({k:row[k] for k in ('generation', 'representation', 'nashconv_lower', 'nashconv_upper')}), flush=True)
                save()
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        report['status'], report['failure'] = 'incomplete', repr(error)
        raise
    finally:
        report['parent_peak_memory'] = peak_rss()
        save()


if __name__ == '__main__':
    main()
