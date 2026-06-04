#!/usr/bin/env python3
"""Run the Jarvis localhost dashboard."""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.server import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Jarvis localhost dashboard.")
    parser.add_argument("--host", default=None, help="Host to bind. Defaults to JARVIS_HOST or 127.0.0.1.")
    parser.add_argument("--port", type=int, default=None, help="Port to bind. Defaults to JARVIS_PORT or 8765.")
    parser.add_argument("--paused", action="store_true", help="Start with /api/command paused until resumed.")
    args = parser.parse_args()
    try:
        options = {key: value for key, value in {"host": args.host, "port": args.port}.items() if value is not None}
        if args.paused:
            options["start_paused"] = True
        run(**options)
    except (OSError, ValueError) as error:
        print(f"Jarvis dashboard failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nJarvis dashboard stopped.")


if __name__ == "__main__":
    main()
