import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bounded_response import ResponseSearch
from game import Game, Rules
from guidance import ProbabilityGuide
from one_face import OneFace
from response_kernels import PreparedClaims, PreparedDepthFirst
from run_gap_response import BASE, normalized_hash
from run_response_kernels import MODES, comparison


class PreparedClaimTests(unittest.TestCase):
    def test_prepared_values_match_legacy_and_direct_scoring(self):
        rng = np.random.default_rng(490091)
        for rules in (Rules(), Rules(zhai_mixed_bonus=True, all_ones_wild_seven=False)):
            game = Game(rules)
            guide = ProbabilityGuide(game)
            original = ResponseSearch(game, guide, None, 0)
            prepared = PreparedClaims(guide)
            sparse = np.array(game.prior) * rng.integers(0, 4, len(game.hands)) / 4
            rare = sparse * 1e-100
            for action, col in guide.columns.items():
                count = guide.counts[:, col]
                win = np.add.outer(count, count) >= guide.quantities[col]
                for mass in (sparse, rare, np.zeros_like(sparse)):
                    new = prepared.value(action, mass, False)
                    np.testing.assert_array_equal(new, original._claim_value(action, mass, False))
                    np.testing.assert_array_equal(-new, prepared.value(action, mass, True))
                    np.testing.assert_allclose(new, (2*win-1) @ mass,
                                               atol=1e-14*mass.sum(), rtol=0)

    def test_recorded_fixture_parity_and_admission(self):
        historical_path = BASE/'outputs/gap-response.json'
        historical = json.loads(historical_path.read_text())
        report = json.loads((BASE/'outputs/response-kernels.json').read_text())
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(normalized_hash(historical_path), report['gap_receipt_sha256_lf'])
        for name, digest in report['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(comparison(historical, report['cap16'], report['width_target']), report['admission'])
        for old, new in zip(historical['cases'], report['fixtures'], strict=True):
            self.assertEqual(old['target_probabilities_sha256'], new['probabilities_sha256'])
            self.assertEqual(set(new['parity']), {m for m in MODES if not m.endswith('-original')})
            for result in new['parity'].values():
                self.assertLess(result['max_reference_error'], 1e-10)
                self.assertEqual(len(result['checks']), 12)
                for row in result['checks']:
                    exact = old['independent'][f'br{row["seat"]}']
                    self.assertLessEqual(row['lower'], exact+1e-10)
                    self.assertGreaterEqual(row['upper'], exact-1e-10)
                    self.assertLess(row['replay_error'], 1e-10)

    def test_branch_reach_preserves_exact_ties_and_positive_support(self):
        game = OneFace(8)
        guide = ProbabilityGuide(game)
        n = len(game.hands)
        rows = {6: np.full(n, 0.25), 4: np.full(n, 0.25), 5: np.zeros(n),
                7: np.full(n, 1e-180), 8: np.full(n, 0.5)}
        model = SimpleNamespace(actions=lambda p, h: rows)
        original = ResponseSearch(game, guide, model, 1)
        prepared = PreparedDepthFirst(game, guide, model, 1, 1, PreparedClaims(guide), reuse_reach=True)
        mass = np.asarray(game.prior)
        before, after = (s._branches(0, (), mass) for s in (original, prepared))
        self.assertEqual([action for action, _ in after], [8, 4, 6, 7])
        for (_, old), (_, new) in zip(before, after, strict=True):
            np.testing.assert_array_equal(old, new)
        self.assertEqual(original.stats['opponent_nodes'], prepared.stats['opponent_nodes'])


if __name__ == '__main__':
    unittest.main()
