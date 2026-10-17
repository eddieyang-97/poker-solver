"""Local experimental two-street solver; no hosted MCP registration."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poker_spot.turn import TurnSolver, evaluate_turn_all_in_call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--all-in-call', action='store_true', help='Terminal effective all-in only; no future betting')
    args = parser.parse_args()
    try:
        config = json.loads(args.scenario.read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            raise ValueError('Scenario must be a JSON object')
        if args.all_in_call:
            result = evaluate_turn_all_in_call(**config)
        else:
            solve_args = {key: config.pop(key) for key in ('iterations', 'oop_hand', 'ip_hand', 'river_card') if key in config}
            result = TurnSolver(**config).solve(**solve_args)
    except (ValueError, TypeError) as error:
        print(json.dumps({'error': {'code': 'INVALID_INPUT', 'message': str(error)}}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
