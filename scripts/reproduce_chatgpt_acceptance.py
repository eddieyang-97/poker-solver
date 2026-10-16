"""Locally reproduce the user's 16 October hosted ChatGPT acceptance report.

This does not make network calls or independently establish hosted provenance.
The reported values are fixed observations, never solver calibration targets.
"""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poker_spot.core import RiverSolver, evaluate_river_call

BOARD = 'Ks,9s,5h,Td,Ts'
COMMON = ('QJo:0.25,QhJh:0.55,QcJc:0.55,QdJd:0.55,'
          'ATs:0.65,T8s:0.5,QTs:0.55,JTs:0.55,'
          'KQs:0.7,KQo:0.6,KJs:0.5,AKo:0.25,'
          '98s:0.4,A9s:0.45,88:0.4,77:0.25,'
          'AJo:0.25,AQo:0.25,87s:0.5,76s:0.5')
TRAPS = {
    'rich': '99:0.9,55:0.65,TT:0.9,KTs:0.75,T9s:0.65,AsQs:0.75,QsJs:0.8,AsJs:0.7,Js8s:0.5',
    'light': '99:0.25,55:0.2,TT:0.25,KTs:0.25,T9s:0.25,AsQs:0.25,QsJs:0.25,AsJs:0.25,Js8s:0.2',
}
IP = ('99:0.8,55:0.6,TT:0.8,KTs:0.7,T9s:0.65,'
      'AsQs:0.8,QsJs:0.85,AsJs:0.7,Js8s:0.4,'
      'QJo:0.5,QhJh:0.65,QcJc:0.65,QdJd:0.65,'
      'ATs:0.85,T8s:0.7,QTs:0.7,JTs:0.7,'
      'KQs:0.8,KQo:0.7,KJs:0.5,AKo:0.6,'
      '98s:0.4,A9s:0.45,88:0.5,77:0.3,'
      'AJo:0.8,AQo:0.7,87s:0.6,76s:0.55,65s:0.4,A7s:0.4')
# Order: check, then bets in ascending size. EVs use half-pot baseline.
REPORTED = {
    'rich_one': ([0.0003, 0.9997], [-245.7149, -244.7502], 0.0057, 36.3053,
                 [-337.7471]),
    'rich_multi': ([0.0002, 0.8957, 0.0479, 0.0562],
                   [-252.4987, -233.0067, -233.0874, -233.0757], 0.0126, 46.4037,
                   [-354.8609, -554.6244, -429.7307]),
    'light_one': ([0.0002, 0.9998], [-215.4237, -210.8820], 0.0049, -30.6844,
                  [-284.9457]),
    'light_multi': ([0.0001, 0.3039, 0.1928, 0.5032],
                    [-252.4580, -226.9145, -226.9299, -226.8926], 0.0112, -14.4852,
                    [-319.5973, -335.2454, -380.5523]),
}


def reproduce():
    evidence = {'provenance': 'User-supplied hosted ChatGPT report; independent local reproduction',
                'hosted_raw_payloads_observed_by_this_script': False,
                'solves': [], 'calls': [], 'discrepancies': []}

    def compare(label, actual, expected, tolerance=0.000051):
        if not math.isfinite(actual) or abs(actual-expected) > tolerance:
            evidence['discrepancies'].append({'field': label, 'actual': actual, 'reported': expected})

    for name, additions in TRAPS.items():
        for tree, sizes in (('one', [450/505]), ('multi', [0.33, 0.6, 450/505])):
            scenario = f'{name}_{tree}'
            inputs = dict(board=BOARD, oop_range=COMMON+','+additions, ip_range=IP,
                          pot=505, stack=450, bet_sizes=sizes, iterations=1200, ip_hand='AsJh')
            solver = RiverSolver(**{k: v for k, v in inputs.items() if k not in ('iterations', 'ip_hand')})
            result = solver.solve(inputs['iterations'], ip_hand=inputs['ip_hand'])
            nodes = result['hands']['ip']['node_strategy']
            node = nodes['ip_after_oop_check']
            frequencies, evs, gap, root_ev, call_evs = REPORTED[scenario]
            for field, observed, reported in (
                ('frequency', list(node['frequency'].values()), frequencies),
                ('action_ev', list(node['action_ev_relative_to_half_pot'].values()), evs),
                ('facing_bet_call_ev', [nodes[f'ip_facing_oop_bet_{size:g}']
                                      ['action_ev_relative_to_half_pot']['call'] for size in sizes], call_evs),
            ):
                for i, (actual, expected) in enumerate(zip(observed, reported, strict=True)):
                    compare(f'{scenario}.{field}.{i}', actual, expected)
            compare(f'{scenario}.nash_conv_chips', result['nash_conv_chips'], gap)
            compare(f'{scenario}.nash_conv_pct_pot', result['nash_conv_pct_pot'],
                    0.001 if tree == 'one' else 0.002, 0)
            compare(f'{scenario}.root_ev', result['root_ev_oop_relative_to_split_pot'], root_ev)
            for side, count in (('oop', 112), ('ip', 119)):
                compare(f'{scenario}.{side}_combos', result['range_combos'][side], count, 0)
            for node_name, strategy in nodes.items():
                compare(f'{scenario}.{node_name}.own_reach', strategy['own_reach_probability'], 1.0, 0)
            evidence['solves'].append({'scenario': scenario, 'inputs': inputs, 'result': result})
            print(scenario, node, 'NashConv', result['nash_conv_chips'], flush=True)

    for weight, expected_ev, expected_weight in ((0.1, -337.6, 6.25),
                                                (0.5, -24.2424, 8.25),
                                                (1.0, 203.4884, 10.75)):
        bluffs = ','.join(f'{hand}:{weight}' for hand in ('AsJh', 'AsQh', 'AsQc', 'AhQh', 'AhJh'))
        inputs = dict(board=BOARD, hero_hand='KdQd', pot=505, bet=450,
                      villain_betting_range='AsQs,QsJs,Js8s,99:0.5,55:0.25,QJs:0.5,'+bluffs)
        result = evaluate_river_call(**inputs)
        compare(f'call.{weight}.ev', result['ev_call_minus_fold'], expected_ev)
        compare(f'call.{weight}.equity', result['hero_equity_vs_assumed_betting_range'],
                {0.1: 0.08, 0.5: 0.303030, 1.0: 0.465116}[weight], 0.000001)
        compare(f'call.{weight}.pot_odds', result['caller_pot_odds'], 0.320285, 0.000001)
        compare(f'call.{weight}.weighted_combos', result['weighted_opponent_combos_after_blockers'], expected_weight)
        compare(f'call.{weight}.distinct_combos', result['opponent_combos_after_blockers'], 16, 0)
        evidence['calls'].append({'inputs': inputs, 'result': result})
        if weight == 0.5:
            reverse = dict(inputs, villain_betting_range='AsQs,Js8s,99:0.5,55:0.25,QJs:0.5,QsJs,'+bluffs)
            reversed_result = evaluate_river_call(**reverse)
            compare('overlap.ev', reversed_result['ev_call_minus_fold'], -48.5714)
            compare('overlap.weighted_combos', reversed_result['weighted_opponent_combos_after_blockers'], 8.75)
            evidence['overlap_diagnostic'] = {'inputs': reverse, 'result': reversed_result}
    return evidence


if __name__ == '__main__':
    evidence = reproduce()
    destination = Path('docs/chatgpt-acceptance-reproduction.json')
    destination.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    print('Discrepancies:', json.dumps(evidence['discrepancies']))
    raise SystemExit(bool(evidence['discrepancies']))
