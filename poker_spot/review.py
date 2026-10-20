"""Transparent range hypotheses and supported river-only post-session orchestration.

This module is not imported by hosted MCP and infers no preflop/flop equilibrium.
"""
from copy import deepcopy
from decimal import Context, Decimal
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from time import perf_counter

from .core import combo_key, expand_range
from .history import HistoryError, card_text, exact_keys, reconstruct
from .validation import validate


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def hypothesis(spec, board, dead=()):
    exact_keys(spec, ('range', 'provenance'), ('updates',))
    if (not isinstance(spec['range'], str) or not 1 <= len(spec['range']) <= 8000
            or not isinstance(spec['provenance'], str) or not 1 <= len(spec['provenance']) <= 2000):
        raise HistoryError('Range hypotheses require bounded range text and explicit provenance')
    initial = expand_range(spec['range'], ())
    weights = {h: w for h, w in initial.items() if not set(h) & set(board)}
    blocked_board = len(initial)-len(weights)
    unblocked = {h: w for h, w in weights.items() if not set(h) & set(dead)}
    blocked_hero = len(weights)-len(unblocked)
    # At most 30 updates of binary64 inputs: 600 decimal digits retain their
    # finite decimal products without an ambient decimal-context dependency.
    arithmetic = Context(prec=600)
    weights = {h: Decimal(str(w)) for h, w in unblocked.items()}
    ledger, gaps = [], []
    updates = spec.get('updates', [])
    if not isinstance(updates, list) or len(updates) > 30:
        raise HistoryError('Too many range updates')
    for update in updates:
        exact_keys(update, ('event', 'likelihoods', 'provenance'))
        if any(not isinstance(update[k], str) or not 1 <= len(update[k]) <= 2000 for k in ('event', 'provenance')):
            raise HistoryError('Conditioning requires event and provenance')
        if update['likelihoods'] is None:
            gaps.append({'event': update['event'], 'reason': 'Action likelihoods unknown; no Bayesian update applied'})
            continue
        if not isinstance(update['likelihoods'], dict) or len(update['likelihoods']) > 1326:
            raise HistoryError('Likelihoods must explicitly cover all supported concrete combos')
        factors = {}
        for text, factor in update['likelihoods'].items():
            hand = combo_key(*card_text(text, 2))
            if hand in factors or isinstance(factor, bool) or not isinstance(factor, (int, float)) or not math.isfinite(factor) or not 0 <= factor <= 1:
                raise HistoryError('Invalid/duplicate action likelihood')
            factors[hand] = factor
        if set(weights)-set(factors) or set(factors)-set(initial):
            raise HistoryError('Missing action likelihood or a combo absent from the supplied prior')
        for hand in list(weights):
            weights[hand] = arithmetic.multiply(weights[hand], Decimal(str(factors[hand])))
        weights = {h: w for h, w in weights.items() if w > 0}
        ledger.append({'kind': 'supplied_likelihood_model', 'event': update['event'], 'provenance': update['provenance'],
                       'formula': 'relative posterior(h) = prior(h) * supplied P(action | h, history)',
                       'likelihoods': deepcopy(update['likelihoods'])})
    if not weights:
        raise HistoryError('Hypothesis has no supported combos after blockers/conditioning')
    largest = max(weights.values())
    dispatch = {h: float(arithmetic.divide(w, largest)) for h, w in weights.items()}
    if any(w == 0 for w in dispatch.values()):
        raise HistoryError('Relative posterior weight cannot be represented by the solver; no silent combo removal')
    text = ','.join(''.join(h)+':'+repr(w) for h, w in dispatch.items())
    return {'range': text, 'weights': {''.join(h): w for h, w in dispatch.items()},
            'posterior_weights_decimal': {''.join(h): str(w) for h, w in weights.items()},
            'dispatch_normalization': 'Each posterior weight divided by the largest surviving posterior weight',
            'provenance': spec['provenance'], 'ledger': ledger, 'gaps': gaps,
            'removed_by_board': blocked_board, 'removed_by_hero': blocked_hero,
            'range_kind': 'supplied hypothesis, not inferred equilibrium'}


def prepare_review(hand, scenarios, iterations=700):
    history = reconstruct(hand)
    if type(iterations) is not int or not 20 <= iterations <= 1500:
        raise HistoryError('River review uses existing hosted 20–1500 iteration bounds')
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 3:
        raise HistoryError('Provide one to three explicit range scenarios')
    report = {'context': 'post_session', 'status': 'not_run', 'reconstruction': history,
              'scenarios': [], 'queries': [], 'limitations': [
                  'Earlier multiway streets are reconstructed, never solved.',
                  'Arrival ranges describe river start. The observed OOP check is not node-locked.',
                  'solve_river chooses the OOP checking strategy endogenously; its conditional node is not a forced observed line.',
                  'Calling EV uses a separately supplied betting-range hypothesis, not the opponent reveal.',
                  'Action EVs use the half-starting-pot baseline; call EV uses call-minus-fold.',
                  'Reported own strategic reach is not the probability of the observed line.',
                  'Solver frequencies and EVs are computed only after successful execution; population deviations are assumptions.']}
    decision = history['decision']
    if decision['street'] != 'river' or len(decision['players']) != 2 or len(history['board']) != 5:
        report['not_run_reason'] = 'Only an actual heads-up river decision can dispatch supported tools'
        return report
    start = decision['street_start']
    if len(start['players_start']) != 2:
        report['not_run_reason'] = 'River began multiway; this adapter requires a heads-up river from its start'
        return report
    if start['pot_start'] <= 0:
        report['not_run_reason'] = 'A positive river-start pot is required by the supported tools'
        return report
    oop, ip = start['action_order']
    river_actions = hand['streets'][-1]['actions']
    simple_line = [a['action'] for a in river_actions] == ['check', 'bet'] and decision['last_bettor'] == ip
    if not decision['actor']:
        report['not_run_reason'] = 'No pending river decision; reconstruct the intended decision point'
        return report
    ids = set()
    for scenario in scenarios:
        exact_keys(scenario, ('id', 'description', 'arrival', 'betting'), ('assumptions',))
        if not isinstance(scenario['id'], str) or scenario['id'] in ids or not scenario['id']:
            raise HistoryError('Each scenario requires a unique id')
        ids.add(scenario['id'])
        if (not isinstance(scenario['description'], str) or not 1 <= len(scenario['description']) <= 4000
                or not isinstance(scenario.get('assumptions', []), list)
                or len(scenario.get('assumptions', [])) > 30
                or any(not isinstance(a, str) or not 1 <= len(a) <= 2000 for a in scenario.get('assumptions', []))
                or not isinstance(scenario['arrival'], dict) or not isinstance(scenario['betting'], dict)):
            raise HistoryError('Scenarios require a description, bounded assumption strings and explicit range objects')
        if set(scenario['arrival']) != {oop, ip}:
            raise HistoryError('Arrival ranges must name exactly the two river players')
        arrivals = {p: hypothesis(scenario['arrival'][p], history['board']) for p in (oop, ip)}
        item = {'id': scenario['id'], 'description': scenario['description'], 'arrival': arrivals,
                'assumptions': scenario.get('assumptions', []), 'betting': {}, 'status': 'not_run'}
        report['scenarios'].append(item)
        if simple_line and start['effective_stack_heads_up'] > 0:
            fraction = decision['outstanding_wager']/start['pot_start']
            args = {'board': ','.join(history['board']), 'oop_range': arrivals[oop]['range'],
                    'ip_range': arrivals[ip]['range'], 'pot': start['pot_start'],
                    'stack': start['effective_stack_heads_up'], 'bet_sizes': [fraction], 'iterations': iterations}
            if not 0 < fraction <= 3 or abs(min(args['stack'], fraction*args['pot'])-decision['to_call']) > 1e-9:
                item['solve_not_run_reason'] = 'Observed bet is outside the supported exact sizing tree'
            else:
                for p, key in ((oop, 'oop_hand'), (ip, 'ip_hand')):
                    if p in history['known_hands']:
                        own = ''.join(combo_key(*history['known_hands'][p]))
                        if own not in arrivals[p]['weights']:
                            raise HistoryError(f'{p} queried own hand is absent from its declared arrival hypothesis')
                        args[key] = own  # Display a hand row; never replace the arrival distribution.
                args = validate('solve_river', args, hosted=True)
                report['queries'].append({'scenario': scenario['id'], 'tool': 'solve_river', 'arguments': args,
                                          'status': 'not_run', 'meaning': 'Unforced river-start restricted equilibrium approximation'})
        else:
            item['solve_not_run_reason'] = 'Observed line is outside this initial check/bet orchestration adapter'
        if decision['to_call'] and decision['actor'] in history['known_hands']:
            bettor = decision['last_bettor']
            if set(scenario['betting']) != {bettor}:
                raise HistoryError('Supply a betting range for the actual last bettor; do not infer it from arrival/showdown')
            hero = history['known_hands'][decision['actor']]
            assumed = hypothesis(scenario['betting'][bettor], history['board'], hero)
            item['betting'][bettor] = assumed
            args = {'board': ','.join(history['board']), 'hero_hand': ''.join(hero),
                    'villain_betting_range': assumed['range'], 'pot': decision['pot_contested_if_call']-decision['to_call'],
                    'bet': decision['to_call']}
            args = validate('evaluate_river_call', args, hosted=True)
            report['queries'].append({'scenario': scenario['id'], 'tool': 'evaluate_river_call', 'arguments': args,
                                      'status': 'not_run', 'meaning': 'Exact incremental call EV against supplied betting hypothesis'})
    return report


def execution_label(record):
    if record.get('status') != 'computed':
        return 'not solver-verified'
    if (record.get('tool') not in ('solve_river', 'evaluate_river_call') or 'result' not in record
            or record.get('request_sha256') != digest({'tool': record['tool'], 'arguments': record.get('arguments')})
            or record.get('result_sha256') != digest(record['result']) or not record.get('source_sha256_lf')):
        raise HistoryError('Computed claim lacks matching request/result/source evidence')
    return 'computed locally; range assumptions remain unverified'


async def run_review(hand, scenarios, iterations=700):
    # No user-supplied execution result or arbitrary tool/callback can enter this path.
    from .execution import CalculationError, Runner

    report = prepare_review(hand, scenarios, iterations)
    report['runtime'] = {'python': sys.version, 'platform': platform.platform(),
                         'execution': 'Existing bounded local disposable workers; unchanged hosted settings'}
    runner = Runner()
    root = Path(__file__).resolve().parent
    sources = {p.name: hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
               for p in (root/'core.py', root/'history.py', root/'review.py', root/'execution.py', root/'validation.py')}
    for query in report['queries']:
        started = perf_counter()
        try:
            result = await runner.run(query['tool'], query['arguments'])
            if result['board'] != history_board(query['arguments']):
                raise HistoryError('Returned board differs from the request')
            if query['tool'] == 'solve_river' and result['effective_bet_amounts'] != [min(query['arguments']['stack'], query['arguments']['bet_sizes'][0]*query['arguments']['pot'])]:
                raise HistoryError('Returned betting amounts differ from the prepared exact tree')
            if query['tool'] == 'evaluate_river_call' and (result['pot_before_bet'] != query['arguments']['pot']
                    or result['villain_bet'] != query['arguments']['bet']):
                raise HistoryError('Returned call amounts differ from the request')
            query.update(status='computed', transport='local disposable worker; no hosted/ChatGPT acceptance', result=result,
                         request_sha256=digest({'tool': query['tool'], 'arguments': query['arguments']}),
                         result_sha256=digest(result), source_sha256_lf=sources)
            query['evidence_label'] = execution_label(query)
        except (CalculationError, ValueError, KeyError, TypeError) as error:
            query.update(status='failed', error={'code': getattr(error, 'code', 'RESULT_MISMATCH'), 'message': str(error)})
        query['wall_seconds'] = perf_counter()-started
    states = [q['status'] for q in report['queries']]
    report['status'] = ('computed' if states and all(s == 'computed' for s in states) else
                        'partial' if 'computed' in states else 'failed' if states else 'not_run')
    for item in report['scenarios']:
        outcomes = [q['status'] for q in report['queries'] if q['scenario'] == item['id']]
        item['status'] = ('computed' if outcomes and all(s == 'computed' for s in outcomes) else
                          'partial' if 'computed' in outcomes else 'failed' if outcomes else 'not_run')
    return report


def history_board(arguments):
    return card_text(arguments['board'], 5)


def render_markdown(report):
    history = report['reconstruction']
    lines = ['# Post-session hand review', '', f'Execution: **{report["status"]}**.', '',
             '| Street | Players at start | Pot before actions | Pot after actions |',
             '| --- | --- | --- | --- |']
    for street in history['streets']:
        lines.append(f'| {street["name"]} | {len(street["players_start"])} | {street["pot_start"]:.2f} | {street["pot_end"]:.2f} |')
    if 'not_run_reason' in report:
        lines += ['', 'Not run: '+report['not_run_reason']]
    decision = history['decision']
    if 'required_equity' in decision:
        lines += ['', f'Call {decision["to_call"]:.2f}; required equity **{100*decision["required_equity"]:.4f}%**.',
                  'Amounts are conditional on the supplied blinds, forced posts and rake model.']
    for item in report['scenarios']:
        lines += ['', f'## {item["id"]}', '', item['description'], '']
        if 'solve_not_run_reason' in item:
            lines += ['Equilibrium query not run: '+item['solve_not_run_reason'], '']
        for assumption in item['assumptions']:
            lines.append('- Assumption: '+assumption)
        for q in (q for q in report['queries'] if q['scenario'] == item['id']):
            label = execution_label(q)
            lines += ['', f'`{q["tool"]}`: {label}.']
            if q['status'] != 'computed':
                if 'error' in q:
                    lines.append('Execution error: '+json.dumps(q['error']))
                continue
            value = q['result']
            if q['tool'] == 'evaluate_river_call':
                lines.append(f'Computed equity {100*value["hero_equity_vs_assumed_betting_range"]:.4f}%; '
                             f'call-minus-fold EV {value["ev_call_minus_fold"]:.4f}; '
                             f'call/fold comparison: **{value["best_action_given_range"]}**.')
                lines.append('This depends on the supplied betting range; it is not a population estimate or full action optimization.')
            else:
                lines.append(f'Reported NashConv {value["nash_conv_chips"]:.4f} chips '
                             f'({value["nash_conv_pct_pot"]}% of pot); {value["iterations"]} iterations.')
                for side, hand in value['hands'].items():
                    for node_name, node in hand['node_strategy'].items():
                        if side == 'ip' and node_name != 'ip_after_oop_check':
                            continue
                        lines.append(f'Queried {side.upper()} {"".join(hand["combo"])} at `{node_name}`: '
                                     f'frequencies {json.dumps(node["frequency"])}; '
                                     f'EVs relative to half the starting pot {json.dumps(node["action_ev_relative_to_half_pot"])}; '
                                     f'own strategic reach {node["own_reach_probability"]}.')
                lines.append('Output rounding: frequencies/EVs 4 decimals; NashConv percent 3 decimals. The OOP check is endogenous, not locked.')
    lines += ['', '## Limitations', '']+['- '+text for text in report['limitations']]
    return '\n'.join(lines)+'\n'
