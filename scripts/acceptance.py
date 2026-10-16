"""Reproducible post-session range sensitivity study. No external services."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poker_spot.core import RiverSolver, evaluate_river_call

BOARD = 'Ks,9s,5h,Td,Ts'
IP = ('KK:0.25,99:0.5,55:0.25,ATs:0.5,KTs:0.5,QTs:0.5,JTs:0.5,T9s:0.5,'
      'AsQs:0.75,AsJs:0.75,QsJs:0.75,Js8s:0.5,8s7s:0.5,QJs:0.5,'
      'AK:0.5,KQ:0.5,KJs:0.5,QQ:0.25,JJ:0.25,'
      'AsJh:0.5,AsQh:0.5,AsQc:0.5,AhQh:0.5,AhJh:0.5,Qh8h:0.25,Jh8h:0.25')
OOP_BASE = ('ATs:0.5,KTs:0.5,QTs:0.5,JTs:0.5,T9s:0.5,QJs:0.75,'
            'AK:0.5,KQ:0.75,KJs:0.5,QQ:0.5,JJ:0.5,88:0.25,AhQh:0.25,AhJh:0.25')
OOP = {
    'some_traps': 'KK:0.25,99:0.5,55:0.25,AsQs:0.25,QsJs:0.5,Js8s:0.5,8s7s:0.5,'+OOP_BASE,
    'more_traps': 'KK:0.75,99:1,55:0.75,AsQs:1,QsJs:1,Js8s:1,8s7s:1,'+OOP_BASE,
    'fewer_traps': 'KK:0.05,99:0.1,55:0.05,AsQs:0.05,QsJs:0.1,Js8s:0.1,8s7s:0.1,'+OOP_BASE,
}


def study():
    results = {'status': 'local study; separate user-reported ChatGPT acceptance in docs/validation.md',
               'assumptions': ('Illustrative weighted river arrival ranges. Prior streets were not supplied. '
                               'OOP check remains an endogenous action; inspect IP after that check. '
                               'No raises or rake; these are not full GTO solutions.'), 'solves': [], 'calls': []}
    for name, oop in OOP.items():
        for sizes in ([450/505], [0.33, 0.6, 450/505]):
            solver = RiverSolver(BOARD, oop, IP, 505, 450, sizes)
            out = solver.solve(1500, 'KdQd', 'AsJh')
            results['solves'].append({'scenario': name, 'inputs': {
                'board': BOARD, 'oop_range': oop, 'ip_range': IP, 'pot': 505, 'stack': 450,
                'bet_sizes': sizes, 'iterations': 1500, 'oop_hand': 'KdQd', 'ip_hand': 'AsJh'},
                'result': out})
    # Separately test a bluffcatcher against exogenous BETTING ranges, not arrival ranges.
    value = 'AsQs,QsJs,Js8s,99:0.5,55:0.25,QJs:0.5'
    for weight in (0.1, 0.5, 1.0):
        betting = value+f',AsJh:{weight},AsQh:{weight},AsQc:{weight},AhQh:{weight},AhJh:{weight}'
        args = dict(board=BOARD, hero_hand='KdQd', villain_betting_range=betting, pot=505, bet=450)
        results['calls'].append({'bluff_weight': weight, 'inputs': args, 'result': evaluate_river_call(**args)})
    return results


if __name__ == '__main__':
    result = study()
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'docs/acceptance-results.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    for row in result['solves']:
        out = row['result']
        node = out['hands']['ip']['node_strategy']['ip_after_oop_check']
        print(row['scenario'], out['effective_bet_amounts'], node, 'NashConv %', out['nash_conv_pct_pot'])
    for row in result['calls']:
        print('call bluff weight', row['bluff_weight'], row['result']['ev_call_minus_fold'])
