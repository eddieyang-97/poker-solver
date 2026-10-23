import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from benchmarks.harness import evaluate_profile, make_game
from benchmarks.turn_decomposition import compare_decomposition, partition, turn_river_profile
from scripts.benchmark_turn_performance import run_worker


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT/'benchmarks/turn-decomposition-fixtures.json').read_text())


class TurnDecompositionTests(unittest.TestCase):
    def test_bounded_parallel_reference_preserves_order_profiles_and_failures(self):
        serial = compare_decomposition(FIXTURES[0], 20, 20, reference_workers=1)
        parallel = compare_decomposition(FIXTURES[0], 20, 20, reference_workers=2)
        for result in (serial, parallel):
            self.assertEqual(len(result['runouts']), 48)
            exports = [r['reference_export'] for r in result['runouts'] if r['mass']]
            self.assertEqual(len(exports), 44)
            for export in exports:
                self.assertIsInstance(export['pid'], int)  # OS process identifiers may be reused after exit.
                self.assertFalse(export['product_modules_loaded'])
                del export['pid']
                del export['training_cost']
        self.assertEqual(serial, parallel)
        for workers in (0, 3, True):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                compare_decomposition(FIXTURES[0], 20, 20, reference_workers=workers)
        with patch('benchmarks.turn_decomposition.run_reference', side_effect=ValueError('worker fault')):
            with self.assertRaisesRegex(ValueError, 'worker fault'):
                compare_decomposition(FIXTURES[0], 20, 20, reference_workers=2)

    def test_weighted_chance_and_zero_mass_cards(self):
        _, mass, rivers = partition(FIXTURES[0])
        self.assertEqual(mass, 1)
        self.assertEqual(len(rivers), 48)
        self.assertEqual({row['card'] for row in rivers if row['mass'] == 0}, {'Kh', 'Kd', 'As', 'Ad'})
        for row in rivers:
            self.assertEqual(row['probability'], 1/44 if row['mass'] else 0)
        _, mass, rivers = partition(FIXTURES[1])
        self.assertAlmostEqual(mass, 1.65)
        self.assertAlmostEqual(sum(row['probability'] for row in rivers), 1)
        ace = next(row for row in rivers if row['card'] == 'As')
        self.assertAlmostEqual(ace['mass'], 0.5)
        self.assertAlmostEqual(ace['probability'], 0.5/(44*1.65))

    def test_independent_river_trees_detect_product_payoff_fault(self):
        solver, _, rivers = partition(FIXTURES[1])
        solver.solve(100)

        def aggregate():
            ev = gap = 0.0
            for row in rivers:
                if not row['mass']:
                    continue
                fixture = copy.deepcopy(row['fixture'])
                # Reverse the independent input order: mapping must be by cards.
                fixture['oop'].reverse()
                fixture['ip'].reverse()
                game = make_game(fixture)
                result = evaluate_profile(game, turn_river_profile(solver, row['card'], fixture, game))
                ev += row['probability']*result['root'][0]
                gap += row['probability']*result['gap']
            return ev, gap

        ev, gap = aggregate()
        baseline = solver.diagnostics()
        self.assertAlmostEqual(ev, baseline['oop_ev'], delta=1e-9)
        self.assertAlmostEqual(gap, baseline['nash_conv_chips'], delta=1e-9)
        solver.river_sign.fill(0)
        corrupted = solver.diagnostics()
        self.assertGreater(abs(ev-corrupted['oop_ev']), 1)
        # Independent evaluation of the unchanged policy never reads river_sign.
        self.assertEqual(aggregate(), (ev, gap))

    def test_reject_tree_and_rounding_substitution(self):
        for change in ({'turn_bet_sizes': [0.5]}, {'bet_sizes': [0.333333333]},
                       {'include_all_in': True}, {'max_raises': 1},
                       {'stack': 20, 'bet_sizes': [0.5, 1]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                partition(FIXTURES[1] | change)
        solver, _, rivers = partition(FIXTURES[0])
        row = next(row for row in rivers if row['mass'])
        game = make_game(row['fixture'])
        solver.nodes['turn/check/check/river'].actions = ('check',)
        with self.assertRaises(ValueError):
            turn_river_profile(solver, row['card'], row['fixture'], game)


class TurnPerformanceTests(unittest.TestCase):
    def test_maximum_dimensions_worker_and_memory_units(self):
        fixture = json.loads((ROOT/'benchmarks/turn-performance-fixtures.json').read_text())[0]
        result = run_worker(fixture['config'], 20, 30)
        self.assertEqual(result['status'], 'COMPLETED', result)
        self.assertEqual(result['range_combos'], {'oop': 24, 'ip': 24})
        self.assertEqual(result['river_decision_templates'], 30)
        self.assertEqual(result['decision_node_templates'], 36)
        self.assertGreater(result['peak_resident_memory']['bytes'], 2**20)
        self.assertGreater(result['output_bytes'], 1000)
        self.assertTrue(all(value == '1' for value in result['blas_threads'].values()))

    def test_timeout_is_reported_as_failure_without_fabricated_peak(self):
        with patch('scripts.benchmark_turn_performance.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(['worker'], 1)) as execute:
            result = run_worker({}, 20, 1)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertNotIn('peak_resident_memory', result)
        self.assertEqual(execute.call_args.kwargs['timeout'], 1)
        self.assertEqual(execute.call_args.kwargs['env']['OPENBLAS_NUM_THREADS'], '1')


if __name__ == '__main__':
    unittest.main()
