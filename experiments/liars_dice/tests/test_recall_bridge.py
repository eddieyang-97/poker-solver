import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import Bid, Game, hand_distribution
from recall_bridge import BRIDGE_QUANTITIES, RECALLS, BridgeEvaluator, BridgeGame, BridgeLayout, BridgeTrainer
from recall_training import RecallPolicy
from run_recall_bridge import BASE, METHODS, SEEDS, TARGETS, digest, profile_sampler, summarize
from test_stratified_holdout import replay_score


class RecallBridgeTests(unittest.TestCase):
    def test_exact_hands_and_retained_action_legality(self):
        full = Game()
        for q in BRIDGE_QUANTITIES:
            game = BridgeGame(q)
            self.assertEqual(game.bids, (*(Bid(3, f, 'fly') for f in range(1, 7)),
                                         Bid(q, 2, 'zhai'), Bid(q, 4, 'zhai'),
                                         Bid(q+2, 2, 'fly'), Bid(q+2, 4, 'fly')))
            self.assertEqual(tuple(zip(game.hands, game.weights)), hand_distribution())
            self.assertEqual(sum(game.weights), 7776)
            np.testing.assert_array_equal(game.counts, np.asarray(full.counts)[:, list(game.selected)])
            for last in ((), *((a,) for a in range(len(game.bids)))):
                mapped = tuple(-1 if a == -1 else game.selected[a] for a in game.actions(last))
                expected = full.actions(tuple(game.selected[a] for a in last))
                self.assertEqual(mapped, tuple(a for a in expected if a == -1 or a in game.selected))

    def test_challenge_tails_match_direct_deal_payoffs(self):
        game = BridgeGame(2)
        evaluator = BridgeEvaluator(game)
        reach = np.asarray(game.prior) * np.linspace(0., 1., len(game.hands))
        reach[::3] = 0.
        for bid in range(len(game.bids)):
            expected = [sum(game.payoff((bid,), (a, b), 1)*p for b, p in enumerate(reach) if p)
                        for a in range(len(reach))]
            np.testing.assert_allclose(evaluator.claim_values(bid, reach), expected, atol=2e-15, rtol=0)
            np.testing.assert_array_equal(evaluator.claim_values(bid, np.zeros_like(reach)), np.zeros_like(reach))

    def test_archive_policies_full_history_and_count_replay(self):
        out = BASE/'outputs'
        report = json.loads((out/'recall-bridge.json').read_text(encoding='utf-8'))
        self.assertEqual(report['summary'], summarize(report['curves']))
        for name, expected in report['source_sha256_lf'].items():
            self.assertEqual(digest((BASE/name).read_bytes().replace(b'\r\n', b'\n')), expected)
        self.assertCountEqual([(c['quantity'], c['recall'], c['seed']) for c in report['curves']],
                              [(q, r, s) for q in BRIDGE_QUANTITIES for r in RECALLS for s in SEEDS])
        games = {q: BridgeGame(q) for q in BRIDGE_QUANTITIES}
        layouts = {(q, r): BridgeLayout(game, r) for q, game in games.items() for r in RECALLS}
        evaluators = {q: BridgeEvaluator(game) for q, game in games.items()}
        for row in report['fixtures']:
            q = row['quantity']
            self.assertEqual(row['state_counts'], [len(layouts[q, r].graph.keys) for r in RECALLS])
            self.assertEqual(row['profile_order'], profile_sampler(games[q]).order)
            self.assertEqual(row['bid_ids'], list(games[q].selected))
        path = out/report['archive']
        self.assertEqual(digest(path.read_bytes()), report['archive_sha256'])
        seen = []
        with np.load(path, allow_pickle=False) as policy_tables:
            for curve in report['curves']:
                q, recall, seed = curve['quantity'], curve['recall'], curve['seed']
                self.assertCountEqual(curve['methods'], METHODS)
                for method, rows in curve['methods'].items():
                    self.assertEqual([row['target_cpu'] for row in rows], list(TARGETS))
                    self.assertEqual([row['policy'] for row in rows[:-1]], [None]*(len(TARGETS)-1))
                    previous_blocks = 0
                    for row in rows:
                        self.assertGreaterEqual(row['training_cpu'], row['target_cpu'])
                        self.assertLessEqual(row['training_wall'], report['training_wall_cap'])
                        self.assertLess(previous_blocks, row['blocks'])
                        self.assertLessEqual(row['blocks'], report['training_block_cap'])
                        self.assertTrue(all(0 <= n <= 252 for n in row['hand_count']))
                        self.assertTrue(all(0 <= a <= b for a, b in
                                            zip(row['positive_average_rows'], row['total_multi_action_rows'], strict=True)))
                        previous_blocks = row['blocks']
                    final = rows[-1]
                    seen.append(final['policy'])
                    data = policy_tables[final['policy']]
                    self.assertEqual(digest(data.tobytes()), final['policy_sha256'])
                    policy = RecallPolicy(layouts[q, recall], data)
                    actual = evaluators[q].evaluate(policy)
                    for key, value in actual.items():
                        self.assertAlmostEqual(value, final['score'][key], places=12)
                    if seed == SEEDS[-1] and (q, recall, method) in ((2, 2, 'iid'), (3, None, 'profile')):
                        expected = replay_score(games[q], policy)
                        for key, value in actual.items():
                            self.assertAlmostEqual(value, expected[key], places=12)
                    if (q, recall, seed, method) == (3, 3, SEEDS[0], 'profile'):
                        trainer = BridgeTrainer(games[q], recall, seed)
                        sample = profile_sampler(games[q])
                        first = rows[0]
                        for _ in range(first['blocks']):
                            trainer.step(sample(trainer.rng))
                        replay = evaluators[q].evaluate(trainer.freeze())
                        for key, value in replay.items():
                            self.assertAlmostEqual(value, first['score'][key], places=11)
            self.assertCountEqual(seen, policy_tables.files)


if __name__ == '__main__':
    unittest.main()
