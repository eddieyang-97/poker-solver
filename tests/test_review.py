import asyncio
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from poker_spot.execution import CalculationError
from poker_spot.history import HistoryError, revise_hand
from poker_spot.review import execution_label, hypothesis, prepare_review, render_markdown, run_review

ROOT = Path(__file__).resolve().parents[1]
HAND = json.loads((ROOT/'examples/hand-review.json').read_text())
SCENARIOS = json.loads((ROOT/'examples/hand-review-scenarios.json').read_text())


class ReviewTests(unittest.TestCase):
    def test_exact_requests_and_no_computed_claim_before_execution(self):
        plan = prepare_review(HAND, SCENARIOS)
        self.assertEqual(plan['status'], 'not_run')
        self.assertEqual(len(plan['queries']), 6)
        for q in plan['queries']:
            self.assertEqual(execution_label(q), 'not solver-verified')
            self.assertEqual(q['arguments']['pot'], 87)
            if q['tool'] == 'solve_river':
                self.assertEqual(q['arguments']['stack'], 367)
                self.assertEqual(q['arguments']['bet_sizes'][0]*87, 40)
                self.assertGreater(len(q['arguments']['oop_range'].split(',')), 1)
                self.assertGreater(len(q['arguments']['ip_range'].split(',')), 1)
            else:
                self.assertEqual(q['arguments']['bet'], 40)
                self.assertEqual(q['arguments']['hero_hand'], '7d3d')
        self.assertTrue(plan['scenarios'][0]['arrival']['UTG']['gaps'])
        self.assertIn('not solver-verified', render_markdown(plan))
        self.assertNotIn('Computed equity', render_markdown(plan))

    def test_bayesian_weights_only_use_supplied_complete_likelihoods(self):
        spec = {'range': 'AsAd:1,KhKd:0.5', 'provenance': 'Test explicit prior',
                'updates': [{'event': 'known test action', 'provenance': 'External supplied frequencies',
                             'likelihoods': {'AsAd': 0.25, 'KhKd': 0.5}}]}
        r = hypothesis(spec, ['2c', '3d', '4h', '8s', '9c'])
        self.assertEqual(set(r['weights'].values()), {1.0})
        self.assertEqual({float(w) for w in r['posterior_weights_decimal'].values()}, {0.25})
        unknown = copy.deepcopy(spec)
        unknown['updates'][0]['likelihoods'] = None
        self.assertEqual(sorted(hypothesis(unknown, [])['weights'].values()), [0.5, 1])
        for factors in ({'AsAd': 0.2}, {'AsAd': 1.1, 'KhKd': 0.5}, {'AsAd': True, 'KhKd': 0.5}):
            bad = copy.deepcopy(spec)
            bad['updates'][0]['likelihoods'] = factors
            with self.assertRaises(HistoryError):
                hypothesis(bad, [])

    def test_reveals_do_not_set_opponent_ranges_and_blockers_are_explicit(self):
        first = prepare_review(HAND, SCENARIOS)
        # Only a displayed own-hand query changes. No arrival/betting weights are inferred from reveal.
        changed = revise_hand(HAND, '/players/2/hole_cards', ['9s', '9d'])
        second = prepare_review(changed, SCENARIOS)
        for a, b in zip(first['queries'], second['queries'], strict=True):
            if a['tool'] == 'evaluate_river_call':
                self.assertEqual(a['arguments'], b['arguments'])
            else:
                self.assertEqual(a['arguments']['oop_range'], b['arguments']['oop_range'])
                self.assertEqual(a['arguments']['ip_range'], b['arguments']['ip_range'])
        blocked = hypothesis({'range': 'AcAd,7dAh,KhKd', 'provenance': 'Blocker test'},
                             ['Ac', 'Jh', '3s', 'Tc', '4c'], ['7d', '3d'])
        self.assertEqual((blocked['removed_by_board'], blocked['removed_by_hero']), (1, 1))
        self.assertEqual(list(blocked['weights']), ['KdKh'])

    def test_unsupported_street_and_multiway_do_not_dispatch(self):
        hand = copy.deepcopy(HAND)
        hand['streets'] = hand['streets'][:2]
        self.assertEqual(prepare_review(hand, SCENARIOS)['queries'], [])
        hand['streets'][-1]['actions'] = hand['streets'][-1]['actions'][:3]
        self.assertEqual(prepare_review(hand, SCENARIOS)['queries'], [])
        hand = copy.deepcopy(HAND)
        hand['streets'][1]['actions'][-1] = {'player': 'UTG+1', 'action': 'call', 'amount': 15}
        hand['streets'][2]['actions'].insert(1, {'player': 'UTG+1', 'action': 'check'})
        hand['streets'][3]['actions'] = [{'player': 'UTG', 'action': 'bet', 'amount': 40},
                                        {'player': 'UTG+1', 'action': 'fold'}]
        review = prepare_review(hand, SCENARIOS)
        self.assertEqual(review['queries'], [])
        self.assertIn('began multiway', review['not_run_reason'])

    def test_false_or_failed_computation_never_verified(self):
        with self.assertRaises(HistoryError):
            execution_label({'tool': 'solve_river', 'status': 'computed', 'result': {}})
        with self.assertRaises(HistoryError):
            prepare_review(HAND, [dict(SCENARIOS[0], verified=True)])
        with patch('poker_spot.execution.Runner.run', new=AsyncMock(side_effect=CalculationError('timeout', 'Test timeout'))):
            result = asyncio.run(run_review(HAND, SCENARIOS[:1]))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(all(execution_label(q) == 'not solver-verified' for q in result['queries']))

    def test_actual_bounded_tools_and_material_range_sensitivity(self):
        result = asyncio.run(run_review(HAND, SCENARIOS, 300))
        self.assertEqual(result['status'], 'computed', result)
        self.assertTrue(all(s['status'] == 'computed' for s in result['scenarios']))
        notes = render_markdown(result)
        self.assertIn('oop_facing_ip_bet_', notes)
        self.assertIn('Computed equity', notes)
        self.assertIn('not locked', notes)
        calls = [q for q in result['queries'] if q['tool'] == 'evaluate_river_call']
        self.assertTrue(all(q['result']['caller_pot_odds'] == round(40/167, 6) for q in calls))
        self.assertGreater(calls[2]['result']['ev_call_minus_fold'], calls[1]['result']['ev_call_minus_fold'])
        self.assertNotEqual(calls[2]['result']['best_action_given_range'], calls[1]['result']['best_action_given_range'])
        for q in result['queries']:
            self.assertIn('computed locally', execution_label(q))
            corrupted = dict(q, result={})
            with self.assertRaises(HistoryError):
                execution_label(corrupted)

    def test_effective_allin_query_uses_refunded_excess(self):
        result = prepare_review(revise_hand(HAND, '/players/0/stack', 50), SCENARIOS[:1])
        call = next(q for q in result['queries'] if q['tool'] == 'evaluate_river_call')
        self.assertEqual((call['arguments']['pot'], call['arguments']['bet']), (87, 17))

    def test_two_player_table_big_blind_is_out_of_position(self):
        hand = copy.deepcopy(HAND)
        hand['players'] = [dict(position='SB', stack=400, hole_cards=['8s', '8c'], knowledge='showdown'),
                           dict(position='BB', stack=400, hole_cards=['7d', '3d'], knowledge='hero')]
        hand['streets'][0]['actions'] = [{'player': 'SB', 'action': 'call', 'amount': 1},
                                        {'player': 'BB', 'action': 'check'}]
        for street in hand['streets'][1:3]:
            street['actions'] = [{'player': 'BB', 'action': 'check'}, {'player': 'SB', 'action': 'check'}]
        hand['streets'][3]['actions'] = [{'player': 'BB', 'action': 'check'}, {'player': 'SB', 'action': 'bet', 'amount': 2}]
        scenario = copy.deepcopy(SCENARIOS[0])
        scenario['arrival'] = {'BB': scenario['arrival']['UTG'], 'SB': scenario['arrival']['UTG+2']}
        scenario['betting'] = {'SB': scenario['betting']['UTG+2']}
        result = prepare_review(hand, [scenario])
        solve = result['queries'][0]['arguments']
        self.assertEqual(solve['oop_hand'], '3d7d')
        self.assertEqual(solve['ip_hand'], '8c8s')
        self.assertEqual(solve['pot'], 4)
        self.assertEqual(result['reconstruction']['decision']['actor'], 'BB')

    def test_returned_tree_mismatch_cannot_claim_computed(self):
        fake = {'board': ['Ac', 'Jh', '3s', 'Tc', '4c'], 'effective_bet_amounts': [39]}
        with patch('poker_spot.execution.Runner.run', new=AsyncMock(return_value=fake)):
            result = asyncio.run(run_review(HAND, SCENARIOS[:1]))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(all(q['status'] == 'failed' for q in result['queries']))

    def test_zero_pot_after_explicit_rake_is_not_dispatched(self):
        hand = copy.deepcopy(HAND)
        hand['rake'] = {'model': 'fixed', 'amount': 87, 'street': 'river'}
        report = prepare_review(hand, SCENARIOS)
        self.assertEqual(report['queries'], [])
        self.assertIn('positive river-start pot', render_markdown(report))

    def test_uniform_likelihood_scaling_preserves_dispatch_and_action_evs(self):
        baseline = copy.deepcopy(SCENARIOS[:1])
        conditioned = copy.deepcopy(baseline)
        for player, spec in conditioned[0]['arrival'].items():
            combos = hypothesis(spec, [])['weights']
            spec['updates'] = [{'event': f'Uniform observation {i}', 'provenance': 'Supplied regression probabilities',
                                'likelihoods': dict.fromkeys(combos, 1e-8)} for i in range(2)]
        expected = asyncio.run(run_review(HAND, baseline, 100))
        actual = asyncio.run(run_review(HAND, conditioned, 100))
        self.assertEqual(actual['status'], 'computed', actual)
        for a, b in zip(expected['queries'], actual['queries'], strict=True):
            self.assertEqual(a['arguments'], b['arguments'])
            self.assertEqual(a['result'], b['result'])
        check = actual['queries'][0]['result']['hands']['oop']['node_strategy']['oop_first']
        self.assertIsNotNone(check['action_ev_relative_to_half_pot']['check'])

    def test_uniform_conditioning_below_float_product_range_retains_support(self):
        spec = {'range': 'AsAd:1,KhKd:0.5', 'provenance': 'Underflow regression',
                'updates': [{'event': str(i), 'provenance': 'Supplied uniform observation',
                             'likelihoods': {'AsAd': 1e-200, 'KhKd': 1e-200}} for i in range(3)]}
        self.assertEqual(hypothesis(spec, [])['range'], hypothesis(dict(spec, updates=[]), [])['range'])
        impossible = copy.deepcopy(spec)
        for update in impossible['updates']:
            update['likelihoods']['KhKd'] = 1
        with self.assertRaisesRegex(HistoryError, 'no silent combo removal'):
            hypothesis(impossible, [])
        zero = dict(spec, updates=[{'event': 'Exclude AA', 'provenance': 'Explicit zero likelihood',
                                   'likelihoods': {'AsAd': 0, 'KhKd': 1}}])
        self.assertEqual(list(hypothesis(zero, [])['weights']), ['KdKh'])


if __name__ == '__main__':
    unittest.main()
