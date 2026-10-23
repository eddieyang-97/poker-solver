"""Issue #26 bounded MCP contract; activation requires a separate app factory."""
from decimal import Context, Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import platform
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .core import cards, combo_key
from .turn import TurnSolver

NAME = 'solve_turn_v1'
VERSION = 'turn-pilot-v1'
ITERATIONS = 2000
MAX_RESULT_BYTES = 24_576
MAX_GAP_PCT = 0.5
SOURCE_FILES = ('core.py', 'turn.py', 'turn_pilot.py', 'turn_worker.py', 'execution.py')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Combo(StrictModel):
    hand: str = Field(min_length=4, max_length=5)
    weight: float = Field(ge=1e-6, le=1, allow_inf_nan=False)


class View(StrictModel):
    player: Literal['oop', 'ip']
    hand: str = Field(min_length=4, max_length=5)
    node: str = Field(default='turn', min_length=4, max_length=160)
    river_card: str | None = Field(default=None, min_length=2, max_length=2)


class TurnInputs(StrictModel):
    board: str = Field(min_length=11, max_length=20)
    oop_range: list[Combo] = Field(min_length=1, max_length=2)
    ip_range: list[Combo] = Field(min_length=1, max_length=2)
    pot_cents: int = Field(gt=0, le=1_000_000)
    stack_cents: int = Field(gt=0, le=1_000_000)
    turn_bet_sizes: list[Annotated[float, Field(gt=0, le=3, allow_inf_nan=False)]] = Field(max_length=1)
    river_bet_sizes: list[Annotated[float, Field(gt=0, le=3, allow_inf_nan=False)]] = Field(max_length=1)
    iterations: int = Field(default=ITERATIONS, ge=ITERATIONS, le=ITERATIONS)
    views: list[View] = Field(default_factory=list, max_length=4)


TOOL = {
    'name': NAME,
    'description': (
        'Experimental post-session heads-up turn/river CFR+ study. Complete explicit '
        'weighted arrival ranges, at most TWO concrete combos per player, one size per street, '
        '2000 iterations. No raises/rake, range inference, node locking or GTO claim. '
        'Money is integer cents; sizes are fractions of the pot at that street, capped at '
        'remaining stack, disclosed exactly. Up to four output-only hand/node/river views; '
        'a river view never conditions turn training on a future card. Strategies are returned '
        'only if the unchanged 0.5%-pot root NashConv gate passes; low-reach action EVs '
        'may remain inaccurate. A timeout or insufficient convergence returns no strategy. '
        'Tiny pedagogical ranges do not represent realistic full-width poker arrivals.'),
    'inputSchema': TurnInputs.model_json_schema(),
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _bet_label(cents):
    whole, fraction = divmod(cents, 100)
    amount = f'{whole}.{fraction:02d}'.rstrip('0') if fraction else str(whole)
    return 'bet_'+amount


def _cent_tree(args):
    """Exact public street roots and amounts; never round fractional-cent input."""
    with localcontext(Context(prec=80)):
        pot, stack = Decimal(args['pot_cents']), Decimal(args['stack_cents'])

        def bets(street, matched):
            values = [min(stack-matched, (pot+2*matched)*Decimal(str(f)))
                      for f in args[street+'_bet_sizes']]
            if any(b != b.to_integral_value() for b in values):
                raise ValueError('All normalized bets must be exact integer cents; no rounding')
            return [int(b) for b in values]

        tree = {'turn': bets('turn', Decimal(0))}
        for amount in tree['turn']:
            if amount < stack:
                for prefix in ('turn/', 'turn/check/'):
                    tree[prefix+_bet_label(amount)+'/call/river'] = bets('river', Decimal(amount))
        tree['turn/check/check/river'] = bets('river', Decimal(0))
        return tree


def prepare(arguments):
    """Cheap admission before acquiring the single shared worker slot; repeat in child."""
    args = TurnInputs.model_validate(arguments).model_dump()
    board = cards(args['board'], 4)
    args['board'] = ','.join(board)
    hands = []
    for name in ('oop_range', 'ip_range'):
        side = []
        for row in args[name]:
            hand = combo_key(*cards(row['hand'], 2))
            if set(hand) & set(board) or hand in side:
                raise ValueError('Explicit range contains a blocked or duplicate combo')
            row['hand'] = ''.join(hand)
            side.append(hand)
        hands.append(side)
    for side in (0, 1):
        if any(not any(not set(a) & set(b) for b in hands[1-side]) for a in hands[side]):
            raise ValueError('Every supplied combo must have a compatible opponent')
    _cent_tree(args)
    for view in args['views']:
        hand = combo_key(*cards(view['hand'], 2))
        if hand not in hands[0 if view['player'] == 'oop' else 1]:
            raise ValueError('Queried hand must belong to its full arrival range')
        view['hand'] = ''.join(hand)
        if view['river_card'] is not None:
            river = cards(view['river_card'], 1)[0]
            if river in board or river in hand:
                raise ValueError('River view is blocked by the board or queried hand')
    return args


def solver_config(args):
    return dict(board=args['board'], pot=args['pot_cents']/100, stack=args['stack_cents']/100,
                oop_range=','.join(f"{r['hand']}:{r['weight']}" for r in args['oop_range']),
                ip_range=','.join(f"{r['hand']}:{r['weight']}" for r in args['ip_range']),
                turn_bet_sizes=args['turn_bet_sizes'], river_bet_sizes=args['river_bet_sizes'])


def _canonicalize_tree(solver, args):
    """Relabel the pilot instance only; leave numerical leaves/tensors/order intact."""
    exact = _cent_tree(args)
    actions, effective = {}, {}

    def street_root(path):
        return path.split('/river', 1)[0]+'/river' if '/river' in path else 'turn'

    def public_path(path):
        parts = path.split('/')
        return '/'.join(actions[street_root('/'.join(parts[:i]))][token]
                        if token.startswith('bet_') else token for i, token in enumerate(parts))

    # Turn action mapping must exist before mapping called-turn river histories.
    for raw in sorted(solver.effective_bets, key=lambda name: name.count('/')):
        public = public_path(raw)
        if public not in exact or public in effective:
            raise ValueError('Float tree differs from exact-cent histories or labels collide')
        amounts = solver.effective_bets[raw]
        labels = solver.nodes[raw].actions[1:]
        cents = exact[public]
        if len(amounts) != len(cents) or len(labels) != len(cents):
            raise ValueError('Float tree differs from exact-cent actions')
        # This only checks an already exact-cent request against binary64 arithmetic.
        # It never admits a near-cent request or changes a numerical contribution.
        allowance = 8*math.ulp(max(solver.pot, solver.stack))
        if any(not math.isfinite(b) or abs(b-c/100) > allowance for b, c in zip(amounts, cents, strict=True)):
            raise ValueError('Float bet differs from validated exact cents')
        public_labels = [_bet_label(c) for c in cents]
        if len(set(labels)) != len(labels) or len(set(public_labels)) != len(public_labels):
            raise ValueError('Public action labels collide')
        actions[raw] = dict(zip(labels, public_labels, strict=True))
        effective[public] = [c/100 for c in cents]
    if set(effective) != set(exact):
        raise ValueError('Float tree is missing exact-cent histories')
    renamed, plans = {}, []
    for raw, node in solver.nodes.items():
        public = public_path(raw)
        labels = tuple(actions[street_root(raw)][a] if a.startswith('bet_') else a for a in node.actions)
        if raw != node.name or public in renamed or len(set(labels)) != len(labels):
            raise ValueError('Public node/action labels collide or tree names disagree')
        renamed[public] = node
        plans.append((node, public, labels))
    # Apply only after the entire mapping has passed, preserving dictionary order.
    for node, public, labels in plans:
        node.name, node.actions = public, labels
    solver.nodes = renamed
    solver.effective_bets = effective


def validated_solver(args):
    solver = TurnSolver(**solver_config(args))
    _canonicalize_tree(solver, args)
    for view in args['views']:
        node = solver.nodes.get(view['node'])
        if (node is None or node.player != (0 if view['player'] == 'oop' else 1)
                or bool(node.street) != (view['river_card'] is not None)):
            raise ValueError('Unknown node, wrong actor, or missing/unexpected river context')
    return solver


def project(solver, views):
    collected = {}
    if views:
        solver._walk(solver.root, *solver.weights, collect=collected)
    rows = []
    for view in views:
        node = solver.nodes[view['node']]
        side = node.player
        index = solver.hands[side].index(combo_key(*cards(view['hand'], 2)))
        location = (index,) if not node.street else (solver.rivers.index(view['river_card']), index)
        data = collected[node.name]
        opponent = float(data['opponent'][location])
        initial = (solver.valid if side == 0 else solver.valid.T)[index] @ solver.weights[1-side]
        rows.append(dict(view, frequency=dict(zip(node.actions, node.average()[location].tolist(), strict=True)),
                         action_ev_relative_to_half_turn_pot={a: float(v) if math.isfinite(v) else None
                             for a, v in zip(node.actions, data['ev'][location], strict=True)},
                         own_reach_given_hand=float(data['own'][location]/solver.weights[side][index]),
                         compatible_opponent_reach=opponent,
                         chance_reach=data['chance_reach'],
                         reach_probability_given_hand=float(data['own'][location]/solver.weights[side][index]
                                                            *opponent/initial*data['chance_reach'])))
    return rows


def calculate(arguments):
    args = prepare(arguments)
    solver = validated_solver(args)
    output = solver.solve(args['iterations'])
    best = [float(solver.weights[side] @ solver._walk(
        solver.root, *solver.weights, best_response=side)[side]/solver.mass) for side in (0, 1)]
    sources = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
               for name in SOURCE_FILES}
    game = {k: v for k, v in args.items() if k != 'views'}
    identity = {'schema': VERSION, 'game': game, 'sources_sha256_lf': sources,
                'algorithm': output['computation'], 'python': platform.python_version(), 'numpy': np.__version__}
    result = {'schema_version': VERSION, 'source': 'computed_on_demand', 'status': 'computed',
              'game': game, 'game_identity_sha256': digest(identity), 'provenance': identity,
              'request_sha256': digest(args), 'diagnostics': output['diagnostics'],
              'best_response_bounds': {'oop_best_response_ev': best[0], 'ip_best_response_ev': best[1],
                                       'raw_nash_conv_chips': sum(best)},
              'checkpoints': output['checkpoints'], 'chance': output['chance'],
              'effective_bets_by_public_history': output['effective_bets_by_public_history'],
              'ev_baseline': output['ev_baseline'], 'action_ev_interpretation': output['action_ev_interpretation'],
              'limitations': 'Experimental tiny independent arrival ranges, no raises/rake/locking; '
                             'root convergence does not establish low-reach EV precision, realistic ranges or full GTO. '
                             'An individual result does not establish release or client acceptance.'}
    d = result['diagnostics']
    values = [v for checkpoint in output['checkpoints'] for v in checkpoint.values()]
    if (not all(math.isfinite(v) for v in values) or abs(d['zero_sum_residual']) > 1e-8
            or d['raw_nash_conv_chips'] < -1e-8 or d['nash_conv_pct_pot'] > MAX_GAP_PCT):
        result.update(status='insufficient_convergence', views=[])
    else:
        result['views'] = project(solver, args['views'])
    result['result_sha256'] = digest(result)
    if len(json.dumps(result, allow_nan=False).encode()) > MAX_RESULT_BYTES:
        raise ValueError('Result exceeds the pilot output budget')
    return result
