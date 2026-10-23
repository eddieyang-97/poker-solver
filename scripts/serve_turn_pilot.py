"""Explicit LOCAL Stage A entry point; never use as the Render start command."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from poker_spot.auth import Settings
from poker_spot.http_server import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose an unprivileged local port')
    settings = Settings.from_env()
    if not settings.configured:
        parser.error('Configure local development authentication or an isolated OAuth resource first; no unauthenticated mode')
    app = create_app(settings, turn_pilot=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
