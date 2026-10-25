"""Issue #25: trusted local experiments, never imported by the product.

Transfer entire behavioral policies, not regrets or claimed target solutions.
Only global suit renaming and exactly proportional complete money ledgers are
admitted as equivalences. Other card bijections are explicitly approximations.
"""
from fractions import Fraction
from itertools import permutations

import numpy as np

from benchmarks.turn_feasibility import digest, identity, validate_record
from poker_spot.core import DECK
from poker_spot.turn import Chance, Decision, Terminal

VERSION = 'turn-reuse-study-v1'
NUMERIC = 1e-8
SUITS = 'cdhs'


def suit_map(order):
    if len(order) != 4 or set(order) != set(SUITS):
        raise ValueError('Global suit permutation required')
    suits = dict(zip(SUITS, order, strict=True))
    return {c: c[0]+suits[c[1]] for c in DECK}


def card_map(mapping):
    if set(mapping) != set(DECK) or set(mapping.values()) != set(DECK):
        raise ValueError('Complete deck bijection required')
    return mapping


def tree_pairs(source, target):
    """Exact ordered structural mapping; no missing actions or implicit sizing.

    Approximate transfer permits different money amounts, but not a changed
    topology, all-in continuation, actor, action order or terminal ledger kind.
    """
    pairs = []

    def walk(a, b):
        if type(a) is not type(b):
            raise ValueError('Incompatible tree topology')
        if isinstance(a, Terminal):
            if (a.kind, a.street, a.winner) != (b.kind, b.street, b.winner):
                raise ValueError('Incompatible terminal semantics')
        elif isinstance(a, Chance):
            walk(a.child, b.child)
        elif isinstance(a, Decision):
            kinds = lambda n: tuple('bet' if x.startswith('bet_') else x for x in n.actions)
            if (a.player, a.street, kinds(a)) != (b.player, b.street, kinds(b)):
                raise ValueError('Incompatible actor/street/action order')
            pairs.append((a, b))
            for x, y in zip(a.children, b.children, strict=True):
                walk(x, y)
        else:
            raise ValueError('Unknown tree node')

    walk(source.root, target.root)
    return pairs


def normalized_tree(solver):
    """Exact binary64 ratios, never rounded to manufacture equivalence."""
    unit = Fraction(solver.pot)
    ratio = lambda x: str(Fraction(x)/unit)

    def walk(node):
        if isinstance(node, Terminal):
            return ['terminal', node.kind, node.street, node.winner, *map(ratio, node.contrib)]
        if isinstance(node, Chance):
            return ['chance', walk(node.child)]
        return ['decision', node.player, node.street,
                [ratio(float(a[4:])) if a.startswith('bet_') else a for a in node.actions],
                [walk(c) for c in node.children]]

    return [ratio(solver.stack), walk(solver.root)]


def equivalent_key(solver, iterations=2000):
    """Canonical complete game under 24 global suit permutations and chip units.

    Preserve absolute expanded weights, solver/runtime/algorithm/iterations,
    player identities, all normalized bet/contribution ledgers and stack ratio.
    Board and combo *order* is irrelevant to this turn game, and mapped explicitly.
    """
    original = identity(solver, iterations)
    common = {k: v for k, v in original.items() if k not in ('board', 'ranges', 'pot', 'stack', 'sizes')}
    common.update(reuse_version=VERSION, normalized_tree=normalized_tree(solver))
    candidates = []
    for order in permutations(SUITS):
        mapping = suit_map(order)
        payload = dict(common, board=sorted(mapping[c] for c in solver.board), ranges=[
            sorted([sorted(mapping[c] for c in hand), float(weight)]
                   for hand, weight in zip(hands, weights, strict=True))
            for hands, weights in zip(solver.hands, solver.weights, strict=True)])
        candidates.append((digest(payload), ''.join(order)))
    key, order = min(candidates)
    return key, suit_map(order)


def equivalence_map(source, target, iterations=2000):
    left, a = equivalent_key(source, iterations)
    right, b = equivalent_key(target, iterations)
    if left != right:
        raise ValueError('Not a verified equivalent complete game')
    inverse = {v: k for k, v in b.items()}
    return {c: inverse[a[c]] for c in DECK}


def transfer(record, source, target, mapping, *, exact=False):
    """Install source *average* policy only; target EVs must be recomputed.

    Source record is verified with #21's existing full-policy contract. Relative
    weight/support, missing hands, stale source and invalid policy fail closed.
    Approximate transfers may change weights, boards and amounts, never support
    or topology. No defaults for unseen hands, public cards or actions.
    """
    validate_record(record, source, record['identity']['iterations'])
    card_map(mapping)
    if set(map(mapping.get, source.board)) != set(target.board):
        raise ValueError('Board mapping mismatch')
    if exact:
        # Check the supplied mapping itself, not merely existence of some isomorphism.
        if mapping not in [suit_map(order) for order in permutations(SUITS)]:
            raise ValueError('Exact transfer requires global suit relabelling')
        if normalized_tree(source) != normalized_tree(target):
            raise ValueError('Money ledger is not exactly proportional')
    hands, rivers = [], [source.rivers.index(next(c for c in source.rivers if mapping[c] == t))
                         for t in target.rivers]
    for side in (0, 1):
        lookup = {frozenset(mapping[c] for c in h): i for i, h in enumerate(source.hands[side])}
        if set(lookup) != {frozenset(h) for h in target.hands[side]}:
            raise ValueError('Unmapped range support')
        order = [lookup[frozenset(h)] for h in target.hands[side]]
        if exact and not np.array_equal(source.weights[side][order], target.weights[side]):
            raise ValueError('Exact transfer weight mismatch')
        hands.append(order)
    pairs = tree_pairs(source, target)
    # Validate the entire mapping before mutating the experimental target.
    for a, b in pairs:
        policy = np.asarray(record['nodes'][a.name]['frequency'])
        if a.street:
            policy = policy[np.ix_(rivers, hands[a.player], range(len(a.actions)))]
        else:
            policy = policy[hands[a.player]]
        b.strategy_sum[:] = policy
    return target


def evaluate(solver):
    """Full target-game policy evaluation and both legal best responses."""
    left, right = solver._walk(solver.root, *solver.weights)
    upper = float(solver.weights[0] @ solver._walk(solver.root, *solver.weights, best_response=0)[0]/solver.mass)
    lower = -float(solver.weights[1] @ solver._walk(solver.root, *solver.weights, best_response=1)[1]/solver.mass)
    value = float(solver.weights[0] @ left/solver.mass)
    residual = value+float(solver.weights[1] @ right/solver.mass)
    if not all(np.isfinite(x) for x in (value, lower, upper, residual)) or abs(residual) > NUMERIC:
        raise ValueError('Invalid zero-sum evaluation')
    if lower > value+NUMERIC or value > upper+NUMERIC:
        raise ValueError('Invalid best-response interval')
    return {'oop_ev': value, 'ip_ev': -value, 'oop_lower_bound': lower, 'oop_upper_bound': upper,
            'nash_conv_chips': upper-lower}


def bound_result(evaluation, pot):
    """A root-value bracket, never precision for every hand or action EV."""
    lower, upper = evaluation['oop_lower_bound'], evaluation['oop_upper_bound']
    if not all(np.isfinite(x) for x in (lower, upper, pot)) or pot <= 0 or lower > upper+NUMERIC:
        raise ValueError('Invalid value bracket')
    width = max(0.0, upper-lower)
    narrow = width <= pot*0.005  # existing convergence gate, unchanged
    return {'status': 'bounded_root_value' if narrow else 'abstain_wide_bound',
            'lower': lower, 'upper': upper, 'midpoint': (lower+upper)/2,
            'maximum_equilibrium_value_error': width/2+NUMERIC,
            'warning': 'Numerical best-response bracket in this constrained target game; no action/hand precision guarantee'}


def checkdown(solver):
    return float(solver.weights[0] @ solver.runout_sign @ solver.weights[1]/solver.mass*solver.pot/2)


def similarity(source, target, mapping):
    """Explanatory diagnostics, not a calibrated acceptance score."""
    order = []
    for side in (0, 1):
        lookup = {frozenset(mapping[c] for c in h): i for i, h in enumerate(source.hands[side])}
        order.append([lookup[frozenset(h)] for h in target.hands[side]])
    inverse = {v: k for k, v in mapping.items()}
    rivers = [source.rivers.index(inverse[c]) for c in target.rivers]
    signs = source.river_sign[np.ix_(rivers, *order)]
    prior = source.weights[0][order[0]][:, None]*source.weights[1][order[1]][None, :]*target.valid
    prior /= prior.sum()
    joint = target.weights[0][:, None]*target.weights[1][None, :]*target.valid/target.mass
    return {'compatible_deal_total_variation': float(abs(prior-joint).sum()/2),
            'runout_payoff_sign_change': float((abs(signs-target.river_sign)*joint[None, :, :]).sum()/88),
            'checkdown_ev_shift_pct_pot': (checkdown(target)/target.pot-checkdown(source)/source.pot)*100,
            'stack_pot_ratio_change': target.stack/target.pot-source.stack/source.pot}


def same_mapped_game(source, target, mapping):
    """Leakage audit: identical complete strategic game under PROVIDED mapping.

    Not a general graph-isomorphism search/key. Unused stack differences can
    disappear, as can blank-rank swaps whose entire payoff/chance tensors agree.
    Comparing equity alone is insufficient: retain every legal public context,
    private deal, terminal payoff and information-set structure.
    """
    card_map(mapping)
    if set(mapping[c] for c in source.board) != set(target.board):
        return False
    tree_pairs(source, target)
    if normalized_tree(source)[1] != normalized_tree(target)[1]:
        return False
    order = []
    for side in (0, 1):
        lookup = {frozenset(mapping[c] for c in h): i for i, h in enumerate(source.hands[side])}
        if set(lookup) != {frozenset(h) for h in target.hands[side]}:
            return False
        indices = [lookup[frozenset(h)] for h in target.hands[side]]
        if not np.array_equal(source.weights[side][indices], target.weights[side]):
            return False
        order.append(indices)
    inverse = {v: k for k, v in mapping.items()}
    rivers = [source.rivers.index(inverse[c]) for c in target.rivers]
    return (np.array_equal(source.valid[np.ix_(*order)], target.valid)
            and np.array_equal(source.river_valid[np.ix_(rivers, *order)], target.river_valid)
            and np.array_equal(source.river_sign[np.ix_(rivers, *order)], target.river_sign))


def root_actions(solver):
    collected = {}
    solver._walk(solver.root, *solver.weights, collect=collected)
    node = solver.nodes['turn']
    return {'actions': list(node.actions), 'ev': collected['turn']['ev'].tolist(),
            'frequency': node.average().tolist(), 'hands': [list(h) for h in solver.hands[0]]}
