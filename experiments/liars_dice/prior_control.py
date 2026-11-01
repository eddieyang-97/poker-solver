"""Exact full chance enumeration of the untrained deterministic probability guide."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time

from game import Game
from guidance import ProbabilityGuide


def exact_prior_value(game, guide):
    weights = [round(p*7776) for p in game.prior]
    if sum(weights) != 7776:
        raise ValueError("Expected five-dice distribution")
    choices = {None: guide._choices(None)}
    wins, lengths, openings = Counter(), Counter(), Counter()
    minimum, maximum = 151, 0
    for h0,w0 in enumerate(weights):
        openings[int(choices[None][h0])] += w0
        for h1,w1 in enumerate(weights):
            hands, history = (h0,h1), ()
            for _ in range(151):
                player = len(history)%2
                last = history[-1] if history else None
                if last not in choices:
                    choices[last] = guide._choices(last)
                action = int(choices[last][hands[player]])
                if action not in game.actions(history):
                    raise AssertionError("Prior guide produced an illegal bid")
                if action == -1:
                    utility = int(game.payoff(history,hands,player))
                    wins[utility] += w0*w1
                    lengths[len(history)] += w0*w1
                    minimum,maximum = min(minimum,len(history)),max(maximum,len(history))
                    break
                history += (action,)
            else:
                raise AssertionError("Deterministic guide failed to terminate")
    total = 7776**2
    if sum(wins.values()) != total:
        raise AssertionError("Incomplete chance enumeration")
    ev = Fraction(wins[1]-wins[-1],total)
    return {'private_deals':len(weights)**2,'ordered_chance_outcomes':total,
            'p0_win_weight':wins[1],'p0_loss_weight':wins[-1],
            'ev_p0_fraction':str(ev),'ev_p0':float(ev),
            'p0_drinks_probability':float(Fraction(wins[-1],total)),
            'mean_bids':float(Fraction(sum(n*w for n,w in lengths.items()),total)),
            'minimum_bids':minimum,'maximum_bids':maximum,
            'opening_weights_out_of_7776':dict(sorted(openings.items())),
            'certified_equilibrium':False,'exploitability_upper_bound':None}


def main():
    start = time.perf_counter()
    game = Game()
    guide = ProbabilityGuide(game)
    root = Path(__file__).parent
    result = {'source_hash_format':'sha256-lf-normalized',
              'source_sha256':{name:hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                               for name in ('game.py','guidance.py','one_face.py','prior_control.py')},
              'policy':'untrained probability guide, threshold 0.5',
              **exact_prior_value(game,guide),'wall_seconds':time.perf_counter()-start}
    path = root/'outputs/prior-control.json'
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
