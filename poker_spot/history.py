"""Post-session accounting and conservative text normalization, not earlier-street solving."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import re

from .core import cards

POSITIONS = ('UTG', 'UTG+1', 'UTG+2', 'BTN', 'SB', 'BB')
ALIASES = {'HJ': 'UTG+1', 'CO': 'UTG+2'}
STREETS = ('preflop', 'flop', 'turn', 'river')


class HistoryError(ValueError):
    def __init__(self, message, code='INVALID_HISTORY'):
        self.code = code
        super().__init__(message)


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise HistoryError('Money must be a finite nonnegative amount, not a boolean')
    try:
        amount = Decimal(str(value).replace('£', '').strip())
        if not amount.is_finite() or amount < 0 or amount > Decimal('1e9') or amount*100 != (amount*100).to_integral_value():
            raise HistoryError('Money must be finite, nonnegative and exact to a penny')
        return int(amount*100)
    except InvalidOperation:
        raise HistoryError('Unrecognized money amount') from None


def chips(value):
    return value/100


def position(value):
    if not isinstance(value, str):
        raise HistoryError('Position must be a string')
    result = ALIASES.get(value, value)
    if result not in POSITIONS:
        raise HistoryError(f'Unknown position: {value}')
    return result


def card_text(value, count):
    if isinstance(value, (list, tuple)):
        if not all(isinstance(c, str) for c in value):
            raise HistoryError('Cards must be strings')
        value = ','.join(value)
    text = str(value).translate(str.maketrans({'♣': 'c', '♦': 'd', '♥': 'h', '♠': 's', '\ufe0f': None}))
    text = re.sub(r'10(?=[cdhs])', 'T', text)
    found = re.findall(r'[2-9TJQKA][cdhs]', text)
    if re.sub(r'[2-9TJQKA][cdhs]|[,\s]', '', text):
        raise HistoryError('Unrecognized card text')
    try:
        return list(cards(found, count))
    except ValueError as error:
        raise HistoryError(str(error)) from None


def exact_keys(value, required, optional=()):
    if not isinstance(value, dict):
        raise HistoryError('Expected an object')
    missing = set(required)-set(value)
    if missing:
        raise HistoryError('Missing details: '+', '.join(sorted(missing)), 'MISSING_DETAIL')
    extra = set(value)-set(required)-set(optional)
    if extra:
        raise HistoryError('Unknown fields: '+', '.join(sorted(extra)))


def revise_hand(hand, pointer, value):
    """Edit one existing JSON-pointer location; rerun reconstruction after edits."""
    result = deepcopy(hand)
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise HistoryError('Use a JSON pointer to an existing hand field')
    parts = [p.replace('~1', '/').replace('~0', '~') for p in pointer[1:].split('/')]
    target = result
    try:
        for part in parts[:-1]:
            if isinstance(target, list) and not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('Invalid list index')
            target = target[int(part)] if isinstance(target, list) else target[part]
        if isinstance(target, list) and not re.fullmatch(r'0|[1-9][0-9]*', parts[-1]):
            raise ValueError('Invalid list index')
        key = int(parts[-1]) if isinstance(target, list) else parts[-1]
        target[key]  # Reject adding an unknown field or silently creating structure.
        target[key] = value
    except (KeyError, IndexError, ValueError, TypeError):
        raise HistoryError('Correction must address an existing field') from None
    return result


def _rake(spec, pot):
    exact_keys(spec, ('model',), ('amount', 'rate', 'cap', 'street', 'rounding'))
    if spec['model'] == 'none':
        exact_keys(spec, ('model',))
        return 0
    if spec['model'] == 'fixed':
        exact_keys(spec, ('model', 'amount', 'street'))
        deduction = money(spec['amount'])
    elif spec['model'] == 'percentage':
        exact_keys(spec, ('model', 'rate', 'cap', 'street', 'rounding'))
        if spec['rounding'] != 'floor_cent' or isinstance(spec['rate'], bool):
            raise HistoryError('Percentage rake requires explicit floor_cent rounding')
        try:
            rate = Decimal(str(spec['rate']))
            if not rate.is_finite() or not 0 <= rate <= 1:
                raise HistoryError('Invalid rake rate')
            deduction = min(money(spec['cap']), int((pot*rate).to_integral_value(rounding=ROUND_DOWN)))
        except InvalidOperation:
            raise HistoryError('Invalid rake rate') from None
    else:
        raise HistoryError('Unsupported rake model', 'UNSUPPORTED_RAKE')
    if spec['street'] not in STREETS[1:] or deduction > pot:
        raise HistoryError('Rake must name a postflop street and cannot exceed the pot')
    return deduction


def reconstruct(hand):
    exact_keys(hand, ('context', 'currency', 'blinds', 'players', 'forced_posts', 'dead_money', 'rake', 'streets'))
    if hand['context'] != 'post_session':
        raise HistoryError('This workflow is for completed-session study only', 'POST_SESSION_ONLY')
    if not isinstance(hand['currency'], str) or not re.fullmatch(r'[A-Z]{3}|chips', hand['currency']):
        raise HistoryError('Supply a currency code or chips')
    exact_keys(hand['blinds'], ('small', 'big'))
    small, big = (money(hand['blinds'][k]) for k in ('small', 'big'))
    if not 0 < small <= big:
        raise HistoryError('Positive small/big blinds required')
    if not isinstance(hand['players'], list) or not 2 <= len(hand['players']) <= 6:
        raise HistoryError('Provide two to six seated players, including folded blinds')
    stacks, known, active = {}, {}, []
    ledger = [{'kind': 'provided_fact', 'path': key, 'value': deepcopy(hand[key])}
              for key in ('context', 'currency', 'blinds', 'forced_posts', 'dead_money', 'rake', 'streets')]
    for row in hand['players']:
        exact_keys(row, ('position', 'stack'), ('hole_cards', 'knowledge', 'seat'))
        name = position(row['position'])
        if name in stacks or money(row['stack']) <= 0:
            raise HistoryError('Duplicate seat or nonpositive starting stack')
        stacks[name] = money(row['stack'])
        active.append(name)
        if 'hole_cards' in row:
            known[name] = card_text(row['hole_cards'], 2)
            if row.get('knowledge') not in ('hero', 'showdown'):
                raise HistoryError('Hole-card knowledge must be labelled hero or showdown')
        elif 'knowledge' in row:
            raise HistoryError('Hole-card knowledge needs explicit cards')
        ledger.append({'kind': 'provided_fact', 'path': 'players/'+name, 'value': deepcopy(row)})
    seated = [p for p in hand['players'] if 'seat' in p]
    if seated:
        if (len(seated) != len(hand['players']) or any(type(p['seat']) is not int or not 1 <= p['seat'] <= 10 for p in seated)
                or len({p['seat'] for p in seated}) != len(seated)):
            raise HistoryError('Supply unique integer physical seats for every player, or use positions alone')
        physical = [position(p['position']) for p in sorted(seated, key=lambda p: p['seat'])]
        logical = [p for p in POSITIONS if p in active]
        if not any(physical == logical[i:]+logical[:i] for i in range(len(logical))):
            raise HistoryError('Physical seat order contradicts supplied positions')
    invested = dict.fromkeys(stacks, 0)
    live = dict.fromkeys(stacks, 0)
    pot = money(hand['dead_money'])
    posts = set()
    if not isinstance(hand['forced_posts'], list) or len(hand['forced_posts']) > 24:
        raise HistoryError('Provide a complete bounded list of forced posts')
    for post in hand['forced_posts']:
        exact_keys(post, ('player', 'kind', 'amount'))
        name, kind, amount = position(post['player']), post['kind'], money(post['amount'])
        if name not in stacks or amount > stacks[name] or amount <= 0 or (name, kind) in posts:
            raise HistoryError('Invalid or duplicate forced post')
        if kind not in ('small_blind', 'big_blind', 'ante', 'dead'):
            raise HistoryError('Unknown forced-post kind')
        if kind in ('small_blind', 'big_blind'):
            expected = small if kind == 'small_blind' else big
            seats = ('SB', 'BTN') if len(stacks) == 2 and kind == 'small_blind' else ('SB',) if kind == 'small_blind' else ('BB',)
            if name not in seats:
                raise HistoryError('Blind player does not match the declared position')
            if amount != min(expected, stacks[name]) or any(k == kind for _, k in posts):
                raise HistoryError('Blind post does not match declared blind/remaining stack')
            live[name] += amount
        posts.add((name, kind))
        stacks[name] -= amount
        invested[name] += amount
        pot += amount
    if not all(any(kind == k for _, kind in posts) for k in ('small_blind', 'big_blind')):
        raise HistoryError('Both blind posts must be explicit', 'MISSING_DETAIL')
    _rake(hand['rake'], 10**12)  # Validate the explicit model before any later deduction.
    if not isinstance(hand['streets'], list) or not 1 <= len(hand['streets']) <= 4:
        raise HistoryError('Provide one to four consecutive streets')
    board, rows, events = [], [], []
    decision = None
    for index, street in enumerate(hand['streets']):
        exact_keys(street, ('name', 'cards', 'actions'))
        if street['name'] != STREETS[index] or len(active) < 2:
            raise HistoryError('Streets must be consecutive with an unresolved pot')
        incoming = card_text(street['cards'], (0, 3, 1, 1)[index])
        board.extend(incoming)
        all_cards = board+[c for pair in known.values() for c in pair]
        if len(set(all_cards)) != len(all_cards):
            raise HistoryError('Board and supplied hole cards overlap')
        if index:
            live = dict.fromkeys(stacks, 0)
        if hand['rake'].get('street') == street['name']:
            deduction = _rake(hand['rake'], pot)
            pot -= deduction
            events.append({'kind': 'computed_reconstruction', 'event': 'rake', 'street': street['name'], 'amount': chips(deduction)})
        order = list(POSITIONS) if index == 0 else list(POSITIONS[4:]+POSITIONS[:4])
        if len(stacks) == 2 and index:
            order = ['BB']+[p for p in order if p != 'BB']
        pending = [p for p in order if p in active and stacks[p] > 0]
        if index and len(pending) < 2:
            pending = []  # All-in runout: one remaining stack cannot bet into an empty side pot.
        current, increment = (big if index == 0 else 0), big
        acted_at = {}
        start = {'name': street['name'], 'board': list(board), 'pot_start': chips(pot),
                 'action_order': [p for p in order if p in active],
                 'players_start': list(active), 'stacks_start': {p: chips(stacks[p]) for p in active},
                 'effective_stack_heads_up': chips(min(stacks[p] for p in active)) if len(active) == 2 else None}
        start['spr_heads_up'] = start['effective_stack_heads_up']/chips(pot) if len(active) == 2 and pot else None
        actions = street['actions']
        if not isinstance(actions, list) or len(actions) > 100:
            raise HistoryError('Street actions must be a bounded list')
        last_bettor = None
        for number, action in enumerate(actions):
            exact_keys(action, ('player', 'action'), ('amount', 'to', 'all_in'))
            actor, verb = position(action['player']), action['action']
            if not pending or actor != pending[0]:
                raise HistoryError(f'Out-of-order action: expected {pending[0] if pending else "round end"}, got {actor}')
            if 'all_in' in action and type(action['all_in']) is not bool:
                raise HistoryError('all_in must be boolean')
            owed = max(0, current-live[actor])
            paid = 0
            if verb in ('fold', 'check'):
                if any(k in action for k in ('amount', 'to', 'all_in')) or (verb == 'check' and owed):
                    raise HistoryError('Cannot check facing a bet, or attach amounts to fold/check')
                if verb == 'fold':
                    active.remove(actor)
            elif verb == 'call':
                paid = min(owed, stacks[actor])
                if not owed or ('amount' in action and 'to' in action):
                    raise HistoryError('Invalid call or ambiguous amount semantics')
                expected = money(action['amount']) if 'amount' in action else money(action['to'])-live[actor] if 'to' in action else paid
                if expected != paid:
                    raise HistoryError('Call amount does not match the amount owed / remaining stack')
            elif verb in ('bet', 'raise'):
                if verb == 'bet':
                    if current or 'amount' not in action or 'to' in action:
                        raise HistoryError('Opening bet requires an incremental amount and no outstanding bet')
                    target = live[actor]+money(action['amount'])
                else:
                    if 'to' not in action or 'amount' in action:
                        raise HistoryError('Raise requires an explicit total-to amount', 'AMBIGUOUS_AMOUNT')
                    if current <= 0:
                        raise HistoryError('Cannot raise without an outstanding wager; use bet')
                    if actor in acted_at and current-acted_at[actor] < increment:
                        raise HistoryError('A short all-in has not reopened raising for this player')
                    target = money(action['to'])
                paid = target-live[actor]
                increase = target-current
                if paid <= 0 or paid > stacks[actor] or increase <= 0:
                    raise HistoryError('Bet/raise exceeds stack or fails to increase the wager')
                if increase < increment and paid != stacks[actor]:
                    raise HistoryError('Under-minimum raise requires an actual all-in')
                if increase >= increment:
                    increment = increase
                current, last_bettor = target, actor
            else:
                raise HistoryError('Unknown betting action')
            if paid > stacks[actor] or ('all_in' in action and action['all_in'] != (paid == stacks[actor])):
                raise HistoryError('All-in declaration disagrees with remaining stack')
            stacks[actor] -= paid
            invested[actor] += paid
            live[actor] += paid
            pot += paid
            if verb == 'check':
                acted_at.pop(actor, None)
            else:
                acted_at[actor] = current
            events.append({'kind': 'computed_reconstruction', 'street': street['name'], 'index': number,
                           'player': actor, 'action': verb, 'paid': chips(paid), 'total_street': chips(live[actor]),
                           'pot_after': chips(pot), 'stack_after': chips(stacks[actor])})
            if verb in ('bet', 'raise'):
                cycle = order[order.index(actor)+1:]+order[:order.index(actor)]
                pending = [p for p in cycle if p in active and stacks[p] > 0 and live[p] < current]
            else:
                pending = pending[1:]
            pending = [p for p in pending if p in active and stacks[p] > 0] if len(active) > 1 else []
        if pending and index != len(hand['streets'])-1:
            raise HistoryError('A street cannot advance while a player still owes an action')
        if not pending:
            # Uncalled chips never belong to the contested pot, including short all-in calls.
            ordered = sorted(live, key=live.get, reverse=True)
            refund = live[ordered[0]]-live[ordered[1]]
            if refund:
                winner = ordered[0]
                stacks[winner] += refund
                invested[winner] -= refund
                live[winner] -= refund
                pot -= refund
                events.append({'kind': 'computed_reconstruction', 'event': 'uncalled_refund', 'player': winner, 'amount': chips(refund)})
        start.update(pot_end=chips(pot), players_end=list(active), pending=list(pending),
                     contributions={p: chips(live[p]) for p in live}, stacks_end={p: chips(stacks[p]) for p in stacks})
        rows.append(start)
        outstanding = max(0, current-live[pending[0]]) if pending else 0
        call = min(outstanding, stacks[pending[0]]) if pending else 0
        excess = outstanding-call if len(active) == 2 else 0
        decision = {'street': street['name'], 'actor': pending[0] if pending else None,
                    'players': list(active), 'last_bettor': last_bettor,
                    'outstanding_wager': chips(outstanding), 'to_call': chips(call),
                    'uncalled_excess_if_call': chips(excess), 'pot_contested_if_call': chips(pot-excess),
                    'pot_current': chips(pot), 'street_start': deepcopy(start)}
    levels = sorted(set(invested.values())-{0})
    layers, lower = [], 0
    for upper in levels:
        payers = [p for p in invested if invested[p] >= upper]
        layers.append({'gross_amount': chips((upper-lower)*len(payers)), 'eligible': [p for p in payers if p in active]})
        lower = upper
    if decision['to_call'] and len(active) == 2:
        decision['required_equity'] = decision['to_call']/(decision['pot_contested_if_call']+decision['to_call'])
    return {'status': 'reconstructed', 'context': 'post_session', 'currency': hand['currency'], 'board': board,
            'streets': rows, 'decision': decision, 'pot_layers_gross_before_rake': layers,
            'ledger': ledger+events, 'known_hands': known, 'input': deepcopy(hand),
            'limitations': ['Earlier multiway streets are accounted for, not solved.',
                            'Pot layers exclude unassigned dead_money; rake is deducted only at its declared street.',
                            'Hole-card reveals are facts, not an inferred opponent range.']}


def parse_history(text):
    """Recognize explicit position/action prose; preserve every unrecognized line."""
    if not isinstance(text, str) or len(text) > 65536:
        raise HistoryError('History text must be at most 65,536 characters')
    result = {'context': None, 'currency': None, 'blinds': {}, 'players': [],
              'forced_posts': [], 'dead_money': None, 'rake': None, 'streets': []}
    issues, holes, stack, headers = [], {}, None, set()
    for line in (p.strip() for p in text.splitlines() if p.strip()):
        header = re.match(r'(Context|Currency|Blinds|Stacks|Players|Rake|Dead money):', line, re.I)
        if header:
            key = header[1].lower()
            if key in headers:
                issues.append('Repeated metadata requires clarification: '+line)
            headers.add(key)
        if re.fullmatch(r'(?:Context:\s*)?post[- ]session', line, re.I):
            result['context'] = 'post_session'
        elif match := re.fullmatch(r'Currency:\s*([A-Z]{3}|chips)', line):
            result['currency'] = match[1]
        elif match := re.fullmatch(r'Blinds:\s*£?([\d.]+)\s*/\s*£?([\d.]+)', line, re.I):
            result['blinds'] = dict(zip(('small', 'big'), match.groups()))
        elif match := re.fullmatch(r'Stacks:\s*(£?[\d.]+|[\d.]+bb)\s*(?:effective|each)?', line, re.I):
            stack = match[1]
        elif match := re.fullmatch(r'Players:\s*(.+)', line, re.I):
            result['players'] = [{'position': position(p.strip())} for p in match[1].split(',')]
        elif match := re.fullmatch(r'(Known|Revealed)\s+(\S+):\s*(.+)', line, re.I):
            if position(match[2]) in holes:
                issues.append('Repeated hole-card claim requires clarification: '+line)
            holes[position(match[2])] = {'hole_cards': card_text(match[3], 2), 'knowledge': 'hero' if match[1].lower() == 'known' else 'showdown'}
        elif re.fullmatch(r'Rake:\s*none', line, re.I):
            result['rake'] = {'model': 'none'}
        elif match := re.fullmatch(r'Dead money:\s*(£?[\d.]+)', line, re.I):
            result['dead_money'] = match[1]
        elif match := re.fullmatch(r'(Preflop|Flop|Turn|River)\s*([^:]*):\s*(.*)', line, re.I):
            name = match[1].lower()
            street = {'name': name, 'cards': card_text(match[2], (0, 3, 1, 1)[STREETS.index(name)]), 'actions': []}
            for phrase in (p.strip().rstrip('.') for p in match[3].split(';') if p.strip()):
                action = re.fullmatch(r'(UTG(?:\+[12])?|HJ|CO|BTN|SB|BB)\s+(checks|folds|calls|bets|raises|opens|3-bets)(?:\s+(to))?(?:\s+(£?[\d.]+))?(?:\s+(all-in))?', phrase)
                if not action:
                    issues.append('Unrecognized or ambiguous action: '+phrase)
                    continue
                player, verb, to, amount, allin = action.groups()
                verb = {'checks': 'check', 'folds': 'fold', 'calls': 'call', 'bets': 'bet', 'raises': 'raise', 'opens': 'raise', '3-bets': 'raise'}[verb]
                row = {'player': position(player), 'action': verb}
                if verb == 'raise' and (not to or amount is None):
                    issues.append('Raise needs explicit total-to amount: '+phrase)
                if amount is not None:
                    row['to' if to else 'amount'] = amount
                if allin:
                    row['all_in'] = True
                street['actions'].append(row)
            result['streets'].append(street)
        else:
            issues.append('Unrecognized line (not ignored): '+line)
    for field in ('context', 'currency', 'dead_money', 'rake'):
        if result[field] is None:
            issues.append('Missing '+field)
    if set(result['blinds']) != {'small', 'big'}:
        issues.append('Missing blinds')
    if not result['players'] or stack is None:
        issues.append('Missing seated players or stacks')
    if set(holes)-{p['position'] for p in result['players']}:
        issues.append('Hole cards refer to a player absent from the seated-player list')
    if stack is not None and result['blinds']:
        try:
            amount = Decimal(stack[:-2])*Decimal(result['blinds']['big']) if stack.lower().endswith('bb') else Decimal(stack.replace('£', ''))
        except (InvalidOperation, KeyError):
            raise HistoryError('Invalid or incomplete stack/blind amount') from None
        for player in result['players']:
            player.update(stack=str(amount), **holes.get(player['position'], {}))
    for name, kind, key in (('SB', 'small_blind', 'small'), ('BB', 'big_blind', 'big')):
        if name in [p['position'] for p in result['players']] and key in result['blinds']:
            result['forced_posts'].append({'player': name, 'kind': kind, 'amount': result['blinds'][key]})
    return {'status': 'needs_clarification' if issues else 'parsed', 'issues': issues, 'hand': result,
            'source_text': text, 'scope': 'Explicit bounded prose grammar; arbitrary narratives require confirmation or structured corrections.'}
