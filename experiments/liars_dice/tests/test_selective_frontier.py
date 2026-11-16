import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier_cost import FactoredReply
from response_kernels import PreparedClaims, PreparedFrontier
from run_gap_response import BASE, TOL, fixtures, normalized_hash, verify
from run_selective_frontier import METHODS, compare, make_oracle, make_search
from selective_frontier import SelectiveFrontier
from one_face import evaluate


class SelectiveTests(unittest.TestCase):
    def test_zero_cap_and_failed_oracle_preserve_feasible_response(self):
        _, guide, target = next(fixtures())
        game = target.game
        claims = PreparedClaims(guide)
        exact = evaluate(game, target.policy)
        for seat in (0, 1):
            control = PreparedFrontier(game, guide, target, seat, 8, claims, reuse_reach=True)
            baseline = control.solve()
            for count, memory in ((0, 10000000), (16, 1)):
                oracle = FactoredReply(game, target, guide, seat, max_bytes=memory)
                search = SelectiveFrontier(game, guide, target, seat, 8, claims, oracle, max_queries=count)
                bound = search.solve()
                for key in ('lower', 'upper'):
                    self.assertEqual(bound[key], baseline[key])
                for h in control.decisions:
                    np.testing.assert_array_equal(control.decisions[h], search.decisions[h])
                self.assertEqual(bound['stats']['oracle_failures'], int(memory == 1))
                self.assertEqual(bound['stats']['oracle_queries'], int(memory == 1))
                verify(search, bound, target, exact)
            with self.assertRaises(ValueError):
                SelectiveFrontier(game, guide, target, seat, 8, claims, oracle, max_queries=-1)

    def test_receipt_and_fresh_selective_curves(self):
        report = json.loads((BASE/'outputs/selective-frontier.json').read_text())
        archive = json.loads((BASE/'outputs/frontier-cost.json').read_text())
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['frontier_cost_receipt_sha256_lf'], normalized_hash(BASE/'outputs/frontier-cost.json'))
        for name, digest in report['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(compare(report['cases'], report['timing']), report['admission'])
        for (_, guide, model), case, old in zip(fixtures(), report['cases'], archive['cases'], strict=True):
            self.assertEqual(model.fingerprint(), case['target_probabilities_sha256'])
            self.assertEqual(model.fingerprint(), old['target_probabilities_sha256'])
            exact = evaluate(model.game, model.policy)
            claims = PreparedClaims(guide)
            for row in case['seats']:
                seat = row['seat']
                for method in METHODS:
                    lo, hi = -1., 1.
                    for cap, point in zip(report['caps'], row['curves'][method], strict=True):
                        self.assertLessEqual(point['stats']['expanded_own_nodes'], cap)
                        self.assertGreaterEqual(point['lower'], lo-TOL)
                        self.assertLessEqual(point['upper'], hi+TOL)
                        self.assertLessEqual(point['lower'], exact[f'br{seat}']+TOL)
                        self.assertGreaterEqual(point['upper'], exact[f'br{seat}']-TOL)
                        self.assertLess(point['realization_error'], TOL)
                        lo, hi = point['lower'], point['upper']
                        if method.startswith('selective'):
                            limit = {'selective4': 4, 'selective16': 16, 'selective': 4096}[method]
                            self.assertLessEqual(point['stats']['oracle_queries'], limit)
                    self.assertAlmostEqual(lo, hi, places=10)
                    if method.startswith('selective'):
                        oracle = make_oracle(method, guide, model, seat)
                        search = make_search(method, guide, model, seat, 16, claims, oracle)
                        for cap, stored in zip(report['caps'][:-1], row['curves'][method][:-1], strict=True):
                            now = search.advance(cap)
                            for key in ('lower', 'upper'):
                                self.assertAlmostEqual(now[key], stored[key], places=11)
                        verify(search, now, model, exact)


if __name__ == '__main__':
    unittest.main()
