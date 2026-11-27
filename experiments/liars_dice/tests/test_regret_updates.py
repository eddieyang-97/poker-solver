import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recall_bridge import BRIDGE_QUANTITIES, BridgeEvaluator, BridgeGame, BridgeLayout, BridgeTrainer
from recall_training import RecallPolicy
from regret_updates import VARIANTS, RegretUpdateTrainer
from run_regret_updates import BASE, RECALLS, SEEDS, TARGETS, digest, summarize
from run_recall_bridge import profile_sampler
from run_stratified_holdout import dense_increments
from test_stratified_holdout import replay_score


class RegretUpdateTests(unittest.TestCase):
    def test_signed_methods_share_regret_and_linear_average_uses_block_weight(self):
        game = BridgeGame(2)
        sampler = profile_sampler(game)
        control = BridgeTrainer(game, 1, 17)
        uniform = RegretUpdateTrainer(game, 1, 17, 'signed-uniform')
        linear = RegretUpdateTrainer(game, 1, 17, 'signed-linear')
        expected_average = np.zeros_like(linear.average)
        for t in range(1, 9):
            hands = sampler(control.rng)
            expected_average += t * dense_increments(control, hands)[1]
            for trainer in (control, uniform, linear):
                trainer.step(hands)
            np.testing.assert_array_equal(control.regret, uniform.regret)
            np.testing.assert_array_equal(control.average, uniform.average)
            np.testing.assert_array_equal(control.regret, linear.regret)
            np.testing.assert_allclose(expected_average, linear.average, rtol=2e-15, atol=1e-15)
            np.testing.assert_array_equal(linear.visits, control.visits)

    def test_plus_clips_once_after_duplicate_contributions(self):
        trainer = RegretUpdateTrainer(BridgeGame(2), 1, 33, 'plus-linear', size=2)
        widths = [len(actions) for actions in trainer.layout.graph.actions]
        delta = [np.zeros((2, width)) for width in widths]
        average = [np.zeros((2, width)) for width in widths]
        delta[0][:, :2] = [[-3, -2], [2, 4]]
        average[0][:, 0] = [1, 2]
        trainer.regret[0] = .5
        trainer.regret[widths[0]] = 11.
        trainer.iterations = 3
        with patch.object(trainer, 'batch_increments', return_value=(delta, average, .25, 1.)):
            self.assertEqual(trainer.step(([0, 0], [1, 2])), .25)
        np.testing.assert_array_equal(trainer.regret[:2], [0., 2.])
        self.assertEqual(trainer.regret[widths[0]], 11.)
        self.assertEqual(trainer.average[0], 12.)
        self.assertEqual(trainer.visits[0, 0], 2)
        self.assertEqual(trainer.iterations, 4)
        with self.assertRaises(ValueError):
            trainer.step(([0, 252], [1, 2]))
        self.assertEqual(trainer.iterations, 4)

    def test_recorded_scores_final_tables_and_checkpoint_replay(self):
        out = BASE/'outputs'
        report = json.loads((out/'regret-updates.json').read_text(encoding='utf-8'))
        self.assertEqual(report['summary'], summarize(report['curves']))
        for name, expected in report['source_sha256_lf'].items():
            self.assertEqual(digest((BASE/name).read_bytes().replace(b'\r\n', b'\n')), expected)
        self.assertCountEqual([(c['quantity'], c['recall'], c['seed']) for c in report['curves']],
                              [(q, r, seed) for q in BRIDGE_QUANTITIES for r in RECALLS for seed in SEEDS])
        games = {q: BridgeGame(q) for q in BRIDGE_QUANTITIES}
        layouts = {(q, r): BridgeLayout(game, r) for q, game in games.items() for r in RECALLS}
        evaluators = {q: BridgeEvaluator(game) for q, game in games.items()}
        for row in report['fixtures']:
            game = games[row['quantity']]
            self.assertEqual(row['bid_ids'], list(game.selected))
            self.assertEqual(row['hand_order'], profile_sampler(game).order)
        path = out/report['archive']
        self.assertEqual(digest(path.read_bytes()), report['archive_sha256'])
        names = []
        with np.load(path, allow_pickle=False) as policies:
            for curve in report['curves']:
                q, recall, seed = curve['quantity'], curve['recall'], curve['seed']
                self.assertCountEqual(curve['variants'], VARIANTS)
                for variant, rows in curve['variants'].items():
                    self.assertEqual([row['target_cpu'] for row in rows], list(TARGETS))
                    blocks = 0
                    for row in rows:
                        self.assertGreater(row['blocks'], blocks)
                        self.assertGreaterEqual(row['training_cpu'], row['target_cpu'])
                        self.assertLessEqual(row['blocks'], report['training_block_cap'])
                        self.assertLessEqual(row['training_wall'], report['training_wall_cap'])
                        blocks = row['blocks']
                    final = rows[-1]
                    names.append(final['policy'])
                    data = policies[final['policy']]
                    self.assertEqual(digest(data.tobytes()), final['policy_sha256'])
                    policy = RecallPolicy(layouts[q, recall], data)
                    for key, actual in evaluators[q].evaluate(policy).items():
                        self.assertAlmostEqual(actual, final['score'][key], places=12)
                    if (q, recall, seed, variant) == (2, 2, SEEDS[0], 'plus-linear'):
                        for key, actual in replay_score(games[q], policy).items():
                            self.assertAlmostEqual(actual, final['score'][key], places=12)
                        trainer = RegretUpdateTrainer(games[q], recall, seed, variant)
                        sampler = profile_sampler(games[q])
                        for _ in range(rows[0]['blocks']):
                            trainer.step(sampler(trainer.rng))
                        for key, actual in evaluators[q].evaluate(trainer.freeze()).items():
                            self.assertAlmostEqual(actual, rows[0]['score'][key], places=11)
            self.assertCountEqual(names, policies.files)


if __name__ == '__main__':
    unittest.main()
