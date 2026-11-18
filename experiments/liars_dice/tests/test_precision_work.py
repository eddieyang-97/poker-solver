import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from one_face import evaluate
from response_kernels import PreparedClaims
from run_gap_response import BASE, TOL, fixtures, normalized_hash
from run_precision_work import METHODS, WIDTHS, new_search, summarize, trajectory


class PrecisionWorkTests(unittest.TestCase):
    def test_query_events_preserve_lower_and_global_containment(self):
        _, guide, model = next(fixtures())
        claims = PreparedClaims(guide)
        exact = evaluate(model.game, model.policy)
        for seat in (0, 1):
            record = trajectory('selective16', guide, model, seat, claims, exact)
            self.assertTrue(record['events'])
            for e in record['events']:
                self.assertGreaterEqual(e['width_reduction'], -TOL)
                self.assertLessEqual(e['lower_after'], exact[f'br{seat}']+TOL)
                self.assertGreaterEqual(e['upper_after'], exact[f'br{seat}']-TOL)
                if e['kind'] == 'query':
                    self.assertEqual(e['queries'], 1)
                    self.assertEqual(e['expansions'], 0)
                    self.assertEqual(e['lower_before'], e['lower_after'])
                else:
                    self.assertEqual(e['queries'], 0)
                    self.assertEqual(e['expansions'], 1)

    def test_precision_receipt_and_first_integer_crossings(self):
        r = json.loads((BASE/'outputs/precision-work.json').read_text())
        self.assertEqual(r['status'], 'completed')
        self.assertEqual(r['admission'], 'unchanged_no_go')
        self.assertEqual(r['selective_receipt_sha256_lf'], normalized_hash(BASE/'outputs/selective-frontier.json'))
        for name, digest in r['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual(summarize(r['cases'], r['timing']), r['summary'])
        for (_, guide, model), case in zip(fixtures(), r['cases'], strict=True):
            self.assertEqual(model.fingerprint(), case['target_probabilities_sha256'])
            for row in case['seats']:
                br = case['independent'][f'br{row["seat"]}']
                for method in METHODS:
                    record = row['methods'][method]
                    lo, hi = -1., 1.
                    for cap, point in enumerate(record['curve'], 1):
                        self.assertEqual(point['max_nodes'], cap)
                        self.assertGreaterEqual(point['lower'], lo-TOL)
                        self.assertLessEqual(point['upper'], hi+TOL)
                        self.assertLessEqual(point['lower'], br+TOL)
                        self.assertGreaterEqual(point['upper'], br-TOL)
                        lo, hi = point['lower'], point['upper']
                    self.assertAlmostEqual(lo, hi, places=10)
                    for width in WIDTHS:
                        p = record['precision'][str(width)]
                        self.assertLessEqual(p['width'], width)
                        self.assertLess(p['realization_error'], TOL)
                        if p['max_nodes'] > 1:
                            self.assertGreater(record['curve'][p['max_nodes']-2]['width'], width)
                    cap = record['precision']['0.02']['max_nodes']
                    fresh = new_search(method, guide, model, row['seat'], cap, PreparedClaims(guide))
                    bound = fresh.solve()
                    for key in ('lower', 'upper'):
                        self.assertAlmostEqual(bound[key], record['precision']['0.02'][key], places=10)
                    events = record['events']
                    if method.startswith('selective'):
                        self.assertEqual(sum(e['queries'] for e in events), record['closure']['stats']['oracle_queries'])


if __name__ == '__main__':
    unittest.main()
