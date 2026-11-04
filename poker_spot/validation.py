"""Strict tool inputs shared by stdio and hosted transports."""
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .core import RiverSolver, cards, combo_key, expand_range

Text = Annotated[str, Field(min_length=1, max_length=8000)]
Amount = Annotated[float, Field(gt=0, le=1e9, allow_inf_nan=False)]


class InputError(ValueError):
    def __init__(self, field, reason, message, expected):
        super().__init__(message)
        self.details = {'field': field, 'reason': reason, 'expected': expected}


def normalized_cards(value, count, field):
    value = value.strip()
    card = r'[2-9TJQKA][cdhs]'
    if not (re.fullmatch(f'(?:{card})+', value) or
            re.fullmatch(f'{card}(?:[,\\s]+{card})*', value)):
        raise InputError(field, 'invalid_card', f'{field}: malformed card notation',
                         'Cards use rank 2-9,T,J,Q,K,A followed by suit c,d,h,s, e.g. Th')
    compact = re.sub(r'[,\s]+', '', value)
    parts = [compact[i:i+2] for i in range(0, len(compact), 2)]
    if len(parts) != count:
        raise InputError(field, 'card_count', f'{field}: expected {count} cards', f'{count} cards')
    if len(set(parts)) != count:
        raise InputError(field, 'duplicate_card', f'{field}: duplicate card', 'Distinct cards')
    return ('' if count == 2 else ',').join(parts)


class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    board: Text
    pot: Amount


class SolveInputs(Inputs):
    oop_range: Text
    ip_range: Text
    stack: Amount
    bet_sizes: list[Annotated[float, Field(gt=0, le=3, allow_inf_nan=False)]] = Field(
        default_factory=lambda: [0.5, 1.0], min_length=1, max_length=3)
    iterations: int = Field(default=700, ge=20, le=10000)
    oop_hand: Text | None = None
    ip_hand: Text | None = None


class CallInputs(Inputs):
    hero_hand: Text
    villain_betting_range: Text
    bet: Amount


def validate(name: str, arguments: dict, hosted: bool = False) -> dict:
    models = {'solve_river': SolveInputs, 'evaluate_river_call': CallInputs}
    if name not in models:
        raise ValueError('Unknown tool')
    try:
        args = models[name].model_validate(arguments).model_dump()
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_input=False)[0]
        field = '.'.join(str(part) for part in error['loc']) or 'arguments'
        raise InputError(field, 'schema', f'{field}: {error["msg"]}',
                         'See tool schema for the supported type and bounds') from None
    args['board'] = normalized_cards(args['board'], 5, 'board')
    board = cards(args['board'], 5)
    range_fields = ('oop_range', 'ip_range') if name == 'solve_river' else ('villain_betting_range',)
    ranges = {}
    for field in range_fields:
        args[field] = ','.join(filter(None, re.split(r'[,\s]+', re.sub(r'\s*:\s*', ':', args[field].strip()))))
        try:
            ranges[field] = expand_range(args[field], board)
        except ValueError as exc:
            message = str(exc)
            reason = ('invalid_weight' if 'weight' in message.lower() or 'could not convert string to float' in message
                      else 'invalid_range')
            raise InputError(field, reason, f'{field}: {message}',
                             'Explicit hands such as AA,AKs:0.5,AsJh with weights in [0,1]') from None
    hand_fields = ('oop_hand', 'ip_hand') if name == 'solve_river' else ('hero_hand',)
    for field in hand_fields:
        if args[field] is not None:
            args[field] = normalized_cards(args[field], 2, field)
            hand = cards(args[field], 2)
            if set(hand) & set(board):
                raise InputError(field, 'board_conflict', f'{field}: card is already on the board',
                                 'Two distinct cards absent from the board')
    if hosted and name == 'solve_river':
        if args['iterations'] > 1500:
            raise InputError('iterations', 'hosted_limit', 'Hosted iterations must be between 20 and 1500', '20-1500')
        n0 = len(ranges['oop_range'])
        n1 = len(ranges['ip_range'])
        if max(n0, n1) > 180 or n0*n1 > 22500:
            raise InputError('ranges', 'hosted_limit', 'Range too large', 'Maximum 180 combos per side and 22500 pairs')
    if name == 'solve_river':
        sizes = args['bet_sizes']
        if len(set(sizes)) != len(sizes) or len({min(args['stack'], b*args['pot']) for b in sizes}) != len(sizes):
            raise InputError('bet_sizes', 'invalid_sizing', 'Bet sizes must produce distinct bets',
                             '1-3 distinct pot fractions in (0,3], without duplicate capped all-ins')
        if not any(not set(a) & set(b) for a in ranges['oop_range'] for b in ranges['ip_range']):
            raise InputError('ranges', 'no_compatible_hands', 'Ranges have no compatible hole-card pairs',
                             'Ranges must contain at least one compatible pair')
        for side in ('oop', 'ip'):
            field = side+'_hand'
            if args[field] is not None:
                hand = combo_key(*cards(args[field], 2))
                if hand not in ranges[side+'_range']:
                    raise InputError(field, 'not_in_range', f'{field} is not in {side}_range',
                                     'A positive-weight combo from the corresponding range')
                other = ranges[('ip' if side == 'oop' else 'oop')+'_range']
                if not any(not set(hand) & set(combo) for combo in other):
                    raise InputError(field, 'no_compatible_hands', f'{field} blocks every opponent combo',
                                     'A hand with at least one compatible opponent combo')
    elif not any(not set(cards(args['hero_hand'], 2)) & set(combo) for combo in ranges['villain_betting_range']):
        raise InputError('villain_betting_range', 'no_compatible_hands', 'Hero blocks every villain combo',
                         'At least one positive-weight combo compatible with hero and board')
    return args


def calculate(name: str, arguments: dict) -> dict:
    from .core import evaluate_river_call

    args = validate(name, arguments)
    if name == 'evaluate_river_call':
        return evaluate_river_call(**args)
    iterations = args.pop('iterations')
    oop = args.pop('oop_hand')
    ip = args.pop('ip_hand')
    return RiverSolver(**args).solve(iterations, oop, ip)
