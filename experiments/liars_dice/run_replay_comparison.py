"""Compare recursive replay, exact streaming and a corpus-only likelihood cache."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from run_analysis_research import corpus, distribution, stress_history
from streaming_analysis import CompiledPopulation, StreamingPolicy, load_snapshot, source_hashes


def main():
    base = Path(__file__).parent
    snapshot = (base/'outputs/analysis-model.json').read_bytes()
    game, guide, target, model_id = load_snapshot(snapshot)
    compiled = CompiledPopulation(game, guide, target)
    policy = StreamingPolicy(compiled)
    cases = list(dict.fromkeys((seat, history) for _, seat, history in corpus(game, policy, games=20)))
    stress = stress_history(game)
    cases.append((len(stress)%2, stress))
    held_out = list(dict.fromkeys((seat, history) for _, seat, history in corpus(game, policy, seed=460048, games=20)))
    table, misses = {}, 0

    def reference(seat, history, cache=False):
        nonlocal misses
        mass = guide.prior.copy()
        for step, action in enumerate(history):
            if step%2 == seat:
                continue
            key = model_id, step%2, history[:step], action
            if cache and key in table:
                likelihood = table[key]
            else:
                if cache:
                    misses += 1
                likelihood = target.likelihood(step%2, history[:step], action)
                if cache:
                    table[key] = likelihood.copy()
            mass *= likelihood
            if mass.sum() == 0:
                return None
            mass /= mass.sum()
        return mass

    timings, outcomes = {}, {}
    # Mathematical posterior-only timing, excluding API validation/serialization.
    for mode in ('recursive', 'stream', 'build_table', 'reuse_table'):
        times, values = [], []
        for seat, history in cases:
            start = time.perf_counter()
            if mode == 'stream':
                state = compiled.state()
                for action in history:
                    state.advance(action)
                value = state.posterior[seat] if state.supported[seat] else None
            else:
                value = reference(seat, history, cache=mode in ('build_table', 'reuse_table'))
            times.append(time.perf_counter()-start)
            values.append(value)
        timings[mode] = distribution(times)
        outcomes[mode] = values
    maximum_error = 0.
    for left, right in zip(outcomes['recursive'], outcomes['stream']):
        if (left is None) != (right is None):
            raise AssertionError('Replay support mismatch')
        if left is not None:
            maximum_error = max(maximum_error, float(np.max(np.abs(left-right))))
            np.testing.assert_allclose(left, right, atol=1e-12, rtol=0)
    before_entries, before_misses = len(table), misses
    held_times = []
    for seat, history in held_out:
        start = time.perf_counter()
        actual = reference(seat, history, cache=True)
        held_times.append(time.perf_counter()-start)
        expected = reference(seat, history)
        if actual is not None:
            np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
        elif expected is not None:
            raise AssertionError('Held-out support mismatch')
    result = {'model_id':model_id, 'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
              'source_sha256_lf':{**source_hashes(), **{
                  name:hashlib.sha256((base/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                  for name in (Path(__file__).name, 'run_analysis_research.py')}},
              'corpus_cases':len(cases), 'held_out_cases':len(held_out), 'maximum_history':len(stress),
              'posterior_maximum_absolute_error':maximum_error, 'posterior_only_seconds':timings,
              'cached_likelihoods_before_holdout':before_entries, 'cached_likelihoods_after_holdout':len(table),
              'held_out_cache_misses':misses-before_misses, 'held_out_seconds':distribution(held_times),
              'cached_vector_bytes_after_holdout':sum(v.nbytes for v in table.values()),
              'cache_key':'model_id, actor, full public prefix, observed action',
              'miss_behavior':'compute exact recursive likelihood and add it; no approximate substitution',
              'caveat':'corpus-only unbounded comparison cache; production prototype instead bounds full-query memoization; recursive model caches warm across passes'}
    (base/'outputs/replay-comparison.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
