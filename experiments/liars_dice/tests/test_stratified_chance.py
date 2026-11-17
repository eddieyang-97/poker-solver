import itertools
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from one_face import evaluate
from recall_ablation import FixtureLayout, HouseFixture
from recall_training import RecallPolicy
from run_stratified_chance import BASE, BUDGETS, SEEDS, digest, summarize
from stratified_chance import StratifiedHands


class TicketStream:
    def __init__(self, tickets):
        self.tickets = iter(tickets)

    def randrange(self, limit):
        v = next(self.tickets)
        assert 0 <= v < limit
        return v


class StratifiedTests(unittest.TestCase):
    def test_exhaustive_crossed_pair_law_with_duplicates_and_zero_mass(self):
        weights = [2, 0, 1]
        k = 2
        sampler = StratifiedHands(weights, k)
        observed = np.zeros((3, 3), dtype=int)
        for draws in itertools.product(range(sum(weights)), repeat=2*k):
            first, second = sampler.deal(TicketStream(draws))
            for a, b in itertools.product(first, second):
                observed[a, b] += 1
        np.testing.assert_array_equal(observed * sum(weights)**2, observed.sum()*np.outer(weights, weights))

    def test_replay_all_models_against_full_history_response(self):
        out = BASE/'outputs'
        report = json.loads((out/'stratified-chance.json').read_text())
        self.assertEqual(report['summary'], summarize(report['pairs']))
        for n, h in report['source_sha256_lf'].items():
            self.assertEqual(digest((BASE/n).read_bytes().replace(b'\r\n', b'\n')), h)
        path = out/report['archive']
        self.assertEqual(digest(path.read_bytes()), report['archive_sha256'])
        layouts = {(q, r): FixtureLayout(HouseFixture(q), r) for q in (2, 3) for r in (1, 2, None)}
        self.assertCountEqual([(p['quantity'], p['recall'], p['seed']) for p in report['pairs']],
                              [(q, r, s) for q, r in layouts for s in SEEDS])
        names = []
        with np.load(path, allow_pickle=False) as tables:
            for pair in report['pairs']:
                layout = layouts[pair['quantity'], pair['recall']]
                for method in ('iid', 'stratified'):
                    rows = pair['methods'][method]
                    self.assertEqual([r['blocks'] for r in rows], list(BUDGETS))
                    for row in rows:
                        names.append(row['policy'])
                        data = tables[row['policy']]
                        self.assertEqual(digest(data.tobytes()), row['policy_sha256'])
                        score = evaluate(layout.game, RecallPolicy(layout, data).policy)
                        for key, value in score.items():
                            self.assertAlmostEqual(value, row['score'][key], places=11)
            self.assertCountEqual(names, tables.files)


if __name__ == '__main__':
    unittest.main()
