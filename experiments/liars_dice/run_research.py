"""Reproducible research driver; run from any directory. Outputs are not GTO claims."""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import time
import tracemalloc

from game import Game, Rules, contribution, hand_distribution
from mccfr import Solver
from one_face import ExactCFR, OneFace, evaluate, exported_policy


def probability_table(game):
    table = []
    for row in game.counts:
        table.append([sum(p for other, p in zip(game.counts, game.prior)
                          if own + other[b] >= game.bids[b].quantity)
                      for b, own in enumerate(row)])
    return table


def bot_policy(game, table, threshold):
    def policy(player, hand, history):
        actions = game.actions(history)
        if history and table[hand][history[-1]] < threshold:
            return [1.0] + [0.0] * (len(actions) - 1)
        bids = [a for a in actions if a != -1]
        if not bids:
            return [1.0]
        # Probability-only, ignores signalling. Prefer highest truth probability,
        # then lower quantity, higher face, fly. Deliberately transparent baseline.
        best = max(bids, key=lambda a: (table[hand][a], -game.bids[a].quantity,
                                       game.bids[a].face, game.bids[a].mode == "fly"))
        return [float(a == best) for a in actions]
    return policy


def matches(game, policies, seed, games, solver=None):
    """Fixed policies; independent fresh-roll evaluation, no training/adaptation."""
    rng = random.Random(seed)
    values, missing, decisions, lengths = [], 0, 0, []
    for _ in range(games):
        hands, history = game.sample(rng), ()
        while True:
            player = len(history) % 2
            if solver is not None and policies[player] == solver.policy:
                decisions += 1
                missing += game.key(player, hands[player], history) not in solver.infos
            strategy = policies[player](player, hands[player], history)
            action = rng.choices(game.actions(history), weights=strategy)[0]
            if action == -1:
                values.append(game.payoff(history, hands, player))
                lengths.append(len(history))
                break
            history += (action,)
    mean = sum(values) / games
    # Hoeffding two-sided 95% interval for outcomes bounded in [-1,+1].
    half = math.sqrt(2 * math.log(40) / games)
    return {"games": games, "seed": seed, "ev_p0": mean,
            "hoeffding95": [max(-1, mean-half), min(1, mean+half)],
            "unseen_solver_fraction": missing / decisions if decisions else None,
            "mean_bids": sum(lengths) / games}


def run_full(iterations, games, seed, rules, max_infos):
    started = time.perf_counter()
    game = Game(rules)
    table = probability_table(game)
    solver = Solver(game, seed=seed, max_infos=max_infos)
    checkpoints = []
    status = "completed_budget"
    tracemalloc.start()
    try:
        for target in sorted(set((max(1, iterations//10), iterations))):
            solver.train(target - solver.iterations)
            checkpoints.append({"iterations": solver.iterations, "infos": len(solver.infos),
                                "seconds": time.perf_counter()-started})
    except MemoryError as exc:
        status = str(exc)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    training_seconds = time.perf_counter()-started
    result = {"rules": asdict(rules), "seed": seed, "requested_iterations": iterations,
              "completed_iterations": solver.iterations, "status": status,
              "information_sets": len(solver.infos), "array_bytes": sum(
                  8 * (len(n.regret)+len(n.average)) for n in solver.infos.values()),
              "python_traced_peak_bytes": peak, "training_seconds": training_seconds,
              "max_importance": solver.max_importance, "checkpoints": checkpoints,
              "exploitability": None, "certified_equilibrium": False}
    uniform = lambda p, t, h: [1 / len(game.actions(h))] * len(game.actions(h))
    result["matches"] = {}
    bots = {"uniform": uniform, "probability_30": bot_policy(game, table, .3),
            "probability_50": bot_policy(game, table, .5),
            "probability_70": bot_policy(game, table, .7)}
    for name, bot in bots.items():
        for seat in (0, 1):
            policies = (solver.policy, bot) if seat == 0 else (bot, solver.policy)
            result["matches"][f"{name}_solver_seat{seat}"] = matches(
                game, policies, seed + 100000 + seat, games, solver)
    result["matches"]["selfplay"] = matches(game, (solver.policy, solver.policy), seed+200000, games, solver)
    result["examples"] = []
    for hand in ((1,1,4,4,4), (2,3,4,4,4), (2,3,4,5,6), (1,1,1,1,1)):
        index = game.hands.index(tuple(sorted(hand)))
        s = solver.policy(0, index, ())
        ranked = sorted(zip(game.actions(()), s), key=lambda x: -x[1])[:5]
        node = solver.infos.get(game.key(0, index, ()))
        result["examples"].append({"hand": hand, "root_updates": node.visits if node else 0,
                                   "top_openings": [{"bid": asdict(game.bids[a]), "p": p}
                                                    for a, p in ranked]})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--games", type=int, default=2000)
    parser.add_argument("--max-infos", type=int, default=100000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[761245, 42])
    parser.add_argument("--policy-bin", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "outputs/research.json")
    args = parser.parse_args()
    if args.iterations < 1 or args.games < 1:
        parser.error("positive iterations/games required")
    start = time.perf_counter()
    here = Path(__file__).parent
    result = {"source_base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(here.glob("*.py")) + sorted(here.glob("*.cpp"))},
              "python": platform.python_version(), "platform": platform.platform(),
              "processor": platform.processor(), "argv": vars(args) | {"output": str(args.output),
              "policy_bin": str(args.policy_bin) if args.policy_bin else None}}
    result["distributions"] = {m: dict(sorted(Counter({v: sum(w for h, w in hand_distribution()
                                          if contribution(h, 4, m) == v)
                                          for v in range(8)}).items())) for m in ("fly", "zhai")}
    if args.policy_bin:
        result["archived_independent_evaluation"] = evaluate(OneFace(), exported_policy(args.policy_bin))
    small = OneFace(5)
    exact = ExactCFR(small)
    result["small_game"] = {"maximum_bid": 5, "exact_cfr": [], "outcome_sampling": []}
    for target in (10, 100, 1000):
        exact.train(target-exact.iterations)
        result["small_game"]["exact_cfr"].append({"iterations": target, **evaluate(small, exact.policy)})
    for seed in args.seeds:
        sampled = Solver(small, seed=seed)
        for target in (1000, 10000, 100000):
            sampled.train(target-sampled.iterations)
            result["small_game"]["outcome_sampling"].append(
                {"seed": seed, "iterations": target, **evaluate(small, sampled.policy)})
    profiles = [("baseline_assumptions", Rules()),
                ("no_face_one", replace(Rules(), face_one=False)),
                ("zhai_mixed_bonus", replace(Rules(), zhai_mixed_bonus=True)),
                ("all_ones_six", replace(Rules(), all_ones_wild_seven=False)),
                ("fly_open_floor_three", replace(Rules(), opening_zhai=False, quantity_floor=3))]
    result["full_game_experiments"] = []
    for name, rules in profiles:
        for seed in args.seeds if name == "baseline_assumptions" else args.seeds[:1]:
            print(f"training {name} seed={seed}", flush=True)
            result["full_game_experiments"].append({"profile": name, **run_full(
                args.iterations, args.games, seed, rules, args.max_infos)})
    result["total_seconds"] = time.perf_counter()-start
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"wrote {args.output}: {result['total_seconds']:.2f}s")


if __name__ == "__main__":
    main()
