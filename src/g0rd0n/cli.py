"""The command line: the only place that reads a config file and the only place that exits.

Phase 0 deliberately offers three commands and no more. `version` says what is installed,
`config` says what was loaded, `doctor` says what is missing. None of them spends anything,
because nothing can be spent until the Ledger exists.

Deletion criterion: this module holds the wager that a human can find out what g0rd0n is
about to do before it does it. Delete it and `doctor_reports_missing_kernel_and_vault_
without_crashing` loses its verdict, and the first symptom of a misconfigured kernel becomes
a half-finished run rather than a refusal to start.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from g0rd0n import __version__
from g0rd0n.config import Config, ConfigError, load

DEFAULT_CONFIG = Path("config/g0rd0n.toml")

#: The whole CLI surface, as data. Phase 0's review question is "does the repo do nothing
#: yet, loudly and correctly?", and this table is where that is answered. Adding a command
#: is a deliberate act with a test to update, not a drive-by.
COMMANDS: dict[str, str] = {
    "version": "print the version and exit",
    "doctor": "check that the kernel, the vault, and the config are where they claim to be",
    "config": "print the resolved configuration",
}


class Check(NamedTuple):
    """One thing g0rd0n needs, and whether it is there."""

    name: str
    ok: bool
    detail: str


def doctor(config: Config) -> list[Check]:
    """Report on everything g0rd0n depends on and does not itself create.

    Pure: it inspects, and never creates a directory or starts a subprocess. A missing
    kernel or vault is a finding, not an exception — the point of the command is to be
    runnable on a machine where nothing is set up yet.
    """
    return [
        _directory("kernel storage", config.kernel_storage_root),
        _executable("knk mcp_server", config.kernel_mcp_server),
        _directory("vault", config.vault_root),
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser from `COMMANDS`."""
    parser = argparse.ArgumentParser(
        prog="g0rd0n",
        description="A bookkeeping machine for a research programme. See AGENTS.md.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        metavar="PATH",
        help=f"path to the config file (default: {DEFAULT_CONFIG})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name, help_text in COMMANDS.items():
        subparsers.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. Returns a process exit status; raises nothing a user should see."""
    args = build_parser().parse_args(argv)

    if args.command == "version":
        print(f"g0rd0n {__version__}")
        return 0

    config_path: Path = args.config
    try:
        config = load(config_path)
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1

    if args.command == "config":
        _print_config(config_path, config)
        return 0

    return _report(doctor(config))


def _directory(name: str, path: Path) -> Check:
    if path.is_dir():
        return Check(name, True, str(path))
    return Check(name, False, f"{path} does not exist (create it, or fix the config)")


def _executable(name: str, path: Path) -> Check:
    if not path.is_file():
        return Check(name, False, f"{path} does not exist (build knk, or fix the config)")
    if not os.access(path, os.X_OK):
        return Check(name, False, f"{path} is not executable")
    return Check(name, True, str(path))


def _report(checks: list[Check]) -> int:
    for check in checks:
        status = "ok  " if check.ok else "FAIL"
        print(f"{status}  {check.name:<15}  {check.detail}")
    failed = sum(1 for check in checks if not check.ok)
    if failed:
        print(f"\n{failed} of {len(checks)} checks failed.", file=sys.stderr)
        return 1
    return 0


def _print_config(path: Path, config: Config) -> None:
    allowlist = ", ".join(config.network_allowlist) or "(empty: no external host is reachable)"
    print(f"config           {path}")
    print(f"kernel storage   {config.kernel_storage_root}")
    print(f"knk mcp_server   {config.kernel_mcp_server}")
    print(f"vault            {config.vault_root}")
    print(
        f"budget usd       session {config.session_usd:g}"
        f" / campaign {config.campaign_usd:g}"
        f" / standing {config.standing_usd:g}"
    )
    print(f"allowlist        {allowlist}")
