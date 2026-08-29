"""Reproduce a pinned built-in baseline manifest."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .harness import BenchmarkHarness
from .manifest import BaselineManifest
from .toy import BUILTIN_SYSTEMS


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m g0rd0n.evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run a pinned built-in baseline manifest")
    run.add_argument("manifest", type=Path)
    arguments = parser.parse_args()
    manifest = BaselineManifest.from_json(arguments.manifest)
    try:
        system = BUILTIN_SYSTEMS[manifest.runner]()
    except KeyError as error:
        raise SystemExit(f"unsupported built-in runner: {manifest.runner}") from error
    result = BenchmarkHarness().run(manifest, system)
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
