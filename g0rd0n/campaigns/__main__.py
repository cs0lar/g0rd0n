from __future__ import annotations

import argparse
import json
from pathlib import Path

from .first import run_campaign


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m g0rd0n.campaigns")
    parser.add_argument("command", choices=("run",))
    parser.add_argument("spec", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run_campaign(arguments.spec).to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
