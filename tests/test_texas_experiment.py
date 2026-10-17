import copy
import json
from pathlib import Path
import unittest

from benchmarks.texas import LOOKUP_SHA256, SOURCE_COMMIT
from benchmarks.texas_blockers import load_blocker_fixture
from benchmarks.texas_experiment import analyze, experiment_commands, replace_once


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
        return {'build': {'source_commit': SOURCE_COMMIT, 'lookup_sha256': LOOKUP_SHA256},
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


if __name__ == '__main__':
    unittest.main()
