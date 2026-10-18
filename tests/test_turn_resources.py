import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from benchmarks.turn_resources import ADDRESS_BYTES, CPU_SECONDS
from scripts.benchmark_turn_resources import run_probe, workloads


ROOT = Path(__file__).resolve().parents[1]


class TurnResourceTests(unittest.TestCase):
    def test_workload_matrix_is_explicit_and_retains_maximum_cases(self):
        cases = workloads()
        self.assertEqual(len(cases), 6)
        self.assertEqual(len({case['id'] for case in cases}), 6)
        originals = json.loads((ROOT/'benchmarks/turn-performance-fixtures.json').read_text())
        self.assertEqual([case['config'] for case in cases[:2]], [case['config'] for case in originals])
        self.assertEqual([len(case['config']['oop_range'].split(',')) for case in cases], [24, 24, 4, 12, 24, 24])
        cases[0]['config']['pot'] = 7
        self.assertEqual(workloads()[0]['config']['pot'], 100)
        for mode, wall in (('limits', 21), ('profile', 181), ('limits', 0), ('unknown', 1)):
            with self.assertRaises(ValueError):
                run_probe({}, 20, mode, wall)

    def test_timeout_and_signal_do_not_fabricate_measurements(self):
        with patch('scripts.benchmark_turn_resources.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(['worker'], 20, stderr=b'{"stage":"imports_complete"}\n')) as run:
            result = run_probe({}, 20)
        self.assertEqual(result['status'], 'WALL_TIMEOUT')
        self.assertIn('imports_complete', result['progress'])
        self.assertNotIn('measurement', result)
        self.assertEqual(run.call_args.kwargs['timeout'], 20)
        self.assertEqual(run.call_args.kwargs['env']['OPENBLAS_NUM_THREADS'], '1')
        with patch('scripts.benchmark_turn_resources.subprocess.run',
                   return_value=subprocess.CompletedProcess([], -9, '', 'stage')):
            result = run_probe({}, 20)
        self.assertEqual((result['status'], result['signal']),
                         ('ERROR', None) if sys.platform == 'win32' else ('SIGNAL', 'SIGKILL'))
        self.assertNotIn('measurement', result)

    def test_real_tight_parent_timeout_reaps_worker(self):
        result = run_probe(workloads()[0]['config'], 2000, wall_seconds=0.001)
        self.assertEqual(result['status'], 'WALL_TIMEOUT')
        self.assertNotIn('measurement', result)

    def test_worker_errors_and_budget_substitution_are_visible(self):
        result = run_probe({}, 19, 'profile', 10)
        self.assertEqual(result['status'], 'ERROR')
        self.assertIn('iterations', result['failure'])
        self.assertNotIn('measurement', result)
        forged = {'status': 'COMPLETED', 'limits': {'cpu_seconds': [21, 21],
                                                  'address_space_bytes': [ADDRESS_BYTES]*2}}
        with patch('scripts.benchmark_turn_resources.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, json.dumps(forged), '')):
            with self.assertRaisesRegex(ValueError, 'exact existing Linux budgets'):
                run_probe({}, 20)

    def test_actual_probe_or_explicit_unsupported_platform(self):
        result = run_probe(workloads()[2]['config'], 20)
        if sys.platform != 'linux':
            self.assertEqual(result['status'], 'UNSUPPORTED')
            self.assertIsNone(result['limits'])
            self.assertNotIn('measurement', result)
        else:
            self.assertEqual(result['status'], 'COMPLETED', result)
            self.assertEqual(result['limits'], {'cpu_seconds': [CPU_SECONDS]*2, 'address_space_bytes': [ADDRESS_BYTES]*2})
            self.assertTrue(result['within_observed_budgets'])
            self.assertGreater(result['linux_memory']['VmPeak_bytes'], 2**20)
            self.assertLessEqual(result['linux_memory']['VmPeak_bytes'], ADDRESS_BYTES)
            self.assertEqual(result['measurement']['range_combos'], {'oop': 4, 'ip': 4})

    @unittest.skipUnless(sys.platform == 'linux', 'Requires real Linux address-space enforcement')
    def test_actual_address_space_limit_rejects_oversized_allocation(self):
        code = ('import sys; sys.path.insert(0,sys.argv[1]); '
                'from benchmarks.turn_resources import install_limits, ADDRESS_BYTES; '
                'install_limits();\ntry: bytes(ADDRESS_BYTES)\n'
                'except MemoryError: print("LIMIT_ENFORCED")\nelse: raise RuntimeError("limit not effective")')
        result = subprocess.run([sys.executable, '-I', '-c', code, str(ROOT)], capture_output=True, text=True,
                                check=True, timeout=10)
        self.assertEqual(result.stdout.strip(), 'LIMIT_ENFORCED')

    def test_profile_is_separate_and_explicitly_unlimited(self):
        result = run_probe(workloads()[2]['config'], 20, 'profile', 30)
        self.assertEqual(result['status'], 'COMPLETED', result)
        self.assertEqual(result['mode'], 'profile')
        self.assertIsNone(result['limits'])
        self.assertNotIn('within_observed_budgets', result)
        self.assertTrue(result['hotspots']['cumulative_seconds'])


if __name__ == '__main__':
    unittest.main()
