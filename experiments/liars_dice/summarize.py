"""Summarize measured runs and exact priors; never infer full-game NashConv."""
import argparse
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from game import Game, contribution, hand_distribution


def complexity(game):
    paths, depths = {}, {}
    openings = game.actions(())
    for a in sorted(range(len(game.bids)), key=lambda i: game.bids[i].rank):
        paths[a] = paths.get(a, 0) + int(a in openings)
        depths[a] = max(depths.get(a, 0), int(a in openings))
        for b in game.actions((a,)):
            if b != -1:
                paths[b] = paths.get(b, 0) + paths[a]
                if depths[a]:
                    depths[b] = max(depths.get(b, 0), depths[a]+1)
    return {"private_hands_per_player": 252, "private_deals": 252**2,
            "opening_actions": len(openings), "public_decision_histories": str(1+sum(paths.values())),
            "maximum_bids_before_challenge": max(depths.values()),
            "perfect_recall_infosets": str(252*(1+sum(paths.values())))}


def lower_bound(matches):
    # Eight predeclared bot/seat tests, simultaneously valid with union bound.
    rows = [(key,value) for key,value in matches.items() if key != "selfplay"]
    m = len(rows)
    p0, p1, lo0, lo1 = [], [], [], []
    for key, value in rows:
        radius = math.sqrt(2*math.log(2*m/.05)/value["games"])
        if key.endswith("seat1"):
            # Bot player0 against frozen solver player1.
            p0.append(value["ev_p0"])
            lo0.append(value["ev_p0"]-radius)
        else:
            p1.append(-value["ev_p0"])
            lo1.append(-value["ev_p0"]-radius)
    return {"empirical_candidate_br_sum": max(p0)+max(p1),
            "nashconv_lower_bound_95_familywise": max(0, max(lo0)+max(lo1)),
            "exploitability_lower_bound_95_familywise": max(0, max(lo0)+max(lo1))/2,
            "exploitability_upper_bound": None,
            "note": "Candidate responses give only a lower bound; no best-response training or equilibrium certificate."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(__file__).parent/"outputs/research.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent/"outputs/summary.json")
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    examples = []
    for hand in ((4,4,4,2,3), (4,4,4,1,1), (1,1,2,3,5)):
        for mode in ("fly","zhai"):
            own = contribution(hand,4,mode)
            rows = []
            for quantity in range(3,11):
                numerator = sum(weight for other,weight in hand_distribution()
                                if own+contribution(other,4,mode) >= quantity)
                p = Fraction(numerator,7776)
                rows.append({"quantity": quantity, "truth_numerator_of_7776": numerator,
                             "truth_probability": float(p), "prior_challenge_ev": float(1-2*p)})
            examples.append({"hand": hand, "mode": mode, "own_count": own, "rows": rows})
    result = {"raw_results_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "assumed_rules": asdict(Game().rules), "complexity": complexity(Game()),
              "exact_pre_action_probabilities": examples,
              "full_game_response_lower_bounds": [{"profile": run["profile"], "seed": run["seed"],
                  **lower_bound(run["matches"])} for run in raw["full_game_experiments"]]}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result["complexity"],indent=2))
    for run in result["full_game_response_lower_bounds"]:
        print(run)


if __name__ == "__main__":
    main()
