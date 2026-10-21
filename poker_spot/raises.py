"""Opt-in local river CFR+ with one additional raise. Never registered with MCP."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math

import numpy as np

from .core import Node, RiverSolver, cards, expand_range


def cents(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Amounts must be finite numbers')
    amount = Decimal(str(value))*100
    if not 0 < amount <= 100_000_000 or amount != amount.to_integral_value():
        raise ValueError('Amounts must be positive, cent-exact and at most 1,000,000 chips')
    return int(amount)


def fractions(values):
    if (not isinstance(values, list) or not 1 <= len(values) <= 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v <= 3 for v in values)
            or values != sorted(set(values))):
        raise ValueError('Supply one or two ascending distinct fractions in (0,3]')
    return values.copy()


def sized(base, fraction, cap):
    try:
        amount = min(Decimal(base)*Decimal(str(fraction)), Decimal(cap))
    except InvalidOperation:
        raise ValueError('Invalid sizing') from None
    if amount != amount.to_integral_value() or amount <= 0:
        raise ValueError('Effective sizing must be positive and cent-exact; no rounding')
    return int(amount)


def label(kind, total):
    return f'{kind}_to_{total//100}.{total%100:02d}'


@dataclass(frozen=True)
class Terminal:
    contributions: tuple[int, int]
    winner: int | None

    @property
    def refunds(self):
        low = min(self.contributions)
        return tuple(c-low for c in self.contributions)

    @property
    def settled(self):
        return tuple(c-r for c, r in zip(self.contributions, self.refunds, strict=True))


class RaiseRiverSolver(RiverSolver):
    """Reuse the existing CFR+ traversal; supply a separate cent-exact local tree.

    Equal effective stacks; one additional raise beyond the opening bet.
    Raise fractions multiply pot after calling, giving the increment beyond call.
    """

    def __init__(self, board, oop_range, ip_range, pot, stack, bet_sizes, raise_sizes, minimum_bet):
        self.pot_cents, self.stack_cents, self.minimum_cents = map(cents, (pot, stack, minimum_bet))
        self.raise_sizes = fractions(raise_sizes)
        bet_sizes = fractions(bet_sizes)
        parsed_board = cards(board, 5)
        for text in (oop_range, ip_range):
            if not isinstance(text, str) or len(text) > 8000 or len(expand_range(text, parsed_board)) > 24:
                raise ValueError('Local raise ranges are limited to 24 board-unblocked combos and 8,000 characters')
        super().__init__(board, oop_range, ip_range, pot, stack, bet_sizes)
        self.w0 /= self.w0.sum()
        self.w1 /= self.w1.sum()
        self.prob = float(self.w0@self.valid@self.w1)
        if not self.prob > 0:
            raise ValueError('Compatible deal mass is not representable')
        self.nodes, self.locations, self.terminals = {}, {}, {}
        self.bet_cents = [sized(self.pot_cents, f, self.stack_cents) for f in bet_sizes]
        if len(set(self.bet_cents)) != len(self.bet_cents):
            raise ValueError('Opening sizes collapse after stack capping')
        if any(b < self.minimum_cents and b != self.stack_cents for b in self.bet_cents):
            raise ValueError('Opening bet below minimum is not an actual all-in')
        self.root = self._build((), (0, 0), 0, 0, 0)

    def _build(self, history, contribution, actor, checks, raises):
        key = '/'.join(history) or 'root'

        def terminal(token, paid, winner=None):
            leaf = Terminal(paid, winner)
            self.terminals['/'.join(history+(token,))] = leaf
            return leaf

        actions, children, details = [], [], []

        def add(action, child, kind, total=0, **extra):
            actions.append(action)
            children.append(child)
            details.append({'kind': kind, 'total_to_cents': total, **extra})

        owed = max(contribution)-contribution[actor]
        if owed:
            add('fold', terminal('f', contribution, 1-actor), 'fold')
            matched = (max(contribution),)*2
            add('call', terminal('c', matched), 'call', matched[actor], paid_cents=owed)
            if raises == 0 and max(contribution) < self.stack_cents:
                used = set()
                for fraction in self.raise_sizes:
                    extra = sized(self.pot_cents+2*max(contribution), fraction, self.stack_cents-max(contribution))
                    target = max(contribution)+extra
                    if target in used:
                        raise ValueError('Raise sizes collapse after stack capping')
                    used.add(target)
                    full = extra >= max(contribution)
                    if not full and target != self.stack_cents:
                        raise ValueError('Under-minimum raise is not an actual all-in')
                    paid = list(contribution)
                    paid[actor] = target
                    add(label('raise', target), self._build(history+(f'r{extra}',), tuple(paid), 1-actor, 0, 1),
                        'raise', target, paid_cents=owed+extra, increment_cents=extra,
                        fraction_of_pot_after_call=fraction, full_raise=full, all_in=target == self.stack_cents)
        else:
            child = terminal('c', contribution) if checks else self._build(history+('c',), contribution, 1-actor, 1, 0)
            add('check', child, 'check')
            for amount in self.bet_cents:
                paid = list(contribution)
                paid[actor] = amount
                add(label('bet', amount), self._build(history+(f'b{amount}',), tuple(paid), 1-actor, 0, 0),
                    'bet', amount, paid_cents=amount, all_in=amount == self.stack_cents)
        node = Node(key, actor, tuple(actions), tuple(children), len(self.h0 if actor == 0 else self.h1))
        self.nodes[key] = node
        self.locations[key] = {'actor': actor, 'contributions_cents': list(contribution), 'actions': details,
                               'additional_raises_used': raises}
        return node

    def _terminal(self, terminal, r0, r1):
        matched = min(terminal.contributions)/100
        half = self.pot/2+matched
        if terminal.winner is None:
            return half*(self.sign@r1), -half*(self.sign.T@r0)
        value = half if terminal.winner == 0 else -half
        return value*(self.valid@r1), -value*(self.valid.T@r0)

    def _eval(self, node, r0, r1, best_response=None, collect=None):
        if not isinstance(node, Node):
            return self._terminal(node, r0, r1)
        strategy = node.average()
        results = [self._eval(child, r0*strategy[:, i] if node.player == 0 else r0,
                              r1*strategy[:, i] if node.player == 1 else r1, best_response, collect)
                   for i, child in enumerate(node.children)]
        values = np.stack([v[node.player] for v in results], axis=1)
        if collect is not None:
            opponent = self.valid@r1 if node.player == 0 else self.valid.T@r0
            q = np.divide(values, opponent[:, None], out=np.full_like(values, np.nan), where=opponent[:, None] > 0)
            collect[node.name] = {'ev': q, 'own_reach': r0 if node.player == 0 else r1,
                                  'opponent_reach': opponent, 'joint_reach': float(r0@self.valid@r1/self.prob)}
        actor = values.max(axis=1) if best_response == node.player else (values*strategy).sum(axis=1)
        other = np.sum([v[1-node.player] for v in results], axis=0)
        return (actor, other) if node.player == 0 else (other, actor)

    def solve(self, iterations=2000, oop_hand=None, ip_hand=None):
        if type(iterations) is not int or not 20 <= iterations <= 5000:
            raise ValueError('Local raise iterations must be between 20 and 5,000')
        if getattr(self, '_solved', False):
            raise ValueError('Use a fresh solver for each recorded training run')
        out = super().solve(iterations, oop_hand, ip_hand)
        self._solved = True
        collected = {}
        self._eval(self.root, self.w0, self.w1, collect=collected)
        out.update(model='Experimental local heads-up river with one additional raise, no rake',
                   effective_bet_amounts=[b/100 for b in self.bet_cents],
                   maximum_additional_raises=1, raise_sizes=self.raise_sizes, minimum_bet=self.minimum_cents/100,
                   raise_size_semantics='fraction of pot after calling, added beyond the call; labels are total-to chips',
                   nodes={name: dict(self.locations[name], joint_reach_probability=collected[name]['joint_reach']) for name in self.nodes},
                   terminal_ledgers={name: {'gross_contributions_cents': list(t.contributions),
                                            'refunds_cents': list(t.refunds), 'settled_contributions_cents': list(t.settled),
                                            'contested_pot_cents': self.pot_cents+sum(t.settled), 'winner': t.winner}
                                     for name, t in self.terminals.items()},
                   limits={'combos_per_side': 24, 'bet_sizes': 2, 'raise_sizes': 2, 'iterations': 5000},
                   interpretation='Computed finite-tree approximation under supplied arrival ranges. EV baseline: half starting pot. '
                                  'Own reach is not joint node reach; null action EV means zero opponent reach. No hosted acceptance.')
        return out
