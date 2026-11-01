"""Perfect-recall action restriction, evaluated back in the larger assumed game.

Keep the smallest legal quantity for EACH face/mode. No private-hand abstraction
or history merging. Omits jump bids; convergence here would not certify full GTO.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import tracemalloc

from game import Game
from mccfr import Solver
from run_research import bot_policy, matches, probability_table
from summarize import lower_bound


class Adjacent(Game):
    def _legal(self, last):
        full = super()._legal(last)
        best = {}
        for a in full:
            if a == -1:
                continue
            bid = self.bids[a]
            key = bid.face, bid.mode
            if key not in best or bid.quantity < self.bids[best[key]].quantity:
                best[key] = a
        return tuple(([-1] if last else []) + sorted(best.values()))


def expand_policy(solver, full):
    def policy(player, hand, history):
        restricted = dict(zip(solver.game.actions(history), solver.policy(player,hand,history)))
        return [restricted.get(a, 0.0) for a in full.actions(history)]
    return policy


def run(iterations, games, seed, max_infos):
    start = time.perf_counter()
    full, abstract = Game(), Adjacent()
    solver = Solver(abstract,seed=seed,max_infos=max_infos)
    status = "completed_budget"
    tracemalloc.start()
    try:
        solver.train(iterations)
    except MemoryError as exc:
        status = str(exc)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    training_seconds = time.perf_counter()-start
    policy = expand_policy(solver,full)
    table = probability_table(full)
    bots = {"uniform": lambda p,t,h:[1/len(full.actions(h))]*len(full.actions(h)),
            **{f"probability_{int(threshold*100)}": bot_policy(full,table,threshold)
               for threshold in (.3,.5,.7)}}
    results = {}
    for name, bot in bots.items():
        for seat in (0,1):
            policies = (policy,bot) if seat == 0 else (bot,policy)
            results[f"{name}_solver_seat{seat}"] = matches(full,policies,seed+100000+seat,games)
    results["selfplay"] = matches(full,(policy,policy),seed+200000,games)
    return {"seed": seed, "rules": asdict(full.rules), "requested_iterations": iterations,
            "completed_iterations": solver.iterations, "status": status,
            "training_seconds": training_seconds, "python_traced_peak_bytes": peak,
            "infos": len(solver.infos), "max_importance": solver.max_importance,
            "opening_actions": len(abstract.actions(())), "matches_in_full_game": results,
            "full_game_lower_bound": lower_bound(results),
            "certified_equilibrium": False, "exploitability_upper_bound": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations",type=int,default=50000)
    parser.add_argument("--games",type=int,default=2000)
    parser.add_argument("--max-infos",type=int,default=100000)
    parser.add_argument("--seeds",type=int,nargs="+",default=[761245,42])
    parser.add_argument("--output",type=Path,default=Path(__file__).parent/"outputs/abstraction.json")
    args = parser.parse_args()
    if min(args.iterations,args.games,args.max_infos) <= 0:
        parser.error("positive budgets required")
    here = Path(__file__).parent
    receipt = {"source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in here.glob("*.py")},
               "action_restriction": "smallest legal quantity for every face/mode",
               "runs": []}
    for seed in args.seeds:
        print(f"adjacent seed={seed}",flush=True)
        receipt["runs"].append(run(args.iterations,args.games,seed,args.max_infos))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
