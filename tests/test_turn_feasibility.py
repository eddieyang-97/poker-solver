import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from benchmarks.turn_feasibility import (
    candidate_input, digest, full_record, games, identity, pack, unpack, validate_record, view,
)
from poker_spot.turn import TurnSolver
from scripts.benchmark_turn_feasibility import coverage, probe


class TurnFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = {'board': 'Js,Ts,2c,3d', 'oop_range': 'AsKs', 'ip_range': 'QhQd',
                      'pot': 100, 'stack': 150, 'turn_bet_sizes': [0.5], 'river_bet_sizes': [0.5]}
        cls.solver = TurnSolver(**cls.config)
        cls.result = cls.solver.solve(200, 'AsKs', 'QhQd')
        cls.record = full_record(cls.solver, cls.result)

    def test_complete_policy_output_views_match_direct_solver(self):
        record = validate_record(self.record, self.solver, 200)
        for side, label in enumerate(('oop', 'ip')):
            actual = view(record, self.solver, side, ''.join(self.solver.hands[side][0]))
            self.assertEqual(actual, self.result['hands'][label])
            filtered = view(record, self.solver, side, ''.join(self.solver.hands[side][0]), '4c')
            expected = {k: v for k, v in actual['node_strategy'].items() if '@' not in k or k.endswith('@4c')}
            self.assertEqual(filtered['node_strategy'], expected)
        self.assertEqual(len(record['rivers']), 48)
        # Hero's own two cards remain explicit zero-support rows in the full tensor.
        self.assertTrue(any(None in np.asarray(r['ev'], dtype=object).flat for r in record['nodes'].values()))

    def test_integrity_version_tree_support_and_nonconvergence_rejected(self):
        blob = pack(self.record)
        checksum = hashlib.sha256(blob).hexdigest()
        self.assertEqual(unpack(blob, checksum, self.solver, 200), self.record)
        with self.assertRaisesRegex(ValueError, 'Corrupt'):
            unpack(blob+b'x', checksum, self.solver, 200)
        mutations = [lambda r: r['identity'].update(version='stale'),
                     lambda r: r['nodes'].pop('turn'),
                     lambda r: r['nodes']['turn'].update(actions=['check', 'bet_51']),
                     lambda r: r['nodes']['turn'].update(frequency=[[0.1, 0.1]]),
                     lambda r: r['nodes']['turn'].update(ev=[[None, None]]),
                     lambda r: r['nodes']['turn'].update(own=[-1]),
                     lambda r: r['diagnostics'].update(nash_conv_pct_pot=0.5001)]
        for mutation in mutations:
            record = copy.deepcopy(self.record)
            mutation(record)
            with self.assertRaises(ValueError):
                validate_record(record, self.solver, 200)

    def test_multiple_hands_views_keep_indices_and_future_cards_separate(self):
        config = games()[0]['config']
        for index in (0, 1):
            solver = TurnSolver(**config)
            hands = [''.join(side[index]) for side in solver.hands]
            direct = solver.solve(100, *hands)
            record = full_record(solver, direct)
            for side, label in enumerate(('oop', 'ip')):
                self.assertEqual(view(record, solver, side, hands[side]), direct['hands'][label])

    def test_keys_bind_complete_games_not_views_or_partial_marginals(self):
        original = digest(identity(self.solver, 200))
        for key, value in (('pot', 101), ('stack', 151), ('oop_range', 'AsKs:0.5'),
                           ('board', 'Js,Ts,2c,4d'), ('turn_bet_sizes', [1]), ('river_bet_sizes', [1])):
            config = dict(self.config, **{key: value})
            self.assertNotEqual(digest(identity(TurnSolver(**config), 200)), original)
        self.assertNotEqual(digest(identity(self.solver, 201)), original)
        view(self.record, self.solver, 0, 'AsKs', '4c')
        self.assertEqual(digest(identity(self.solver, 200)), original)

    def test_candidate_envelope_rejects_unvalidated_classes(self):
        self.assertTrue(candidate_input(self.solver, 2000))
        self.assertFalse(candidate_input(self.solver, 500))
        self.assertFalse(candidate_input(TurnSolver(**dict(self.config, oop_range='AsKs,AhKh,AcKc')), 2000))
        self.assertFalse(candidate_input(TurnSolver(**dict(self.config, turn_bet_sizes=[0.5, 1])), 2000))
        wide = TurnSolver(**dict(self.config, oop_range='AA'))
        self.assertGreater(len(wide.hands[0]), 4)
        self.assertFalse(candidate_input(wide, 2000))
        for bad in ({'oop_range': 'AA,KK,QQ,JJ,TT,99'}, {'turn_bet_sizes': [0.5, 1, 2]},
                    {'oop_range': 'AsKs', 'ip_range': 'AsQd'}):
            with self.assertRaises(ValueError):
                TurnSolver(**dict(self.config, **bad))

    def test_declared_coverage_separates_constructed_reuse_from_changed_games(self):
        cases = games()
        catalog = {digest(identity(TurnSolver(**c['config']), c['iterations'])) for c in cases}
        result = coverage(cases, catalog)
        self.assertEqual((result['synthetic_hits'], result['total'], result['held_out_hits']), (15, 23, 0))
        self.assertTrue(all(q['status'] == 'not_found' for q in result['queries'] if q['kind'].startswith('held_out')))
        self.assertIn('not measured user demand', result['warning'])

    def test_real_timeout_invalid_input_and_successful_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            request = {'config': self.config, 'iterations': 20, 'artifact': str(Path(folder)/'record.gz')}
            timed = probe(request, unlimited=True, wall=0.001)
            self.assertEqual(timed['status'], 'WALL_TIMEOUT')
            self.assertTrue(timed['killed_and_reaped'])
            self.assertNotIn('diagnostics', timed)
            invalid = probe(dict(request, iterations=19), unlimited=True)
            self.assertEqual(invalid['status'], 'ERROR')
            self.assertIn('iterations', invalid['failure'])
            recovered = probe(request, unlimited=True)
            self.assertEqual(recovered['status'], 'COMPLETED', recovered)
            self.assertIsNone(recovered['limits'])
            self.assertNotIn('budget_fit', recovered)
            self.assertEqual(recovered['key'], digest(identity(self.solver, 20)))
            self.assertGreater(recovered['artifact_bytes'], 0)
            request['sha256'] = '0'*64
            request['views'] = [{'side': 0, 'hand': 'AsKs'}]
            corrupt = probe(request, unlimited=True, lookup=True)
            self.assertEqual(corrupt['status'], 'ERROR')
            self.assertIn('Corrupt', corrupt['failure'])
        for wall in (0, 21):
            with self.assertRaises(ValueError):
                probe({}, wall=wall)


if __name__ == '__main__':
    unittest.main()
