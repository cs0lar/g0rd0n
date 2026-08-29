"""Small command-line boundary for validating scientific contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core.mission import MissionSpec


def main() -> int:
    parser = argparse.ArgumentParser(prog="g0rd0n")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a MissionSpec JSON file")
    validate.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command == "validate":
        spec = MissionSpec.from_json(args.path)
        print(f"valid MissionSpec: {spec.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
