from functools import lru_cache
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import Game
from guidance import ProbabilityGuide
from one_face import OneFace
from recall_training import Layout, RecallTrainer
from response_refinement import CachedRecallModel
from revealed_frontier import RevealedUpper, oracle_resources
from run_gap_response import BASE, TOL, TableTarget, normalized_hash
from run_revealed_frontier import CAPS, METHODS, decision


class RevealedFrontierTests(unittest.TestCase):
    def test_full_history_and_cached_values_against_scalar_deal_oracle(self):
        game = OneFace(7)
        game.rank = int
        guide = ProbabilityGuide(game)
        n = len(game.hands)
        rng = np.random.default_rng(490101)

        def random_rows(history):
            rows = rng.uniform(.01, 1., (n, len(game.actions(history))))
            return rows / rows.sum(axis=1, keepdims=True)

        full = TableTarget(game, random_rows)
        trainer = RecallTrainer(game, 490101)
        trainer.average[:] = rng.uniform(.01, 1., trainer.average.shape)
        frozen = trainer.freeze()
        sparse = np.asarray(game.prior) * np.array([.8, 0., .01, 0., .4, 0., .2])
        for model in (full, CachedRecallModel(frozen)):
            for seat in (0, 1):
                scalar = model.target.policy

                @lru_cache(None)
                def brute(history, own, opp):
                    actor = len(history) % 2
                    hands = (own, opp) if seat == 0 else (opp, own)
                    children = [((1 if seat == 0 else -1) * game.payoff(history, hands, actor))
                                if action == -1 else brute(history+(action,), own, opp)
                                for action in game.actions(history)]
                    if actor == seat:
                        return max(children)
                    return sum(a*b for a, b in zip(scalar(actor, opp, history), children, strict=True))

                oracle = RevealedUpper(game, model, guide, seat)
                with self.assertRaises(MemoryError):
                    RevealedUpper(game, model, guide, seat, max_bytes=1)
                with self.assertRaises(MemoryError):
                    RevealedUpper(game, model, guide, seat, max_pair_edges=1)
                self.assertEqual(oracle.resources['recall'], 1 if model is not full else None)
                for h in full.rows:
                    expected = np.array([[brute(h, own, opp) for opp in range(n)] for own in range(n)])
                    np.testing.assert_allclose(oracle.matrix(h), expected, atol=1e-14, rtol=0)
                    np.testing.assert_allclose(oracle.upper(h, sparse), expected @ sparse, atol=1e-14, rtol=0)
                if model is full and seat == 1:
                    self.assertFalse(np.array_equal(oracle.matrix((3, 6)), oracle.matrix((4, 6))))
                if model is not full:
                    self.assertTrue(np.shares_memory(oracle.matrix((3, 6)), oracle.matrix((4, 6))))

    def test_recorded_frontier_curves_and_admission(self):
        report = json.loads((BASE/'outputs/revealed-frontier.json').read_text())
        previous_path = BASE/'outputs/gap-response.json'
        previous = json.loads(previous_path.read_text())
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['gap_receipt_sha256_lf'], normalized_hash(previous_path))
        self.assertEqual(report['caps'], list(CAPS))
        for name, digest in report['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(decision(report['cases'], report['timing']), report['admission'])
        full = Game()
        self.assertEqual(oracle_resources(Layout(full).graph, len(full.hands)), report['full_rule_static_inventory'])
        for case, prior in zip(report['cases'], previous['cases'], strict=True):
            self.assertEqual(case['target_probabilities_sha256'], prior['target_probabilities_sha256'])
            self.assertEqual([row['seat'] for row in case['seats']], [0, 1])
            for row in case['seats']:
                seat = row['seat']
                br = prior['independent'][f'br{seat}']
                self.assertGreaterEqual(row['revealed_root_upper'], br-TOL)
                for method in METHODS:
                    lo, hi = -1., 1.
                    for cap, point in zip(CAPS, row['curves'][method], strict=True):
                        self.assertLessEqual(point['stats']['expanded_own_nodes'], cap)
                        self.assertGreaterEqual(point['lower'], lo-TOL)
                        self.assertLessEqual(point['upper'], hi+TOL)
                        self.assertLessEqual(point['lower'], br+TOL)
                        self.assertGreaterEqual(point['upper'], br-TOL)
                        self.assertLess(point['realization_error'], TOL)
                        lo, hi = point['lower'], point['upper']
                    self.assertAlmostEqual(lo, hi, places=10)
                    self.assertLessEqual(row['width_target'][method]['width'], report['width_target'])
                for a, b in zip(row['curves']['prepared'][1:],
                                prior['seats'][seat]['checkpoints']['gap'], strict=True):
                    self.assertAlmostEqual(a['lower'], b['lower'], places=10)
                    self.assertAlmostEqual(a['upper'], b['upper'], places=10)


if __name__ == '__main__':
    unittest.main()
