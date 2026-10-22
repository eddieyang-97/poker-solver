"""Reconstruct a post-session hand; optionally execute existing bounded river calculations."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poker_spot.history import HistoryError, parse_history, reconstruct, revise_hand
from poker_spot.review import prepare_review, render_markdown, run_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hand', type=Path)
    parser.add_argument('--scenarios', type=Path)
    parser.add_argument('--run', action='store_true', help='Run actual local disposable river workers; otherwise retain not_run requests')
    parser.add_argument('--iterations', type=int, default=700)
    parser.add_argument('--markdown', action='store_true', help='Render computed evidence and explicit not-run states as readable study notes')
    parser.add_argument('--output', type=Path, help='Write complete JSON and readable Markdown evidence to this prefix')
    parser.add_argument('--set', action='append', default=[], metavar='POINTER=JSON', help='Correct an existing field without rewriting the hand')
    args = parser.parse_args()
    try:
        text = args.hand.read_text(encoding='utf-8-sig')
        if len(text) > 65536:
            raise HistoryError('Hand input exceeds 65,536 characters')
        if text.lstrip().startswith('{'):
            hand = json.loads(text)
        else:
            parsed = parse_history(text)
            if parsed['status'] != 'parsed':
                print(json.dumps(dict(parsed, execution='not_run'), indent=2))
                return 2
            hand = parsed['hand']
        for change in args.set:
            pointer, separator, value = change.partition('=')
            if not separator:
                raise HistoryError('Correction requires POINTER=JSON')
            hand = revise_hand(hand, pointer, json.loads(value))
        if args.scenarios:
            scenarios = json.loads(args.scenarios.read_text(encoding='utf-8-sig'))
            result = asyncio.run(run_review(hand, scenarios, args.iterations)) if args.run else prepare_review(hand, scenarios, args.iterations)
        elif args.run:
            raise HistoryError('Explicit scenarios are required; no automatic range inference')
        else:
            result = {'status': 'not_run', 'reconstruction': reconstruct(hand), 'queries': [],
                      'reason': 'Supply explicit scenarios before preparing or running river tools'}
    except (HistoryError, ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({'status': 'not_run', 'error': {'code': getattr(error, 'code', 'INVALID_INPUT'), 'message': str(error)}}), file=sys.stderr)
        return 2
    encoded = json.dumps(result, indent=2, allow_nan=False)+'\n'
    notes = render_markdown(result) if 'scenarios' in result else None
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.json').write_text(encoded, encoding='utf-8')
        if notes is not None:
            args.output.with_suffix('.md').write_text(notes, encoding='utf-8')
    else:
        print(notes if args.markdown and notes is not None else encoded, end='')
    return 1 if result['status'] in ('partial', 'failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
