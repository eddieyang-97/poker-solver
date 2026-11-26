import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import Bid, hand_distribution
from recall_ablation import FixtureLayout
from recall_training import RecallPolicy
from run_stratified_holdout import (
    BASE,
    BLOCK_SIZE,
    CHECKPOINTS,
    FIXTURES,
    MAX_BLOCKS,
    MAX_TRAIN_WALL,
    METHODS,
    MOMENT_BLOCKS,
    MOMENT_SEEDS,
    RECALLS,
    SEEDS,
    AxisFixtureTrainer,
    OrderedDraws,
    digest,
    fixture,
    frozen_block_stats,
    hand_orders,
    summary,
)


class ConstantTicket:
    def __init__(self, value):
        self.value = value

    def randrange(self, limit):
        assert 0 <= self.value < limit
        return self.value


def replay_score(game, policy):
    """Independent full-history pass, with terminal tables built once per bid."""
    prior = np.array(game.prior)
    empty = np.zeros_like(prior)
    terminal = [np.array([[game.payoff((bid,), (a, b), 1) for b in range(len(prior))]
                          for a in range(len(prior))]) for bid in range(len(game.bids))]

    def walk(history, reach):
        seat = len(history) % 2
        probabilities = policy.actions(seat, history)
        ev = np.zeros((len(prior), len(prior)))
        options = []
        for action in game.actions(history):
            strategy = probabilities.get(action, empty)
            next_reach = list(reach)
            next_reach[seat] = reach[seat] * strategy
            if action == -1:
                child = terminal[history[-1]] * (1 if seat == 1 else -1)
                replies = child @ next_reach[1], -(next_reach[0] @ child)
            else:
                child, replies = walk((*history, action), next_reach)
            ev += child * (strategy[:, None] if seat == 0 else strategy[None, :])
            options.append(replies)
        options = np.asarray(options)
        replies = options.sum(axis=0)
        # The responding seat maximizes only after pooling opponent hands.
        replies[seat] = options[:, seat].max(axis=0)
        return ev, replies

    ev, (reply0, reply1) = walk((), (prior, prior))
    ev, br0, br1 = float(prior @ ev @ prior), float(prior @ reply0), float(prior @ reply1)
    return {'ev_p0': ev, 'br0': br0, 'br1': br1, 'gain0': br0-ev, 'gain1': br1+ev,
            'nashconv': br0+br1, 'exploitability': (br0+br1)/2}


class StratifiedHoldoutTests(unittest.TestCase):
    def test_heldout_fixture_lossless_legal_and_weighted(self):
        game = fixture('q2-face6')
        self.assertEqual(len(game.hands), 126)
        self.assertEqual(game.bids[:-1], fixture('q2').bids)
        self.assertEqual(game.bids[-1], Bid(3, 6, 'fly'))
        counts = np.array(game.counts)[list(game.projection)]
        np.testing.assert_array_equal(counts, np.array(game.full.counts)[:, list(game.selected)])
        weights = [0] * len(game.hands)
        for raw, (_, weight) in enumerate(hand_distribution()):
            weights[game.projection[raw]] += weight
        self.assertEqual(weights, game.weights)
        self.assertEqual(sum(weights), 7776)
        for last in ((), *((bid,) for bid in range(len(game.bids)))):
            legal = game.full.actions(tuple(game.selected[a] for a in last))
            mapped = tuple(-1 if a == -1 else game.selected[a] for a in game.actions(last))
            self.assertCountEqual(mapped, [a for a in legal if a == -1 or a in game.selected])

    def test_ordered_tickets_map_to_canonical_hand_ids(self):
        # Sweeping all offsets counts every stratum ticket exactly once.
        weights = [2, 0, 1, 5]
        draws = OrderedDraws(SimpleNamespace(weights=weights), [3, 0, 2, 1])
        totals = [0] * len(weights)
        for ticket in range(sum(weights)):
            first, second = draws(ConstantTicket(ticket))
            self.assertEqual(first, second)
            for i in first:
                totals[i] += 1
        self.assertEqual(totals, [BLOCK_SIZE*w for w in weights])

    def test_frozen_moments_match_actual_training_deltas(self):
        game = fixture('q2')
        sampler = OrderedDraws(game, hand_orders(game)['profile'])
        trainer = AxisFixtureTrainer(game, 2, 12, BLOCK_SIZE, True)
        for _ in range(4):
            trainer.step()
        initial_regret, initial_average = trainer.regret.copy(), trainer.average.copy()
        seed, blocks = 32, 9
        rng = random.Random(seed)
        regrets, averages, supports = [], [], []
        for _ in range(blocks):
            trainer.regret[:] = initial_regret
            trainer.average[:] = initial_average
            hands = sampler(rng)
            trainer.step(hands)
            regrets.append(trainer.regret - initial_regret)
            averages.append(trainer.average - initial_average)
            supports.append([len(set(row)) for row in hands])
        trainer.regret[:] = initial_regret
        actual = frozen_block_stats(trainer, sampler, seed, blocks)
        np.testing.assert_array_equal(trainer.regret, initial_regret)
        seats = np.repeat(trainer.layout.players, np.diff(trainer.layout.offsets))
        for key, data in (('regret_trace_by_seat', regrets), ('average_trace_by_seat', averages)):
            variance = np.var(data, axis=0, ddof=1)
            np.testing.assert_allclose(actual[key], [variance[seats == s].sum() for s in (0, 1)], atol=1e-14)
        np.testing.assert_allclose(actual['unique_hands_by_seat'], np.mean(supports, axis=0))
        self.assertAlmostEqual(actual['unique_pairs'], np.prod(supports, axis=1).mean())

    def test_replay_all_policies_and_frozen_holdout_diagnostic(self):
        out = BASE/'outputs'
        report = json.loads((out/'stratified-holdout.json').read_text(encoding='utf-8'))
        self.assertEqual(report['summary'], summary(report['curves'], report['diagnostics']))
        for name, expected in report['source_sha256_lf'].items():
            self.assertEqual(digest((BASE/name).read_bytes().replace(b'\r\n', b'\n')), expected)
        path = out/report['archive']
        self.assertEqual(digest(path.read_bytes()), report['archive_sha256'])
        games = {label: fixture(label) for label in FIXTURES}
        layouts = {(label, recall): FixtureLayout(game, recall)
                   for label, game in games.items() for recall in RECALLS}
        for label, game in games.items():
            self.assertEqual(report['fixtures'][label]['orders'], hand_orders(game))
            self.assertEqual(report['fixtures'][label]['weights'], game.weights)
            self.assertEqual(report['fixtures'][label]['bid_ids'], list(game.selected))
        self.assertCountEqual([(c['fixture'], c['recall'], c['seed']) for c in report['curves']],
                              [(f, r, s) for f, r in layouts for s in SEEDS])
        self.assertCountEqual([(d['fixture'], d['recall']) for d in report['diagnostics']], layouts.keys())
        names = []
        with np.load(path, allow_pickle=False) as tables:
            for curve in report['curves']:
                layout = layouts[curve['fixture'], curve['recall']]
                self.assertCountEqual(curve['methods'], METHODS)
                for rows in curve['methods'].values():
                    self.assertEqual([r['target_cpu'] for r in rows], list(CHECKPOINTS))
                    previous_blocks = 0
                    for row in rows:
                        self.assertLess(previous_blocks, row['blocks'])
                        self.assertLessEqual(row['blocks'], MAX_BLOCKS)
                        previous_blocks = row['blocks']
                        self.assertGreaterEqual(row['training_cpu'], row['target_cpu'])
                        self.assertLessEqual(row['training_wall'], MAX_TRAIN_WALL)
                        names.append(row['policy'])
                        data = tables[row['policy']]
                        self.assertEqual(digest(data.tobytes()), row['policy_sha256'])
                        scores = replay_score(layout.game, RecallPolicy(layout, data))
                        for key, value in scores.items():
                            self.assertAlmostEqual(value, row['score'][key], places=11)
            for diag in report['diagnostics']:
                names.append(diag['regret_table'])
                regret = tables[diag['regret_table']]
                self.assertEqual(digest(regret.tobytes()), diag['regret_sha256'])
                self.assertEqual(regret.size, layouts[diag['fixture'], diag['recall']].entries)
                self.assertEqual(diag['warmup_blocks'], 128)
                self.assertCountEqual(diag['methods'], METHODS)
                for rows in diag['methods'].values():
                    self.assertEqual([r['seed'] for r in rows], list(MOMENT_SEEDS))
                    self.assertTrue(all(r['blocks'] == MOMENT_BLOCKS for r in rows))
                if (diag['fixture'], diag['recall']) == ('q2-face6', None):
                    game = games[diag['fixture']]
                    trainer = AxisFixtureTrainer(game, None, 1, BLOCK_SIZE, True)
                    trainer.regret[:] = regret
                    samplers = {'iid': None, **{m: OrderedDraws(game, order)
                                                for m, order in hand_orders(game).items()}}
                    for method in METHODS:
                        row = diag['methods'][method][0]
                        replay = frozen_block_stats(trainer, samplers[method], row['seed'])
                        for key, value in replay.items():
                            np.testing.assert_allclose(value, row[key], rtol=1e-12)
            self.assertCountEqual(names, tables.files)


if __name__ == '__main__':
    unittest.main()
