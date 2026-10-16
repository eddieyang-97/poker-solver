import argparse
import json
from pathlib import Path
from .core import RiverSolver


def main():
    ap=argparse.ArgumentParser(description='Solve a restricted heads-up river decision spot. Study use only.')
    ap.add_argument('scenario',help='Path to a scenario JSON file')
    ap.add_argument('--iterations',type=int,help='CFR+ iterations, default from JSON (500)')
    args=ap.parse_args()
    config=json.loads(Path(args.scenario).read_text())
    it=args.iterations or config.pop('iterations',500)
    oop_hand=config.pop('oop_hand',None); ip_hand=config.pop('ip_hand',None)
    solver=RiverSolver(**config)
    print(json.dumps(solver.solve(it,oop_hand,ip_hand),indent=2))

if __name__=='__main__':main()
