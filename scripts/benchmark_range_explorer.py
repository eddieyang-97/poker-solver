"""Actual local range-model sensitivity and maximum-dimension worker samples."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from poker_spot.core import DECK
from scripts.explore_ranges import execute


def maximum_case(overlap=False):
    hand = json.loads((ROOT/'examples/hand-review.json').read_text())
    hand['streets'] = [dict(name='preflop', cards=[], actions=[])]
    actions = hand['streets'][0]['actions']
    models, priors = [], {}
    players = ['UTG', 'UTG+1', 'UTG+2']
    for side, player in enumerate(players):
        pool = DECK[side*(4 if overlap else 8):side*(4 if overlap else 8)+8]
        priors[player] = {'range': ','.join(''.join(h) for h in list(itertools.combinations(pool, 2))[:24]),
                          'provenance': 'Synthetic dimension probe; not a population prior'}
    target = 2
    for i in range(24):
        player = players[i % 3]
        target += 4
        index = len(actions)
        actions.append(dict(player=player, action='raise', to=target))
        rows = {}
        for j, h in enumerate(priors[player]['range'].split(',')):
            p = '0.6' if overlap and j < 12 else '0.2'
            rows[h] = {'raise': p, 'call': '0.2' if p == '0.6' else '0.6', 'fold': '0.2'}
        models.append(dict(street='preflop', index=index, provenance='Synthetic supplied action model',
                           alternatives=[dict(id='raise', action='raise', to=target), dict(id='call', action='call'), dict(id='fold', action='fold')],
                           frequencies=rows))
        if i == 2:
            actions.extend(dict(player=p, action='fold') for p in ('BTN', 'SB', 'BB'))
    profiles = [dict(id='sample'+str(i), description='Maximum-dimension supplied model probe', models=copy.deepcopy(models)) for i in range(3)]
    return hand, dict(through=dict(street='preflop', index=len(actions)-1), priors=priors,
                      target_pair=['UTG', 'UTG+2'], profiles=profiles)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/range-explorer'))
    args = parser.parse_args()
    hand = json.loads((ROOT/'examples/hand-review.json').read_text())
    models = json.loads((ROOT/'examples/range-models.json').read_text())
    cases = [('example', hand, models)]
    cases += [('maximum_'+str(overlap).lower(), *maximum_case(overlap)) for overlap in (False, True)]
    summary = {'scope': 'Actual local supplied-model conditioning; no solver execution, calibration or hosted acceptance', 'cases': [], 'failures': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for identity, hand, spec in cases:
        result = execute(hand, spec)
        raw = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
        path = args.output.parent/(args.output.name+'.'+identity+'.json')
        path.write_bytes(raw)
        row = {'id': identity, 'status': result['status'], 'raw_report_sha256': hashlib.sha256(raw).hexdigest(),
               'path': str(path), 'output_bytes': len(raw), 'parent_wall_seconds': result.get('parent_wall_seconds'),
               'worker_metrics': result.get('worker_metrics'), 'source_sha256_lf': result.get('source_sha256_lf'),
               'profiles': [{k: p.get(k) for k in ('id', 'status', 'initial_compatible_deals', 'compatible_deals',
                                                 'marginals_decimal', 'independent_marginal_export_tv_decimal', 'sensitivity')}
                            for p in result.get('profiles', [])]}
        summary['cases'].append(row)
        if result['status'] != 'computed':
            summary['failures'].append(identity+': '+str(result.get('error', result['status'])))
        elif identity == 'example':
            # Hand-derived enumeration of this four-compatible-deal example.
            expected = [1/4, 4/7, 40/61]
            errors = [abs(float(p['marginals_decimal']['UTG']['AdAs'])-v) for p, v in zip(result['profiles'], expected, strict=True)]
            row['analytical_max_delta'] = max(errors)
            if max(errors) > 1e-14:
                summary['failures'].append('Analytical example posterior disagrees')
        elif any(len(p['trace']) != 24 for p in result['profiles']) or len(result['profiles']) != 3:
            summary['failures'].append('Maximum probe did not exercise all 24 models and three profiles')
        elif identity == 'maximum_false' and any(p['initial_compatible_deals'] != 24**3 for p in result['profiles']):
            summary['failures'].append('Maximum probe did not enumerate 24^3 compatible private deals')
        print(identity, result['status'], result.get('parent_wall_seconds'), flush=True)
    args.output.with_suffix('.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    return bool(summary['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
