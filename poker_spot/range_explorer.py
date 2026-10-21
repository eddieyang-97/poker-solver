"""Bounded joint range conditioning under supplied action models; no solver dispatch."""
from copy import deepcopy
from decimal import Context, Decimal, InvalidOperation, localcontext
import itertools

from .core import combo_key, expand_range
from .history import HistoryError, STREETS, card_text, exact_keys, position, reconstruct
from .review import digest

ARITHMETIC = Context(prec=600)
ROW_ARITHMETIC = Context(prec=1200)


def replay(hand):
    # The accountant's Decimal money/rake arithmetic must not inherit caller precision.
    with localcontext(ARITHMETIC):
        return reconstruct(hand)


def total(values):
    result = Decimal(0)
    for value in values:
        result = ARITHMETIC.add(result, value)
    return result


def text(value, name, limit=2000):
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise HistoryError(f'{name} must be a bounded nonempty string')
    return value


def probability(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float, str))
            or len(str(value)) > 350):
        raise HistoryError('Action frequencies require bounded decimal numbers/strings')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise HistoryError('Invalid action frequency') from None
    if not result.is_finite() or not 0 <= result <= 1 or result and result.adjusted() < -300:
        raise HistoryError('Action frequencies must be zero or between 1e-300 and 1')
    return result if result else Decimal(0)


def prefix(hand, through):
    exact_keys(through, ('street', 'index'))
    if through['street'] not in STREETS or type(through['index']) is not int or through['index'] < 0:
        raise HistoryError('through needs an actual street and zero-based observed action index')
    stop, index = STREETS.index(through['street']), through['index']
    if (not isinstance(hand, dict) or not isinstance(hand.get('streets'), list) or stop >= len(hand['streets'])
            or not isinstance(hand['streets'][stop], dict) or not isinstance(hand['streets'][stop].get('actions'), list)
            or index >= len(hand['streets'][stop]['actions'])):
        raise HistoryError('Selected action is absent from the history')
    cut = deepcopy(hand)
    cut['streets'] = cut['streets'][:stop+1]
    cut['streets'][-1]['actions'] = cut['streets'][-1]['actions'][:index+1]
    if not isinstance(cut.get('players'), list) or any(not isinstance(p, dict) for p in cut['players']):
        raise HistoryError('Supply seated players')
    for player in cut['players']:
        player.pop('hole_cards', None)
        player.pop('knowledge', None)
    # A rake deduction on a later street is not part of the selected prefix.
    if isinstance(cut.get('rake'), dict) and cut['rake'].get('street') in STREETS[stop+1:]:
        cut['rake'] = {'model': 'none'}
    replay(cut)
    # Canonicalize every identity once, before model binding, inference and reporting.
    for player in cut['players']:
        player['position'] = position(player['position'])
    for post in cut['forced_posts']:
        post['player'] = position(post['player'])
    for street in cut['streets']:
        for action in street['actions']:
            action['player'] = position(action['player'])
    return cut


def action_event(hand, street_index, index, alternative=None):
    cut = deepcopy(hand)
    cut['streets'] = cut['streets'][:street_index+1]
    cut['streets'][-1]['actions'] = cut['streets'][-1]['actions'][:index+1]
    if alternative is not None:
        cut['streets'][-1]['actions'][-1] = alternative
    result = replay(cut)
    row = next(r for r in result['ledger'] if r.get('street') == STREETS[street_index] and r.get('index') == index)
    return tuple(row[k] for k in ('player', 'action', 'paid', 'total_street'))


def models_for(profile, hand, priors):
    exact_keys(profile, ('id', 'description', 'models'))
    text(profile['id'], 'Profile id', 80)
    text(profile['description'], 'Profile description')
    if not isinstance(profile['models'], list) or len(profile['models']) > 24:
        raise HistoryError('Supply at most 24 action models per profile')
    compiled = {}
    for model in profile['models']:
        exact_keys(model, ('street', 'index', 'provenance', 'alternatives', 'frequencies'))
        text(model['provenance'], 'Model provenance')
        prefix(hand, {k: model[k] for k in ('street', 'index')})
        street_index = STREETS.index(model['street'])
        key = model['street'], model['index']
        if key in compiled:
            raise HistoryError('Duplicate action model')
        observed = hand['streets'][street_index]['actions'][model['index']]
        actor = observed['player']
        if actor not in priors:
            raise HistoryError('Action model actor needs a declared prior')
        if not isinstance(model['alternatives'], list) or not 1 <= len(model['alternatives']) <= 6:
            raise HistoryError('Supply one to six explicit legal alternatives')
        actual = action_event(hand, street_index, model['index'])
        identities, fingerprints, match = set(), set(), []
        for alternative in model['alternatives']:
            exact_keys(alternative, ('id', 'action'), ('amount', 'to', 'all_in'))
            identity = text(alternative['id'], 'Action id', 80)
            action = {k: v for k, v in alternative.items() if k != 'id'} | {'player': actor}
            fingerprint = action_event(hand, street_index, model['index'], action)
            if identity in identities or fingerprint in fingerprints:
                raise HistoryError('Duplicate action id or equivalent alternative')
            identities.add(identity)
            fingerprints.add(fingerprint)
            if fingerprint == actual:
                match.append(identity)
        if len(match) != 1:
            raise HistoryError('Exactly one alternative must match the actual observed action and amount')
        if not isinstance(model['frequencies'], dict):
            raise HistoryError('Supply complete concrete-combo frequency rows')
        factors = {}
        for combo, row in model['frequencies'].items():
            h = combo_key(*card_text(combo, 2))
            if h in factors or not isinstance(row, dict) or set(row) != identities:
                raise HistoryError('Duplicate combo or incomplete action-frequency row')
            probabilities = {k: probability(v) for k, v in row.items()}
            row_sum = Decimal(0)
            for value in probabilities.values():
                row_sum = ROW_ARITHMETIC.add(row_sum, value)
            if row_sum != 1:
                raise HistoryError('Each action-frequency row must sum to exactly 1 in decimal; no silent normalization')
            factors[h] = probabilities[match[0]]
        if set(factors) != set(priors[actor]):
            raise HistoryError('Frequency rows must exactly cover the actor original positive prior')
        compiled[key] = {'factors': factors, 'observed_id': match[0], 'provenance': model['provenance']}
    return compiled


def compatible_deals(priors):
    for deal in itertools.product(*priors.values()):
        cs = [c for h in deal for c in h]
        if len(set(cs)) != len(cs):
            continue
        weight = Decimal(1)
        for h, weights in zip(deal, priors.values(), strict=True):
            weight = ARITHMETIC.multiply(weight, weights[h])
        yield deal, weight


def snapshot(deals, players, priors, pair):
    mass = total(w for _, w in deals)
    marginal = {p: dict.fromkeys(priors[p], Decimal(0)) for p in players}
    joint = {}
    pair_indexes = [players.index(p) for p in pair]
    for deal, w in deals:
        for player, h in zip(players, deal, strict=True):
            marginal[player][h] = ARITHMETIC.add(marginal[player][h], w)
        h = tuple(deal[i] for i in pair_indexes)
        joint[h] = ARITHMETIC.add(joint.get(h, Decimal(0)), w)
    marginal = {p: {h: ARITHMETIC.divide(w, mass) for h, w in rows.items()} for p, rows in marginal.items()}
    joint = {h: ARITHMETIC.divide(w, mass) for h, w in joint.items()}
    product = {(a, b): ARITHMETIC.multiply(wa, wb) for a, wa in marginal[pair[0]].items()
               for b, wb in marginal[pair[1]].items() if not set(a) & set(b)}
    product_mass = total(product.values())
    tv = ARITHMETIC.divide(total(ARITHMETIC.subtract(joint.get(h, Decimal(0)), ARITHMETIC.divide(w, product_mass)).copy_abs()
                                   for h, w in product.items()), Decimal(2))
    return {'compatible_deals': len(deals), 'relative_mass_decimal': str(mass),
            'marginals_decimal': {p: {''.join(h): str(w) for h, w in rows.items()} for p, rows in marginal.items()},
            'target_pair_joint_decimal': {'|'.join(''.join(h) for h in hs): str(w) for hs, w in joint.items()},
            'independent_marginal_export_tv_decimal': str(tv),
            'solver_export': 'not_run: do not substitute posterior marginals for independent arrival weights'}


def explore_profile(hand, priors, pair, profile):
    compiled = models_for(profile, hand, priors)
    players = list(priors)
    deals = list(compatible_deals(priors))
    if not deals:
        raise HistoryError('Priors have no mutually compatible private deal')
    trace, gaps = [], []
    out = {'id': profile['id'], 'description': profile['description'], 'trace': trace, 'gaps': gaps,
           'status': 'computed', 'initial_compatible_deals': len(deals)}
    for street in hand['streets']:
        if street['cards']:
            incoming = card_text(street['cards'], (0, 3, 1, 1)[STREETS.index(street['name'])])
            board = set(incoming)
            before = total(w for _, w in deals)
            deals = [(deal, w) for deal, w in deals if not board.intersection(c for h in deal for c in h)]
            after = total(w for _, w in deals)
            trace.append({'kind': 'public_cards', 'street': street['name'], 'cards': incoming,
                          'surviving_private_deal_mass_ratio_decimal': str(ARITHMETIC.divide(after, before)),
                          'compatible_deals': len(deals), 'meaning': 'Card-removal survival, not the probability of this exact board'})
            if not deals:
                out.update(status='impossible_observation', reason='Public board has zero support under supplied priors')
                return out
        for index, action in enumerate(street['actions']):
            key = street['name'], index
            event = {'street': key[0], 'index': index, 'player': action['player'], 'action': deepcopy(action)}
            if key not in compiled:
                gaps.append(event | {'reason': 'Unknown action likelihood; no update',
                                     'modeled_player': action['player'] in priors})
                continue
            model = compiled[key]
            actor = players.index(action['player'])
            before = total(w for _, w in deals)
            deals = [(deal, ARITHMETIC.multiply(w, model['factors'][deal[actor]])) for deal, w in deals]
            deals = [(deal, w) for deal, w in deals if w > 0]
            after = total(w for _, w in deals)
            trace.append(event | {'kind': 'supplied_action_model', 'provenance': model['provenance'],
                                  'observed_id': model['observed_id'], 'compatible_deals': len(deals),
                                  'conditional_action_probability_decimal': str(ARITHMETIC.divide(after, before))})
            if not deals:
                out.update(status='impossible_observation', reason='Observed action has zero probability under this supplied model')
                return out
    out.update(snapshot(deals, players, priors, pair))
    return out


def explore(hand, spec):
    exact_keys(spec, ('through', 'priors', 'target_pair', 'profiles'))
    hand = prefix(hand, spec['through'])
    if not isinstance(spec['priors'], dict) or not 2 <= len(spec['priors']) <= 3:
        raise HistoryError('Model two or three seated participants')
    spec = deepcopy(spec)
    canonical_priors = {}
    for player, prior in spec['priors'].items():
        name = position(player)
        if name in canonical_priors:
            raise HistoryError('Duplicate prior position after alias normalization')
        canonical_priors[name] = prior
    spec['priors'] = canonical_priors
    if isinstance(spec['target_pair'], list):
        spec['target_pair'] = [position(p) for p in spec['target_pair']]
    seated = {p['position'] for p in hand['players']}
    if set(spec['priors'])-seated:
        raise HistoryError('Prior player is absent from the hand')
    priors = {}
    for player, prior in spec['priors'].items():
        exact_keys(prior, ('range', 'provenance'))
        text(prior['provenance'], 'Prior provenance')
        prior_text = text(prior['range'], 'Prior range', 8000)
        for token in prior_text.split(','):
            _, separator, raw = token.partition(':')
            if separator:
                try:
                    weight = Decimal(raw.strip())
                except InvalidOperation:
                    raise HistoryError('Invalid prior weight') from None
                if not weight.is_finite() or not 0 <= weight <= 1 or weight > 0 and float(weight) == 0:
                    raise HistoryError('Prior weights must be in [0,1] and positive support must survive binary64 parsing')
        weights = expand_range(prior_text, ())
        if len(weights) > 24:
            raise HistoryError('Each prior is limited to 24 positive expanded combos before board removal')
        priors[player] = {h: Decimal(str(w)) for h, w in weights.items()}
    pair = spec['target_pair']
    if (not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(p, str) and p in priors for p in pair)
            or pair[0] == pair[1]):
        raise HistoryError('target_pair must identify two distinct modeled players')
    profiles = spec['profiles']
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 3:
        raise HistoryError('Supply one to three named profiles')
    results = [explore_profile(hand, priors, pair, p) for p in profiles]
    if len({p['id'] for p in results}) != len(results):
        raise HistoryError('Duplicate profile ids')
    base = results[0]
    for result in results:
        if result['status'] != 'computed' or base['status'] != 'computed':
            result['sensitivity'] = {'status': 'not_comparable', 'reason': 'Baseline or comparison line has zero modeled support'}
            continue
        differences = {}
        for player, rows in result['marginals_decimal'].items():
            delta = {h: ARITHMETIC.subtract(Decimal(w), Decimal(base['marginals_decimal'][player][h])) for h, w in rows.items()}
            differences[player] = {'total_variation_decimal': str(ARITHMETIC.divide(total(v.copy_abs() for v in delta.values()), Decimal(2))),
                                   'delta_decimal': {h: str(v) for h, v in delta.items()}}
        result['sensitivity'] = {'status': 'computed', 'baseline': base['id'], 'players': differences}
    states = [r['status'] for r in results]
    return {'context': 'post_session', 'status': 'computed' if all(s == 'computed' for s in states) else
            'partial' if 'computed' in states else 'impossible_observation',
            'computation': 'Joint range conditioning under explicitly supplied action-frequency assumptions',
            'solver_execution': 'not_run', 'request_sha256': digest({'hand_prefix_without_hole_cards': hand, 'models': spec}),
            'through': deepcopy(spec['through']), 'hand_prefix': hand, 'input_models': deepcopy(spec),
            'board': replay(hand)['board'], 'priors': deepcopy(spec['priors']),
            'modeled_players': list(priors), 'omitted_players': sorted(seated-set(priors)), 'target_pair': pair,
            'profiles': results, 'limits': {'players': 3, 'combos_per_player': 24, 'candidate_deals': 24**3,
                                           'profiles': 3, 'models_per_profile': 24},
            'limitations': ['No strategy, equilibrium frequencies or action EVs are computed.',
                            'All priors/action frequencies are supplied assumptions, not calibrated population estimates.',
                            'Supplied finite alternatives assign zero modeled probability to omitted legal actions/sizes.',
                            'All hole-card claims and future public actions/cards are excluded from inference.',
                            'Omitted players latent cards and action-selection effects are unmodeled.',
                            'Modeled folded players retain their latent cards and joint correlations.',
                            'Unknown likelihoods are gaps, not assumed unit action probabilities.',
                            'Decimal probabilities use 600-digit sums/division; no symbolic-exactness claim.',
                            'Posterior marginals are not an automatic valid solver input; no solver or MCP dispatch.']}


def render_markdown(report):
    lines = ['# Post-session range exploration', '', report['computation'], '',
             '**Solver execution: not run.** Probabilities below depend on supplied assumptions.', '',
             'Omitted players: '+', '.join(report['omitted_players'])+'.']
    for result in report['profiles']:
        lines += ['', '## '+result['id'], '', result['description'], '', 'Status: '+result['status']+'.']
        if result['status'] != 'computed':
            lines.append(result['reason'])
            continue
        lines += ['', '| Player | Combo | Posterior probability | Delta from first profile |', '| --- | --- | ---: | ---: |']
        for player, rows in result['marginals_decimal'].items():
            for hand, value in rows.items():
                sensitivity = result['sensitivity']
                delta = sensitivity['players'][player]['delta_decimal'][hand] if sensitivity['status'] == 'computed' else None
                lines.append(f'| {player} | {hand} | {float(value):.6g} | {float(delta):+.6g} |' if delta is not None else
                             f'| {player} | {hand} | {float(value):.6g} | not comparable |')
        lines += ['', 'Unknown-action gaps: '+str(len(result['gaps']))+'.',
                  'TV if posterior marginals were reused as independent arrivals: '+f'{float(result["independent_marginal_export_tv_decimal"]):.6g}'+'.',
                  'Full JSON retains provenance, trace, decimal probabilities, joint distribution and sensitivity.']
    lines += ['', '## Limits', '']+['- '+v for v in report['limitations']]
    return '\n'.join(lines)+'\n'
