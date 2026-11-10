import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier_cost import FactoredReply
from game import Game
from recall_training import Layout
from run_full_frontier_feasibility import (ARCHIVE, BLOCKS, CHECK_HANDS, MATRIX_CAP, METHODS, PAIR_EDGE_CAP,
                                           TOL, full_paths, inventory_workload, loaded_targets)
from run_gap_response import BASE, normalized_hash, sha


class FullFrontierFeasibilityTests(unittest.TestCase):
    def test_stress_paths_are_legal_and_match_each_graph_key(self):
        game = Game()
        graph = Layout(game).graph
        short, long = full_paths(graph)
        self.assertEqual(set(short), set(range(len(graph.keys))))
        self.assertEqual(set(long), set(short))
        for i, key in enumerate(graph.keys):
            for h in (short[i], long[i]):
                self.assertEqual(graph.key(len(h) % 2, h), key)
                for j, action in enumerate(h):
                    self.assertIn(action, game.actions(h[:j]))
            self.assertLessEqual(len(short[i]), len(long[i]))
        self.assertGreater(max(map(len, long.values())), 50)

    def test_real_matrix_cap_includes_retained_arrays_after_failure(self):
        _, _, game, guide, model = next(loaded_targets())
        limit = 1024**2
        oracle = FactoredReply(game, model, guide, 0, max_bytes=limit)
        queries, _ = inventory_workload(game, model, 0, np.asarray(game.prior))
        completed = 0
        with self.assertRaisesRegex(MemoryError, 'pair-memory cap'):
            for q in sorted(queries, key=lambda q: len(game.actions(q.history))):
                if not q.forced:
                    oracle.upper(q.history, q.mass)
                    completed += 1
        self.assertGreater(completed, 0)
        retained = sum(a.nbytes for cache in (oracle.truth, oracle.bad, oracle.risk)
                       for a in cache.values() if a is not None)
        estimate = oracle.resources()['estimated_matrix_bytes']
        self.assertLessEqual(retained, estimate)
        self.assertLessEqual(estimate, limit)

    def test_fixed_work_receipt_preserves_scope_and_resource_caps(self):
        report = json.loads((BASE/'outputs/full-frontier-feasibility.json').read_text())
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['full_game_admission'], 'unchanged_no_go')
        self.assertEqual(normalized_hash(ARCHIVE), report['target_receipt_sha256_lf'])
        for name, digest in report['source_sha256_lf'].items():
            self.assertEqual(normalized_hash(BASE/name), digest)
        self.assertEqual({t['method'] for t in report['targets']}, {'axis', 'reference'})
        self.assertEqual(len(report['targets']), 2)
        game = Game()
        fanout = sum(len(game.actions((bid,)))-1 for bid in game.actions(()))
        openings = len(game.actions(()))
        queries = 0
        for target in report['targets']:
            artifact = target['target']
            self.assertEqual(sha((BASE/'outputs'/artifact['file']).read_bytes()), artifact['sha256'])
            self.assertEqual([row['seat'] for row in target['seats']], [0, 1])
            for row in target['seats']:
                opening = row['workloads']['opening']
                self.assertEqual(opening['queries']+opening['zero_reach_omitted'], fanout if row['seat'] == 0 else openings)
                self.assertEqual(opening['prior_stress_queries'], 0)
                self.assertGreater(row['workloads']['inventory']['maximum_bids'], 50)
                for part in row['workloads'].values():
                    queries += part['queries']
                    self.assertEqual(part['independent_value_count'], part['queries']*len(CHECK_HANDS))
                    self.assertLess(part['max_abs_error'], TOL)
                    self.assertLessEqual(part['factored_resources']['estimated_matrix_bytes'], MATRIX_CAP)
                    self.assertLessEqual(part['factored_resources']['pair_edges'], PAIR_EDGE_CAP)
                    self.assertLessEqual(part['checksum']['factored'], part['checksum']['prepared']+TOL)
                    self.assertEqual(set(part['repeats_per_block']), set(METHODS))
                    self.assertGreater(part['repeats_per_block']['prepared'], part['repeats_per_block']['factored'])
                    self.assertEqual(len(part['timing_blocks']), BLOCKS)
                    for block in part['timing_blocks']:
                        self.assertEqual(set(block), set(METHODS))
                        self.assertTrue(all(t['wall_ns'] > 0 and t['cpu_ns'] >= 0 for t in block.values()))
                matrix, work = (row['cap_probes'][m] for m in ('matrix', 'work'))
                self.assertEqual(matrix['status'], 'blocked')
                self.assertEqual(work['status'], 'blocked')
                self.assertGreater(matrix['completed_queries'], 0)
                self.assertGreater(work['completed_queries'], 0)
                self.assertLessEqual(matrix['resources']['estimated_matrix_bytes'], 1024**2)
                self.assertLessEqual(work['resources']['pair_edges'], 4_000_000)
        for m in METHODS:
            self.assertEqual(report['isolated_memory'][m]['queries'], queries)
            self.assertGreater(report['isolated_memory'][m]['process_peak']['bytes'], 0)


if __name__ == '__main__':
    unittest.main()
