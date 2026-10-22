import copy
from decimal import localcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.raises import compare, reference_game
from poker_spot.history import parse_history
from poker_spot.raise_review import evidence_label, prepare_raise_review, render_raise_markdown, run_raise_review
from poker_spot.raises import RaiseRiverSolver

ROOT = Path(__file__).resolve().parents[1]
HAND = parse_history((ROOT/'examples/hand-review-raises.txt').read_text())['hand']
SCENARIOS = json.loads((ROOT/'examples/hand-review-raise-scenarios.json').read_text())
CONFIG = dict(board='Ac,Jh,3s,Tc,4c', oop_range='7d3d:1,AhJd:0.35', ip_range='8s8c:0.5,QsQd:1',
              pot=63, stack=275, minimum_bet=2, bet_amounts_cents=[4000], raise_to_cents=[12000, 27500])


class ExactRaiseReviewTests(unittest.TestCase):
    def test_exact_and_fractional_forms_preserve_identical_strategy_and_payoffs(self):
        legacy = dict(board='2c,3d,4h,8s,9c', oop_range='AsAd:0.5,KhKd:1',
                      ip_range='AhAc:0.5,KsKc:1', pot=100, stack=200,
                      minimum_bet=2, bet_sizes=[0.5], raise_sizes=[0.5])
        exact = {k: v for k, v in legacy.items() if k not in ('bet_sizes', 'raise_sizes')}
        exact.update(bet_amounts_cents=[5000], raise_to_cents=[15000])
        a = RaiseRiverSolver(**legacy).solve(300, 'AsAd', 'KsKc')
        b = RaiseRiverSolver(**exact).solve(300, 'AsAd', 'KsKc')
        for key in ('hands', 'root_ev_oop_relative_to_split_pot', 'nash_conv_chips', 'terminal_ledgers', 'effective_bet_amounts'):
            self.assertEqual(a[key], b[key])
        self.assertNotIn('sizing_mode', a)
        self.assertIsNone(b['bet_sizes'])

    def test_exact_validation_minimums_short_allins_and_refunds(self):
        for change in ({'bet_amounts_cents': [True]}, {'bet_amounts_cents': [4000.0]},
                       {'bet_amounts_cents': [4000, 4000]}, {'bet_amounts_cents': [30000]},
                       {'bet_amounts_cents': [1]}, {'raise_to_cents': [4000]}, {'raise_to_cents': [7000]},
                       {'raise_to_cents': [12000, 12000]}, {'raise_to_cents': [12000, 30000]},
                       {'raise_to_cents': [12000, 16000, 27500]}, {'raise_to_cents': [27500, 12000]},
                       {'bet_sizes': [0.5]}, {'raise_to_cents': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RaiseRiverSolver(**dict(CONFIG, **change))
        short = RaiseRiverSolver(**dict(CONFIG, stack=60, raise_to_cents=[6000]))
        row = short.locations['c/b4000']['actions'][-1]
        self.assertTrue(row['all_in'])
        self.assertFalse(row['full_raise'])
        self.assertEqual(short.terminals['c/b4000/r2000/f'].refunds, (2000, 0))
        self.assertEqual(short.nodes['c/b4000/r2000'].actions, ('fold', 'call'))
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(RaiseRiverSolver(**CONFIG).stack_cents, 27500)

    def test_exact_independent_reference_and_incompatible_tree_rejection(self):
        result = compare(CONFIG, 400, 800)
        self.assertEqual(result['failures'], [])
        self.assertFalse(result['reference_metadata']['product_modules_loaded'])
        self.assertLessEqual(result['same_policy_max_delta'], 1e-8)
        with self.assertRaisesRegex(ValueError, 'one opening amount'):
            reference_game(dict(CONFIG, bet_amounts_cents=[3000, 4000]))

    def test_plan_prefix_mapping_and_unsupported_cases(self):
        options = dict(river_through=1, raise_to_cents=[12000, 27500])
        plan = prepare_raise_review(HAND, SCENARIOS, **options)
        self.assertEqual(plan['status'], 'not_run')
        q = plan['queries'][0]
        self.assertEqual(q['tree']['target_node'], 'c/b4000')
        self.assertEqual([a['action'] for a in q['tree']['observed_actions']], ['check', 'bet_to_40.00'])
        self.assertEqual(q['arguments']['pot'], 63)
        self.assertEqual(q['arguments']['stack'], 275)
        self.assertEqual(evidence_label(q), 'not solver-verified')
        later = prepare_raise_review(HAND, SCENARIOS, river_through=2)
        self.assertEqual(later['queries'][0]['tree']['target_node'], 'c/b4000/r8000')
        self.assertEqual(later['queries'][0]['arguments']['raise_to_cents'], [12000])
        for opts in ({}, dict(river_through=1), dict(river_through=2, raise_to_cents=[27500]),
                     dict(river_through=1, raise_to_cents=[12000, 12000])):
            rejected = prepare_raise_review(HAND, SCENARIOS, **opts)
            self.assertEqual(rejected['queries'], [])
            self.assertEqual(rejected['status'], 'not_run')
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(plan, prepare_raise_review(HAND, SCENARIOS, **options))
        lead = copy.deepcopy(HAND)
        lead['streets'][-1]['actions'] = [dict(player='HJ', action='bet', amount=40),
                                         dict(player='BTN', action='raise', to=120)]
        self.assertEqual(prepare_raise_review(lead, SCENARIOS)['queries'][0]['tree']['target_node'], 'b4000/r8000')

    def test_actual_worker_evidence_reach_and_false_result_rejection(self):
        result = run_raise_review(HAND, SCENARIOS, 300, river_through=1, raise_to_cents=[12000, 27500])
        self.assertEqual(result['status'], 'computed', result)
        q = result['queries'][0]
        self.assertIn('computed locally', evidence_label(q))
        self.assertIn('not locked', render_raise_markdown(result))
        self.assertIn('raise_to_120.00', q['result']['hands']['oop']['node_strategy']['c/b4000']['frequency'])
        self.assertIn('joint_reach_probability', q['result']['nodes']['c/b4000'])
        corrupted = copy.deepcopy(q)
        corrupted['result']['pot'] = 64
        with self.assertRaises(ValueError):
            evidence_label(corrupted)
        for response in ({'status': 'computed', 'result': {}},
                         {'status': 'failed', 'error': {'code': 'TIMEOUT'}},
                         {'status': 'not_run', 'error': {'code': 'INVALID_INPUT'}}):
            with patch('scripts.solve_river_raises.execute', return_value=response):
                failed = run_raise_review(HAND, SCENARIOS, river_through=1, raise_to_cents=[12000])
            self.assertNotEqual(failed['status'], 'computed')
            self.assertNotIn('result', failed['queries'][0])

    def test_opt_in_cli_and_default_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'review'
            cmd = [sys.executable, str(ROOT/'scripts/review_hand.py'), str(ROOT/'examples/hand-review-raises.txt'),
                   '--local-raises', '--river-through', '1', '--raise-to-cents', '12000', '27500',
                   '--scenarios', str(ROOT/'examples/hand-review-raise-scenarios.json'), '--output', str(out)]
            child = subprocess.run(cmd, capture_output=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            plan = json.loads(out.with_suffix('.json').read_text())
            self.assertEqual(plan['status'], 'not_run')
            self.assertEqual(plan['queries'][0]['tool'], 'local_raise_river')
            child = subprocess.run([sys.executable, str(ROOT/'scripts/review_hand.py'),
                                    str(ROOT/'examples/hand-review-raises.txt')], capture_output=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(json.loads(child.stdout)['queries'], [])


if __name__ == '__main__':
    unittest.main()
