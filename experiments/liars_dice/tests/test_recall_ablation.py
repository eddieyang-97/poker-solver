from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fixed_strategy import tree_increments
from one_face import evaluate
from recall_ablation import HouseFixture, ExactFixtureCFR, SampledFixtureCFR


def raw_count(dice, face, mode):
    if all(d == face for d in dice): return 7
    if face == 1: return dice.count(1)
    if mode == 'zhai': return dice.count(face)
    if all(d == 1 for d in dice): return 7
    if all(d in (1,face) for d in dice): return 6
    return sum(d in (1,face) for d in dice)


class RecallAblationTests(unittest.TestCase):
    def test_raw_chance_profiles_and_action_subset(self):
        with self.assertRaises(ValueError): HouseFixture(4)
        with self.assertRaises(ValueError): ExactFixtureCFR(HouseFixture(2,compress=False),1)
        for q in (2,3):
            game = HouseFixture(q)
            counts = Counter(tuple(raw_count(dice,b.face,b.mode) for b in game.bids)
                             for dice in product(range(1,7),repeat=5))
            self.assertEqual(counts,dict(zip(game.hands,game.weights)))
            self.assertEqual(sum(game.weights),7776)
            self.assertEqual(len(game.hands),56)
            for last in (None,*range(6)):
                expected = [] if last is None else [-1]
                for a,b in enumerate(game.bids):
                    if last is None: legal = b.quantity >= 3
                    else:
                        old = game.bids[last]
                        legal = ((b.quantity,b.face) > (old.quantity,old.face) if b.mode == old.mode else
                                 b.quantity >= old.quantity+(-1 if old.mode == 'fly' else 2))
                    if legal: expected.append(a)
                self.assertEqual(game.actions(() if last is None else (last,)),tuple(expected))

    def test_compression_preserves_full_private_type_evaluation(self):
        small,full = HouseFixture(2),HouseFixture(2,compress=False)
        trained = ExactFixtureCFR(small,1)
        for _ in range(10): trained.step()
        score = evaluate(small,trained.policy)
        projected = lambda p,t,h:trained.policy(p,small.projection[t],h)
        large = evaluate(full,projected)
        for key in score: self.assertAlmostEqual(score[key],large[key],places=11)

    def test_recall_adapters_match_scalar_and_sample_expectation(self):
        game = HouseFixture(2)
        # Conditional three-profile chance fixture keeps the scalar oracle tiny.
        game.hands = game.hands[:3]; game.counts = game.counts[:3]
        game.prior = (.6,.3,.1)
        for recall in (1,2,None):
            exact,sampled = ExactFixtureCFR(game,recall),SampledFixtureCFR(game,recall,490031)
            rng = np.random.default_rng(490031)
            for i,r in enumerate(exact.regrets):
                r[:] = rng.normal(size=r.shape)
                for t in range(3): sampled.layout.row(sampled.regret,i,t)[:] = r[t]
            strategies = exact.current()
            graph = exact.increments(strategies)
            scalar = tree_increments(game,exact.graph,strategies)
            for aa,bb in zip(graph[:2],scalar[:2]):
                for a,b in zip(aa,bb): np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)
            delta = [np.zeros_like(r) for r in exact.regrets]
            average = [np.zeros_like(r) for r in exact.regrets]
            for a in range(3):
                for b in range(3):
                    dr,da,_,_ = sampled.increments((a,b))
                    for i,p in enumerate(sampled.layout.players):
                        delta[i][(a,b)[p]] += game.prior[a]*game.prior[b]*dr[i]
                        average[i][(a,b)[p]] += game.prior[a]*game.prior[b]*da[i]
            for aa,bb in ((graph[0],delta),(graph[1],average)):
                for a,b in zip(aa,bb): np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)

    def test_recorded_full_history_policy_replay(self):
        base = Path(__file__).resolve().parents[1]
        receipt = json.loads((base/'outputs/recall-ablation.json').read_text())
        self.assertEqual(receipt['status'],'completed')
        self.assertEqual([f['zhai_quantity'] for f in receipt['fixtures']],[2,3])
        for name,h in receipt['source_sha256_lf'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),h)
        for fixture in receipt['fixtures']:
            self.assertEqual(len(fixture['runs']),12)
            self.assertEqual({(r['recall'],r['seed']) for r in fixture['runs']},
                             {(m,s) for m in (1,2,None) for s in (None,490021,490022,490023)})
            game = HouseFixture(fixture['zhai_quantity'])
            for run in fixture['runs']:
                self.assertEqual([r['iterations'] for r in run['checkpoints']],[1000,5000,20000])
                record = run['checkpoints'][-1]
                path = base/'outputs'/record['policy']['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['policy']['sha256'])
                table = json.loads(path.read_text())
                def policy(p,t,h): return table[','.join(map(str,h))][t]
                score = evaluate(game,policy)
                for k in score: self.assertAlmostEqual(score[k],record['full_history_evaluation'][k],places=11)


if __name__ == '__main__': unittest.main()
