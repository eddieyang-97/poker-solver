"""Local research invariants, not hosted acceptance or fitted accuracy tests."""
import copy
from itertools import permutations
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import numpy as np

from benchmarks.turn_feasibility import full_record
from benchmarks.turn_independent import product_solver, product_profile
from benchmarks.turn_reference import IndependentTurnGame
from benchmarks.turn_reuse import (
    bound_result, equivalence_map, equivalent_key, evaluate, normalized_tree,
    same_mapped_game, similarity, suit_map, transfer,
)
from poker_spot.core import DECK
from scripts.benchmark_turn_reuse import online_probe

ROOT = Path(__file__).resolve().parents[1]


def transformed(config, mapping, scale=1):
    result = copy.deepcopy(config)
    result['board'] = [mapping[c] for c in result['board']]
    for side in ('oop', 'ip'):
        for row in result[side]:
            row['hand'] = ''.join(mapping[row['hand'][i:i+2]] for i in (0, 2))
    result['pot'] *= scale
    result['stack'] *= scale
    return result


class TurnReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'benchmarks/turn-independent-fixtures.json').read_text())[0]['config']
        cls.source = product_solver(cls.config)
        result = cls.source.solve(200)
        cls.record = full_record(cls.source, result)

    def test_all_global_suit_permutations_and_money_share_key(self):
        expected, _ = equivalent_key(self.source, 200)
        for order in permutations('cdhs'):
            target = product_solver(transformed(self.config, suit_map(order), 2))
            self.assertEqual(equivalent_key(target, 200)[0], expected)
        self.assertNotEqual(equivalent_key(self.source, 201)[0], expected)

    def test_exact_transfer_preserves_all_runouts_hand_order_and_scaled_ev(self):
        mapping = suit_map('shdc')
        config = transformed(self.config, mapping, .5)
        config['board'].reverse()
        target = product_solver(config)
        transfer(self.record, self.source, target, equivalence_map(self.source, target, 200), exact=True)
        actual, expected = evaluate(target), evaluate(self.source)
        for key in actual:
            self.assertAlmostEqual(actual[key], expected[key]*.5, places=10)
        game = IndependentTurnGame(config)
        external = game.evaluate(product_profile(game, target))
        for key in actual:
            self.assertAlmostEqual(actual[key], external[key], places=10)
        a, b = {}, {}
        self.source._walk(self.source.root, *self.source.weights, collect=a)
        target._walk(target.root, *target.weights, collect=b)
        for sa, tb in zip(self.source.nodes.values(), target.nodes.values(), strict=True):
            if sa.street:
                order = [target.rivers.index(mapping[c]) for c in self.source.rivers]
                ev = b[tb.name]['ev'][order]
            else:
                ev = b[tb.name]['ev']
            np.testing.assert_allclose(ev, a[sa.name]['ev']*.5, atol=1e-10, rtol=0, equal_nan=True)

    def test_exact_rejects_non_global_mapping_weight_and_money_changes(self):
        identity = {c: c for c in DECK}
        for mutation in (lambda c: c.update(stack=151),
                         lambda c: c['oop'][0].update(weight=.5),
                         lambda c: c.update(river_bet_sizes=[1])):
            config = copy.deepcopy(self.config)
            mutation(config)
            target = product_solver(config)
            self.assertNotEqual(equivalent_key(target, 200)[0], equivalent_key(self.source, 200)[0])
            with self.assertRaises(ValueError):
                transfer(self.record, self.source, target, identity, exact=True)
        bad = dict(identity, **{'2c': '2d', '2d': '2c'})
        with self.assertRaises(ValueError):
            transfer(self.record, self.source, product_solver(transformed(self.config, bad)), bad, exact=True)

    def test_approximate_transfer_checks_deck_hands_topology_and_record(self):
        identity = {c: c for c in DECK}
        for changes in ({'stack': 20}, {'turn_bet_sizes': [.5, 1]},
                        {'oop': [{'hand': 'AhKh', 'weight': 1}]}):
            target = product_solver(dict(self.config, **changes))
            with self.assertRaises(ValueError):
                transfer(self.record, self.source, target, identity)
            self.assertTrue(all(not n.strategy_sum.any() for n in target.nodes.values()))
        with self.assertRaisesRegex(ValueError, 'bijection'):
            transfer(self.record, self.source, product_solver(self.config), {'2c': '2c'})
        corrupt = copy.deepcopy(self.record)
        corrupt['nodes']['turn']['frequency'][0] = [1, 1]
        with self.assertRaises(ValueError):
            transfer(corrupt, self.source, product_solver(self.config), identity)

    def test_weighted_collision_hand_permutation_and_exact_null_support(self):
        config = json.loads((ROOT/'benchmarks/turn-reuse-fixtures.json').read_text())['sources']['weighted_collision']
        source = product_solver(config)
        record = full_record(source, source.solve(200))
        mapping = suit_map('dhsc')
        changed = transformed(config, mapping)
        for side in ('oop', 'ip'):
            changed[side].reverse()
        target = product_solver(changed)
        transfer(record, source, target, mapping, exact=True)
        external = IndependentTurnGame(changed)
        values = external.evaluate(product_profile(external, target))
        for key, value in evaluate(source).items():
            self.assertAlmostEqual(values[key], value, places=10)
        a, b = {}, {}
        source._walk(source.root, *source.weights, collect=a)
        target._walk(target.root, *target.weights, collect=b)
        for sa, tb in zip(source.nodes.values(), target.nodes.values(), strict=True):
            lookup = {frozenset(h): i for i, h in enumerate(target.hands[sa.player])}
            hands = [lookup[frozenset(mapping[c] for c in h)] for h in source.hands[sa.player]]
            if sa.street:
                rivers = [target.rivers.index(mapping[c]) for c in source.rivers]
                ev = b[tb.name]['ev'][np.ix_(rivers, hands, range(len(sa.actions)))]
            else:
                ev = b[tb.name]['ev'][hands]
            np.testing.assert_allclose(ev, a[sa.name]['ev'], atol=1e-10, rtol=0, equal_nan=True)

    def test_approximate_board_transfer_is_evaluated_on_target_not_source(self):
        mapping = {c: c for c in DECK}
        mapping['Js'], mapping['Qs'] = 'Qs', 'Js'
        config = transformed(self.config, mapping)
        target = product_solver(config)
        transfer(self.record, self.source, target, mapping)
        actual = evaluate(target)
        external = IndependentTurnGame(config)
        checked = external.evaluate(product_profile(external, target))
        for key in actual:
            self.assertAlmostEqual(actual[key], checked[key], places=10)
        self.assertNotAlmostEqual(actual['oop_ev'], evaluate(self.source)['oop_ev'], places=3)
        self.assertGreater(similarity(self.source, target, mapping)['runout_payoff_sign_change'], 0)

    def test_bounds_keep_wide_cases_as_abstentions_and_cent_ledger_exact(self):
        bound = bound_result({'oop_lower_bound': -2, 'oop_upper_bound': 3}, 100)
        self.assertEqual(bound['status'], 'abstain_wide_bound')
        self.assertAlmostEqual(bound['maximum_equilibrium_value_error'], 2.5+1e-8)
        self.assertEqual(bound_result({'oop_lower_bound': 1, 'oop_upper_bound': 1.5}, 100)['status'], 'bounded_root_value')
        a = product_solver(self.config)
        b = product_solver(dict(self.config, pot=100.00000000001))
        self.assertNotEqual(normalized_tree(a), normalized_tree(b))

    def test_fixture_design_has_disjoint_equivalence_classes_and_explicit_negatives(self):
        fixture = json.loads((ROOT/'benchmarks/turn-reuse-fixtures.json').read_text())
        source_keys = {equivalent_key(product_solver(c))[0] for c in fixture['sources'].values()}
        self.assertEqual(len(source_keys), len(fixture['sources']))
        duplicates = []
        for case in fixture['targets']:
            target = product_solver(case['config'])
            key = equivalent_key(target)[0]
            self.assertEqual(key in source_keys, case['kind'] in ('exact', 'equivalent'), case['id'])
            if case['kind'] == 'approximate':
                mapping = {c: case['card_mapping'].get(c, c) for c in DECK}
                if same_mapped_game(product_solver(fixture['sources'][case['source']]), target, mapping):
                    duplicates.append(case['id'])
        self.assertEqual(duplicates, ['dry_stack_160', 'dry_turn_9s', 'collision_turn_9s'])

    def test_linux_probe_requires_real_limits_and_budget_receipt(self):
        good = {'mode': 'linux_limits_not_hosted', 'limits': {'cpu_seconds': [20, 20],
                'address_space_bytes': [384*1024**2]*2}, 'linux_memory': {'VmPeak_bytes': 100*1024**2},
                'cpu_through_snapshot_seconds': .3}
        cases = [good, dict(good, limits=None), dict(good, mode='unlimited_local'),
                 dict(good, cpu_through_snapshot_seconds=21),
                 dict(good, linux_memory={'VmPeak_bytes': 385*1024**2})]
        for i, value in enumerate(cases):
            process = subprocess.CompletedProcess([], 0, stdout=json.dumps(value), stderr='')
            with patch('scripts.benchmark_turn_reuse.sys.platform', 'linux'), \
                    patch('scripts.benchmark_turn_reuse.subprocess.run', return_value=process) as run:
                if i:
                    with self.assertRaisesRegex(ValueError, 'receipt'):
                        online_probe({}, {}, ROOT)
                else:
                    self.assertEqual(online_probe({}, {}, ROOT)['limits'], good['limits'])
                self.assertEqual(run.call_args.kwargs['timeout'], 20)
                self.assertNotIn('--unlimited', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
