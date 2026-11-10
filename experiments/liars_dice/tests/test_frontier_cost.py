import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier_cost import FactoredReply, LazyUpper
from guidance import ProbabilityGuide
from one_face import OneFace
from recall_training import RecallTrainer
from response_refinement import CachedRecallModel
from revealed_frontier import RevealedUpper
from run_frontier_cost import METHODS, compare
from run_gap_response import BASE, TOL, TableTarget, normalized_hash


class FrontierCostTests(unittest.TestCase):
    def test_lazy_matrix_and_reply_cutoff_against_independent_payoff(self):
        game = OneFace(7)
        game.rank = int
        n = len(game.hands)
        guide = ProbabilityGuide(game)
        rng = np.random.default_rng(490111)

        def random_rows(history):
            rows = rng.uniform(.05, 1., (n, len(game.actions(history))))
            return rows / rows.sum(axis=1, keepdims=True)

        full = TableTarget(game, random_rows)
        trainer = RecallTrainer(game, 490111)
        trainer.average[:] = rng.uniform(.05, 1., trainer.average.shape)
        for model in (full, CachedRecallModel(trainer.freeze())):
            for seat in (0, 1):
                lazy = LazyUpper(game, model, guide, seat)
                reply = LazyUpper(game, model, guide, seat, reply_only=True)
                factored = FactoredReply(game, model, guide, seat)
                dense = RevealedUpper(game, model, guide, seat)
                with self.assertRaises(MemoryError):
                    LazyUpper(game, model, guide, seat, max_bytes=1).matrix(())
                exhausted = LazyUpper(game, model, guide, seat, max_pair_edges=1)
                with self.assertRaises(MemoryError):
                    exhausted.matrix(())
                self.assertEqual(exhausted.resources()['cached_matrices'], 0)
                for h in full.rows:
                    np.testing.assert_array_equal(lazy.matrix(h), dense.matrix(h))
                    if len(h) % 2 != seat:
                        continue
                    expected = np.empty((n, n))
                    for a in range(n):
                        for b in range(n):
                            hands = (a, b) if seat == 0 else (b, a)
                            options = []
                            for action in game.actions(h):
                                if action == -1:
                                    options.append((1-2*seat)*game.payoff(h, hands, seat))
                                    continue
                                prefix = h+(action,)
                                other = 1-seat
                                probabilities = model.target.policy(other, b, prefix)
                                options.append(sum(
                                    w*((1-2*seat)*game.payoff(prefix, hands, other) if move == -1 else 1.)
                                    for w, move in zip(probabilities, game.actions(prefix), strict=True)))
                            expected[a, b] = max(options)
                    np.testing.assert_allclose(reply.matrix(h), expected, atol=1e-14, rtol=0)
                    np.testing.assert_allclose(factored.matrix(h), expected, atol=1e-14, rtol=0)
                    mass = np.asarray(game.prior) * (np.arange(n) % 2)
                    np.testing.assert_allclose(factored.upper(h, mass), expected @ mass, atol=1e-14, rtol=0)
                    self.assertTrue((reply.matrix(h) >= dense.matrix(h)-1e-14).all())

    def test_recorded_comparison_and_numerical_invariants(self):
        path = BASE/'outputs/revealed-frontier.json'
        old = json.loads(path.read_text())
        result = json.loads((BASE/'outputs/frontier-cost.json').read_text())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['revealed_receipt_sha256_lf'], normalized_hash(path))
        for name, digest in result['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(compare(result['cases'], result['timing']), result['admission'])
        for case, prior in zip(result['cases'], old['cases'], strict=True):
            self.assertEqual(case['target_probabilities_sha256'], prior['target_probabilities_sha256'])
            for row in case['seats']:
                br = prior['independent'][f'br{row["seat"]}']
                for method in METHODS:
                    lo, hi = -1., 1.
                    for cap, point in zip(result['caps'], row['curves'][method], strict=True):
                        self.assertLessEqual(point['stats']['expanded_own_nodes'], cap)
                        self.assertGreaterEqual(point['lower'], lo-TOL)
                        self.assertLessEqual(point['upper'], hi+TOL)
                        self.assertLessEqual(point['lower'], br+TOL)
                        self.assertGreaterEqual(point['upper'], br-TOL)
                        self.assertLess(point['realization_error'], TOL)
                        lo, hi = point['lower'], point['upper']
                    self.assertAlmostEqual(lo, hi, places=10)
                    self.assertLessEqual(row['width_target'][method]['width'], result['width_target'])


if __name__ == '__main__':
    unittest.main()
