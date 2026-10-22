"""Opt-in local one-raise review. Observed actions are mapped, never locked."""
from copy import deepcopy
from decimal import Context, localcontext
import hashlib
from pathlib import Path
from time import perf_counter

from .core import Node
from .history import HistoryError, exact_keys, money, position, reconstruct
from .raises import RaiseRiverSolver
from .raise_worker import accepted_configuration, canonical_digest
from .review import digest, hypothesis


def prepared_tree(solver, events):
    node, mapping = solver.root, []
    for event in events:
        if not isinstance(node, Node):
            raise HistoryError('Observed line continues past a terminal')
        kind = event['action']
        matches = [i for i, action in enumerate(solver.locations[node.name]['actions'])
                   if action['kind'] == kind and (kind in ('check', 'fold') or
                                                  action['total_to_cents'] == money(event['total_street']))]
        if len(matches) != 1:
            raise HistoryError('Observed action/amount is outside the explicitly admitted raise tree')
        i = matches[0]
        mapping.append({'node': node.name, 'player': event['player'], 'action': node.actions[i],
                        'paid_cents': money(event['paid']), 'total_to_cents': money(event['total_street'])})
        node = node.children[i]
    if not isinstance(node, Node):
        raise HistoryError('No pending river decision; select a prefix before the reviewed action')
    return {'observed_actions': mapping, 'target_node': node.name,
            'nodes': deepcopy(solver.locations)}


def prepare_raise_review(hand, scenarios, iterations=700, *, raise_to_cents=None, river_through=None):
    # Isolate all money replay as well as the independent probability arithmetic.
    with localcontext(Context(prec=600)):
        return _prepare(hand, scenarios, iterations, raise_to_cents, river_through)


def _prepare(hand, scenarios, iterations, raise_to_cents, river_through):
    hand = deepcopy(hand)
    if river_through is not None:
        if (type(river_through) is not int or river_through < 0 or len(hand['streets']) != 4
                or river_through >= len(hand['streets'][3]['actions'])):
            raise HistoryError('river_through must select an existing zero-based river action')
        hand['streets'][3]['actions'] = hand['streets'][3]['actions'][:river_through+1]
    history = reconstruct(hand)
    if type(iterations) is not int or not 20 <= iterations <= 5000:
        raise HistoryError('Local raise iterations must be between 20 and 5,000')
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 3:
        raise HistoryError('Supply one to three explicit local raise scenarios')
    report = {'context': 'post_session', 'mode': 'local_river_raises', 'status': 'not_run',
              'reconstruction': history, 'scenarios': [], 'queries': [], 'limitations': [
                  'Earlier multiway streets are reconstructed, not solved.',
                  'Observed actions are mapped, NOT LOCKED; checks and bets remain endogenous.',
                  'Conditional node EVs are against the computed opponent continuation, not a forced observed betting range.',
                  'Own strategic reach and equilibrium joint node reach are not observed-line probabilities.',
                  'EVs share the half-river-starting-pot baseline; compare actions within the same node.',
                  'Ranges and supplied likelihood updates are hypotheses, not calibrated population estimates.',
                  'No joint-range substitution, node locking, turn solving, MCP or hosted acceptance.']}
    d = history['decision']
    start = d['street_start']
    if d['street'] != 'river' or len(history['board']) != 5 or len(start['players_start']) != 2:
        report['not_run_reason'] = 'Only a river that began heads-up is supported'
        return report
    if hand['rake'] != {'model': 'none'}:
        report['not_run_reason'] = 'Local raise review currently requires explicit zero rake'
        return report
    if not d['actor']:
        report['not_run_reason'] = 'No pending river decision; select a river prefix'
        return report
    events = [e for e in history['ledger'] if e.get('street') == 'river' and 'index' in e]
    bets = [money(e['total_street']) for e in events if e['action'] == 'bet']
    observed_raises = [money(e['total_street']) for e in events if e['action'] == 'raise']
    if len(bets) != 1 or len(observed_raises) > 1:
        report['not_run_reason'] = 'Supply an observed opening bet and at most one additional raise'
        return report
    targets = deepcopy(raise_to_cents) if raise_to_cents is not None else observed_raises
    if not targets:
        report['not_run_reason'] = 'Explicit raise_to_cents are required before an observed raise'
        return report
    oop, ip = start['action_order']
    ids = set()
    for scenario in scenarios:
        exact_keys(scenario, ('id', 'description', 'arrival'), ('assumptions', 'query_hands'))
        if (not isinstance(scenario['id'], str) or not 1 <= len(scenario['id']) <= 80 or scenario['id'] in ids
                or not isinstance(scenario['description'], str) or not 1 <= len(scenario['description']) <= 4000):
            raise HistoryError('Supply unique bounded scenario ids and descriptions')
        ids.add(scenario['id'])
        assumptions = scenario.get('assumptions', [])
        if (not isinstance(assumptions, list) or len(assumptions) > 30
                or any(not isinstance(a, str) or not 1 <= len(a) <= 2000 for a in assumptions)
                or not isinstance(scenario['arrival'], dict)):
            raise HistoryError('Supply bounded assumptions and explicit arrival objects')
        arrivals = {}
        for p, value in scenario['arrival'].items():
            p = position(p)
            if p in arrivals:
                raise HistoryError('Duplicate canonical arrival position')
            arrivals[p] = hypothesis(value, history['board'])
        if set(arrivals) != {oop, ip}:
            raise HistoryError('Arrival hypotheses must name both river players')
        queries = {}
        supplied = scenario.get('query_hands', {})
        if not isinstance(supplied, dict):
            raise HistoryError('query_hands must name modeled players')
        for p, h in supplied.items():
            p = position(p)
            if p not in arrivals or p in queries:
                raise HistoryError('Invalid/duplicate query-hand position')
            queries[p] = h
        config = dict(context='post_session', board=','.join(history['board']),
                      oop_range=arrivals[oop]['range'], ip_range=arrivals[ip]['range'],
                      pot=start['pot_start'], stack=start['effective_stack_heads_up'],
                      minimum_bet=money(hand['blinds']['big'])/100, bet_amounts_cents=bets,
                      raise_to_cents=targets, iterations=iterations)
        for p, key in ((oop, 'oop_hand'), (ip, 'ip_hand')):
            if p in queries:
                config[key] = queries[p]
        item = {'id': scenario['id'], 'description': scenario['description'], 'assumptions': assumptions,
                'arrival': arrivals, 'status': 'not_run'}
        report['scenarios'].append(item)
        try:
            solver = RaiseRiverSolver(**{k: v for k, v in config.items() if k not in ('context', 'iterations', 'oop_hand', 'ip_hand')})
            tree = prepared_tree(solver, events)
            # Validate displayed hand queries without training or a fabricated result.
            from .core import cards, combo_key
            for key, hands in (('oop_hand', solver.h0), ('ip_hand', solver.h1)):
                if key in config:
                    h = combo_key(*cards(config[key], 2))
                    if h not in hands:
                        raise HistoryError('Queried own hand is absent from its supplied arrival range')
            report['queries'].append({'scenario': scenario['id'], 'tool': 'local_raise_river',
                                      'arguments': config, 'tree': tree, 'status': 'not_run',
                                      'accepted_configuration': accepted_configuration(solver, iterations, **{
                                          k: config[k] for k in ('oop_hand', 'ip_hand') if k in config}),
                                      'meaning': 'Unforced local river-start one-raise equilibrium approximation'})
        except (ValueError, TypeError) as error:
            item['not_run_reason'] = str(error)
    return report


def evidence_label(query):
    if query['status'] != 'computed':
        return 'not solver-verified'
    if (query.get('tool') != 'local_raise_river' or not query.get('source_sha256_lf')
            or query.get('request_sha256') != digest({'tool': query['tool'], 'arguments': query['arguments']})
            or query.get('result_sha256') != digest(query['result'])):
        raise HistoryError('Computed raise claim lacks request/result/source evidence')
    verify_receipt(query['receipt'], query['accepted_configuration'], query['result'])
    return 'computed locally; supplied ranges remain assumptions'


def verify_receipt(receipt, expected, result):
    if (receipt['configuration'] != expected
            or receipt['configuration_sha256'] != canonical_digest(expected)
            or receipt['result_sha256'] != canonical_digest(result)
            or result['iterations'] != expected['iterations']
            or {side: row['combo'] for side, row in result['hands'].items()}
            != {side: hand for side, hand in expected['query_hands'].items() if hand is not None}):
        raise HistoryError('Worker accepted configuration or bound result differs from prepared request')


def run_raise_review(hand, scenarios, iterations=700, **options):
    from scripts.solve_river_raises import execute

    report = prepare_raise_review(hand, scenarios, iterations, **options)
    root = Path(__file__).resolve().parents[1]
    sources = ['poker_spot/core.py', 'poker_spot/raises.py', 'poker_spot/raise_worker.py',
               'poker_spot/raise_review.py', 'poker_spot/history.py', 'poker_spot/review.py',
               'scripts/solve_river_raises.py', 'scripts/review_hand.py']
    source_hashes = {p: hashlib.sha256((root/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sources}
    for query in report['queries']:
        started = perf_counter()
        response = execute(query['arguments'])
        if response['status'] != 'computed':
            query.update(status=response['status'], error=response.get('error', {'code': 'WORKER_FAILED'}))
        else:
            try:
                value, config = response['result'], query['arguments']
                verify_receipt(response['receipt'], query['accepted_configuration'], value)
                if (value['board'] != report['reconstruction']['board'] or value['pot'] != config['pot']
                        or value['stack'] != config['stack'] or value['sizing_mode'] != 'exact_integer_cents'
                        or value['bet_amounts_cents'] != config['bet_amounts_cents']
                        or value['raise_to_cents'] != config['raise_to_cents']
                        or set(value['nodes']) != set(query['tree']['nodes'])
                        or any(any(value['nodes'][n][k] != v for k, v in row.items())
                               for n, row in query['tree']['nodes'].items())):
                    raise HistoryError('Returned board, amounts or action tree differ from request')
                query.update(status='computed', result=value, metrics=response['metrics'],
                             receipt=response['receipt'],
                             source_sha256_lf=source_hashes,
                             request_sha256=digest({'tool': query['tool'], 'arguments': config}), result_sha256=digest(value))
                query['evidence_label'] = evidence_label(query)
            except (ValueError, KeyError, TypeError) as error:
                query.update(status='failed', error={'code': 'RESULT_MISMATCH', 'message': str(error)})
        query['wall_seconds'] = perf_counter()-started
    for item in report['scenarios']:
        states = [q['status'] for q in report['queries'] if q['scenario'] == item['id']]
        item['status'] = states[0] if states else 'not_run'
    states = [s['status'] for s in report['scenarios']]
    report['status'] = ('computed' if states and all(s == 'computed' for s in states) else
                        'partial' if 'computed' in states else 'failed' if 'failed' in states else 'not_run')
    return report


def render_raise_markdown(report):
    lines = ['# Local post-session raise review', '', 'Execution: **'+report['status']+'**.',
             '', 'Observed actions are **not locked**; checks and bets remain endogenous.']
    if 'not_run_reason' in report:
        lines += ['', 'Not run: '+report['not_run_reason']]
    for item in report['scenarios']:
        lines += ['', '## '+item['id'], '', item['description']]
        if 'not_run_reason' in item:
            lines += ['Not run: '+item['not_run_reason']]
        for query in (q for q in report['queries'] if q['scenario'] == item['id']):
            lines += ['', evidence_label(query)+'. Target node: `'+query['tree']['target_node']+'`.']
            if query['status'] != 'computed':
                lines += ['Status: '+query['status']+'. '+str(query.get('error', ''))]
                continue
            result = query['result']
            lines += [f'NashConv {result["nash_conv_chips"]} chips; {result["iterations"]} iterations.']
            for side, hand in result['hands'].items():
                for node, row in hand['node_strategy'].items():
                    lines += [f'{side} {"".join(hand["combo"])} at `{node}`: frequencies {row["frequency"]}; '
                              f'conditional EVs (half-starting-pot baseline) {row["action_ev_relative_to_half_pot"]}; '
                              f'own reach {row["own_reach_probability"]}; joint node reach '
                              f'{result["nodes"][node]["joint_reach_probability"]}.']
    return '\n'.join(lines+['', '## Limitations', '']+['- '+v for v in report['limitations']])+'\n'
