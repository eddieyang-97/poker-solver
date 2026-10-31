from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beliefs import posterior
from finite_family import Family, Mixture, MixtureResponse, exact_matrix, solve_matrix
from guidance import ProbabilityGuide
from one_face import OneFace, evaluate


class FiniteFamilyTests(unittest.TestCase):
    def test_known_matrix_games_and_direct_saddle_gap(self):
        for matrix,value in (([[1,-1],[-1,1]],0),([[2,-1],[-2,1]],0),([[1,2],[0,1]],1),
                             ([[0,-1,1],[1,0,-1],[-1,1,0]],0)):
            matrix = np.array(matrix,dtype=float)
            report = solve_matrix(matrix,(1000,10000))[-1]
            self.assertLess(report['family_nashconv'],.005)
            self.assertAlmostEqual(report['value'],value,delta=.005)
            x,y = np.array(report['mixture0']),np.array(report['mixture1'])
            self.assertAlmostEqual(report['family_nashconv'],max(matrix @ y)-min(x @ matrix))

    def test_exact_chance_matrix_and_perfect_recall_mixture(self):
        game = OneFace(5)
        guide = ProbabilityGuide(game)
        family = Family(game,guide,((.3,None),(.7,.2),(.5,.95)))
        numerators,total = exact_matrix(family)
        matrix = numerators/total
        for i in range(3):
            for j in range(3):
                first,second = family.pure_policy(i),family.pure_policy(j)
                policy = lambda p,t,h:first(p,t,h) if p == 0 else second(p,t,h)
                self.assertAlmostEqual(matrix[i,j],evaluate(game,policy)['ev_p0'])
        x,y = np.array([.2,.3,.5]),np.array([.4,.1,.5])
        mixture = Mixture(family,x,y)
        # Naively mixing anew at each turn generally fails this realization identity.
        self.assertAlmostEqual(evaluate(game,mixture.policy)['ev_p0'],x @ matrix @ y)
        response = MixtureResponse(game,mixture,guide)
        for history in ((3,),(4,),(3,4),(3,4,5)):
            seat = len(history)%2
            expected = posterior(game,seat,history,mixture.policy)
            np.testing.assert_allclose(response._belief(seat,history),expected,rtol=0,atol=1e-14)


if __name__ == '__main__':
    unittest.main()
