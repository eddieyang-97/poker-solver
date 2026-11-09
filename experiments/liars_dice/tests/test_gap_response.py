import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gap_response import FrontierResponse, HistoryLimit
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate
from run_gap_response import (BASE, BUDGETS, EXHAUSTIVE_CAP, METHODS, WIDTH_TARGET, TableTarget,
                              admission, build_search, fixtures, normalized_hash, sha, verify)


class GapResponseTests(unittest.TestCase):
    def test_checkpoint_and_history_cap_preserve_policy_value(self):
        game = OneFace(9)
        guide = ProbabilityGuide(game)
        target = TableTarget(game, lambda h: np.full(
            (len(game.hands), len(game.actions(h))), 1/len(game.actions(h))))
        exact = evaluate(game, target.policy)
        baseline = FrontierResponse(game, guide, target, 0, 1).solve()
        histories = baseline['stats']['generated_histories']
        for method in ('gap', 'reach'):
            search = FrontierResponse(game, guide, target, 0, 128, method, max_histories=histories)
            first = search.advance(1)
            final = search.solve()
            self.assertEqual(final['stop'], 'history_cap')
            self.assertEqual(final['stats']['generated_histories'], histories)
            self.assertGreaterEqual(final['lower'], first['lower']-1e-12)
            self.assertLessEqual(final['upper'], first['upper']+1e-12)
            verify(search, final, target, exact)
        for seat in (0, 1):
            incomplete = FrontierResponse(game, guide, target, seat, 4, max_histories=1)
            with self.assertRaises(HistoryLimit):
                incomplete.solve()
            self.assertIsNone(incomplete.result)
            with self.assertRaises(HistoryLimit):
                incomplete.solve()

    def test_archived_and_generated_fixtures(self):
        report = json.loads((BASE/'outputs/gap-response.json').read_text())
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['node_caps'], [*BUDGETS, EXHAUSTIVE_CAP])
        for name, digest in report['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(normalized_hash(BASE/'outputs/recall-ablation.json'), report['ablation_receipt_sha256_lf'])
        self.assertEqual(admission(report['cases']), report['admission'])
        self.assertEqual(len(report['cases']), 6)
        for row, (label, guide, target) in zip(report['cases'], fixtures(), strict=True):
            self.assertEqual(row['target_probabilities_sha256'], target.fingerprint())
            self.assertEqual(row['seed'], label['seed'])
            if 'artifact' in row:
                artifact = row['artifact']
                self.assertEqual(sha((BASE/'outputs'/artifact['file']).read_bytes()), artifact['sha256'])
            exact = evaluate(target.game, target.policy)
            self.assertEqual([s['seat'] for s in row['seats']], [0, 1])
            for record in row['seats']:
                seat = record['seat']
                for method in METHODS:
                    prior_lower, prior_upper = -1., 1.
                    for bound, cap in zip(record['checkpoints'][method], report['node_caps'], strict=True):
                        self.assertLessEqual(bound['stats']['expanded_own_nodes'], cap)
                        self.assertLess(bound['realization_error'], 1e-10)
                        self.assertGreaterEqual(bound['lower'], prior_lower-1e-10)
                        self.assertLessEqual(bound['upper'], prior_upper+1e-10)
                        self.assertLessEqual(bound['lower'], exact[f'br{seat}']+1e-10)
                        self.assertGreaterEqual(bound['upper'], exact[f'br{seat}']-1e-10)
                        prior_lower, prior_upper = bound['lower'], bound['upper']
                    self.assertAlmostEqual(prior_upper, prior_lower, places=10)
                    matched = record['width_target_checkpoints'][method]
                    self.assertLessEqual(matched['width'], WIDTH_TARGET)
                    if matched['max_nodes'] > 1:
                        preceding = build_search(method, guide, target, seat, matched['max_nodes']-1).solve()
                        self.assertGreater(preceding['width'], WIDTH_TARGET)
                fresh = FrontierResponse(target.game, guide, target, seat, 16)
                for cap, stored in zip(BUDGETS, record['checkpoints']['gap'][:-1], strict=True):
                    current = fresh.advance(cap)
                    self.assertAlmostEqual(current['lower'], stored['lower'], places=10)
                    self.assertAlmostEqual(current['upper'], stored['upper'], places=10)
                verify(fresh, current, target, exact)


if __name__ == '__main__':
    unittest.main()
