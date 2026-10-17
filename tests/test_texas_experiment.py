import copy
import json
from pathlib import Path
import unittest

from benchmarks.texas import LOOKUP_SHA256, SOURCE_COMMIT
from benchmarks.texas_blockers import load_blocker_fixture
from benchmarks.texas_experiment import SOURCE_LOOKUP_SHA256_LF, analyze, experiment_commands, replace_once


class TexasExperimentTests(unittest.TestCase):
    def test_patch_anchor_rejects_missing_and_ambiguous_source(self):
        for text in ('missing', 'anchor anchor'):
            with self.assertRaises(ValueError):
                replace_once(text, 'anchor', 'changed')

    @staticmethod
    def synthetic_execution():
        # These are test inputs made from recorded release policies, not source-build evidence.
        record = json.loads((Path(__file__).resolve().parents[1] / 'docs/texas-blocker-results.json').read_text())
        points = [{'iterations': n, 'exploitability_percent': 0.5,
                   'average': run['strategy'], 'current': run['strategy']}
                  for n, run in zip((4000, 40000), record['execution']['runs'], strict=True)]
        return {'build': {'source_commit': SOURCE_COMMIT, 'lookup_sha256': LOOKUP_SHA256,
                          'lookup_sha256_lf': SOURCE_LOOKUP_SHA256_LF},
                'fixture': load_blocker_fixture(),
                'variants': {name: {'input_commands': experiment_commands(), 'checkpoints': copy.deepcopy(points)}
                             for name in ('baseline_observer', 'theta_one')}}

    def test_identical_profiles_do_not_establish_averaging_effect(self):
        report = analyze(self.synthetic_execution())
        self.assertFalse(report['averaging_effect_observed_with_matching_current_policies'])
        self.assertEqual(report['max_current_policy_difference_between_variants'], 0)
        self.assertTrue(all(row['status'] == 'FAIL' for row in report['rows']))

    def test_comparison_rejects_misaligned_or_changed_game_evidence(self):
        for change in ('checkpoint', 'commands', 'fixture', 'nonfinite'):
            record = self.synthetic_execution()
            data = record['variants']['theta_one']
            if change == 'checkpoint':
                data['checkpoints'][0]['iterations'] += 1
            elif change == 'commands':
                data['input_commands'] += 'set_bet_sizes ip,river,raise,50\n'
            elif change == 'fixture':
                record['fixture']['ip'][0]['weight'] = 0.2
            else:
                data['checkpoints'][0]['exploitability_percent'] = float('nan')
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze(record)

    def test_changed_current_trajectory_prevents_isolated_effect_claim(self):
        record = self.synthetic_execution()
        baseline = record['variants']['baseline_observer']['checkpoints']
        baseline[-1]['average'] = copy.deepcopy(baseline[0]['average'])
        # Synthetic average-only improvement while current policies still match.
        self.assertTrue(analyze(record)['averaging_effect_observed_with_matching_current_policies'])
        changed = record['variants']['theta_one']['checkpoints']
        changed[-1]['current'] = copy.deepcopy(changed[0]['current'])
        report = analyze(record)
        self.assertGreater(report['max_current_policy_difference_between_variants'], 0)
        self.assertFalse(report['averaging_effect_observed_with_matching_current_policies'])

    def test_actual_source_build_evidence_preserves_baseline_and_isolates_average(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root / 'docs/texas-averaging-results.json').read_text())
        report = analyze(evidence['execution'])
        self.assertEqual(report['iterations_checked'], list(range(4000, 40001, 4000)))
        self.assertEqual(report['max_current_policy_difference_between_variants'], 0)
        self.assertTrue(report['averaging_effect_observed_with_matching_current_policies'])
        for row, saved in zip(report['rows'], evidence['analysis']['rows'], strict=True):
            # Same serialized policies evaluated again, not a cross-engine convergence tolerance.
            self.assertAlmostEqual(row['nashconv'], saved['nashconv'], delta=1e-9)
            self.assertAlmostEqual(row['oop_ev'], saved['oop_ev'], delta=1e-9)
            expected = 'PASS' if row['variant'] == 'theta_one' and row['policy'] == 'average' else 'FAIL'
            self.assertEqual(row['status'], expected)
            if row['policy'] == 'average':
                # Same £0.000051 output-precision allowance used by the admitted pilot.
                self.assertLess(row['source_vs_independent_gap_delta'], 0.000051)
        release = json.loads((root / 'docs/texas-blocker-results.json').read_text())
        baseline = evidence['execution']['variants']['baseline_observer']['checkpoints']
        for point, original in zip((baseline[0], baseline[-1]), release['execution']['runs'], strict=True):
            self.assertEqual(point['average'], original['strategy'])
        for variant in evidence['execution']['variants'].values():
            self.assertEqual(variant['post_statistics_final_policy'], variant['checkpoints'][-1]['average'])


if __name__ == '__main__':
    unittest.main()
