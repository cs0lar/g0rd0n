"""Independent proof verification command."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import ProofBundle, builtin_verifier_registry


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m g0rd0n.proofs")
    parser.add_argument("command", choices=("verify",))
    parser.add_argument("artifact", type=Path)
    arguments = parser.parse_args()
    bundle = ProofBundle.from_json(arguments.artifact)
    result = builtin_verifier_registry().verify(bundle)
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
