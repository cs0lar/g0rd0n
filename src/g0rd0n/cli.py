"""The command line: the only place that reads a config file and the only place that exits.

Nine commands, and no more. `version` says what is installed, `config` says what was loaded,
`doctor` says what is missing, `cost` says what was spent and on which claim, `vault`
rebuilds the projection, `charter` shows the current question and puts it into the kernel,
`evidence` searches the literature and audits g0rd0n's own unsourced numbers against it,
`portfolio` says what is being bet on and what is worth spending on next, and `bench` prints
the chartered task families and lets a person score one instance by hand.

`bench` is there because AGENTS.md §Phase 8 asks for a bench "small enough that one person can
verify it is not lying", and the cheapest way to verify a checker is to read one instance and
grade it yourself.

`evidence` is the first command that reaches the open network, and the first that costs
anything — wall-clock, against a wager, through the ledger like everything else.

This is also the one place a `BudgetExhausted` is caught. Everywhere else it propagates, so
that `open_session` can settle what is open on its way past.

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

from g0rd0n import __version__, vault
from g0rd0n.config import Config, ConfigError, load
from g0rd0n.cortex import allocator, portfolio
from g0rd0n.cortex import charter as charter_document
from g0rd0n.cortex.allocator import AllocationError, Board, Exhausted, Next
from g0rd0n.cortex.charter import CharterError
from g0rd0n.cortex.wager import WagerError
from g0rd0n.evidence import seeds
from g0rd0n.evidence.channel import EvidenceError
from g0rd0n.evidence.citation import UnresolvableCitation
from g0rd0n.instruments import fetch, search, tasks
from g0rd0n.instruments.fetch import FetchError
from g0rd0n.instruments.search import SearchError
from g0rd0n.instruments.tasks import TaskError
from g0rd0n.kernel import KernelError
from g0rd0n.kernel import connect as connect_kernel
from g0rd0n.ledger import BudgetExhausted, JournalError, Ledger, LedgerError
from g0rd0n.ledger import report as cost_report
from g0rd0n.vault import VaultError

DEFAULT_CONFIG = Path("config/g0rd0n.toml")

#: The whole CLI surface, as data. Phase 0's review question — "does the repo do nothing yet,
#: loudly and correctly?" — is answered in this table. Adding a command is a deliberate act
#: with a test to update, not a drive-by.
COMMANDS: dict[str, str] = {
    "version": "print the version and exit",
    "doctor": "check that the kernel, the vault, and the config are where they claim to be",
    "config": "print the resolved configuration",
    "cost": "report what has been spent, and on which claim",
    "vault": "rebuild the Obsidian vault as a projection of the kernel",
    "charter": "show the well-posed question, or put a signed one into the kernel",
    "evidence": "search primary literature, and audit the seed numbers against it",
    "portfolio": "show the candidate families, and what is worth spending on next",
    "bench": "show the chartered task families, or print and score one instance",
}

#: `vault` takes exactly one action today. It is spelled out rather than implied so that
#: `g0rd0n vault` on its own is an error with a list, not a rebuild nobody asked for.
VAULT_ACTIONS = ("rebuild",)

#: Same, for `charter`. `show` reads the two documents and says what they fix; `commit` is
#: the gated one — it refuses an unsigned charter and refuses to write the same one twice.
CHARTER_ACTIONS = ("show", "commit")

#: `evidence search QUERY` finds papers; `seed` commits AGENTS.md's unsourced numbers as
#: hypotheses; `audit` resolves what a primary source says about each. `audit` is re-runnable:
#: the seeds are idempotent and a source already supporting a claim is skipped.
EVIDENCE_ACTIONS = ("search", "seed", "audit")

#: `portfolio seed` commits the nine candidate families and their kill criteria under the
#: Charter's question; `status` reads the board back, flagging any family still standing only
#: because nothing tried to kill it; `next` ranks the open survey wagers cheapest-falsifier
#: first, or says the question is exhausted and hands back the criticisms a new one must
#: answer. None of them spends: `next` prices a plan, it does not run it.
PORTFOLIO_ACTIONS = ("seed", "status", "next")

#: `bench families` lists what CHARTER.md charters, with the version each is measured under;
#: `bench sample` prints one instance exactly as an arm would be shown it, and grades an
#: `--answer` with the family's own checker. Neither runs an arm and neither spends: this is
#: the affordance that lets a person check the bench by hand before trusting a curve from it.
BENCH_ACTIONS = ("families", "sample")


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
        _directory("ledger", config.ledger_journal.parent),
        _directory("human queue", config.human_queue),
        _api_key(config),
        _endpoint(config),
        _charter(config),
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "price the work without doing it or recording it. Nothing spends money yet, so "
            "today this only affects `vault rebuild`, which reads and compares but writes "
            "nothing; it takes effect for spend with the first cell (Phase 4)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name, help_text in COMMANDS.items():
        subparser = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "cost":
            subparser.add_argument(
                "--by",
                choices=cost_report.BY,
                default="wager",
                help="what to group spend by (default: wager)",
            )
        if name == "vault":
            subparser.add_argument(
                "action",
                choices=VAULT_ACTIONS,
                help="drop the vault and project it again from the kernel",
            )
        if name == "charter":
            subparser.add_argument(
                "action",
                choices=CHARTER_ACTIONS,
                help="print the current charter, or commit a signed one to the kernel",
            )
        if name == "portfolio":
            subparser.add_argument(
                "action",
                choices=PORTFOLIO_ACTIONS,
                help="seed the families, show where they stand, or rank what to run next",
            )
        if name == "bench":
            subparser.add_argument(
                "action",
                choices=BENCH_ACTIONS,
                help="list the chartered families, or print and score one instance",
            )
            subparser.add_argument(
                "--family", default=tasks.FAMILIES[0].slug, help="which family to sample from"
            )
            subparser.add_argument("--size", type=int, default=6, help="the instance's size")
            subparser.add_argument("--seed", type=int, default=0, help="the instance's seed")
            subparser.add_argument(
                "--answer", help="score this answer with the family's own checker"
            )
        if name == "evidence":
            subparser.add_argument("action", choices=EVIDENCE_ACTIONS, help="what to do")
            subparser.add_argument(
                "query", nargs="?", help="what to search for (required by `search`)"
            )
            subparser.add_argument(
                "--limit",
                type=int,
                default=search.DEFAULT_LIMIT,
                help=f"how many results to return (default: {search.DEFAULT_LIMIT})",
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. Returns a process exit status; raises nothing a user should see.

    The single catch site for `BudgetExhausted`. It is an outcome, not a crash: by the time
    it arrives here `open_session` has already settled everything that was open, so there is
    nothing to clean up and nothing lost — only a session that stopped where it said it
    would.
    """
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

    try:
        if args.command == "config":
            _print_config(config_path, config)
            return 0
        if args.command == "cost":
            print(cost_report.read(config.ledger_journal, args.by))
            return 0
        if args.command == "vault":
            return _vault(config, dry_run=args.dry_run)
        if args.command == "charter":
            return _charter_command(config, args.action, dry_run=args.dry_run)
        if args.command == "evidence":
            return _evidence(config, args.action, args.query, limit=args.limit)
        if args.command == "portfolio":
            return _portfolio(config, args.action)
        if args.command == "bench":
            return _bench(args.action, args.family, args.size, args.seed, args.answer)
        return _report(doctor(config))
    except BudgetExhausted as exc:
        print(f"budget: {exc}", file=sys.stderr)
        return 1
    except CharterError as exc:
        print(f"charter: {exc}", file=sys.stderr)
        return 1
    except (SearchError, FetchError, UnresolvableCitation, EvidenceError) as exc:
        print(f"evidence: {exc}", file=sys.stderr)
        return 1
    except (WagerError, AllocationError) as exc:
        print(f"portfolio: {exc}", file=sys.stderr)
        return 1
    except TaskError as exc:
        print(f"bench: {exc}", file=sys.stderr)
        return 1
    except (LedgerError, JournalError) as exc:
        print(f"ledger: {exc}", file=sys.stderr)
        return 1
    except VaultError as exc:
        print(f"vault: {exc}", file=sys.stderr)
        return 1
    except KernelError as exc:
        print(f"kernel: {exc}", file=sys.stderr)
        return 1


def _vault(config: Config, *, dry_run: bool) -> int:
    """Rebuild the vault, saying what it is about to overwrite before it does.

    `--dry-run` reads the kernel and compares, and writes nothing: the way to find out what a
    rebuild would cost you in hand-edits without paying it.
    """
    with connect_kernel(config) as bridge:
        done = vault.rebuild(bridge, config.vault_root, dry_run=dry_run)

    for line in done.edits.describe():
        print(f"warning: {line}", file=sys.stderr)
    if done.edits:
        print(
            f"warning: {len(done.edits.describe())} hand-edited or unexpected files"
            + (" would be lost" if dry_run else " were overwritten")
            + "; prose that should last belongs in the kernel first.",
            file=sys.stderr,
        )

    verb = "would write" if dry_run else "wrote"
    print(f"{verb} {done.notes} files to {config.vault_root}")
    return 0


#: The wager the seed audit spends against. A string until Phase 7 mints `WagerId`s to point
#: at; the chain from this dollar to a question is `AGENTS.md` §The Question, which is the
#: thing being audited.
AUDIT_WAGER = "w-006-seed-audit"


def _evidence(config: Config, action: str, query: str | None, *, limit: int) -> int:
    """Search the literature, seed g0rd0n's unsourced numbers, or audit them against it."""
    http = fetch.Http(allowlist=config.network_allowlist)
    if action == "search":
        if not query:
            print("evidence: `search` needs something to search for", file=sys.stderr)
            return 2
        for found in search.Arxiv(fetcher=http).find(query, limit=limit):
            print(f"{found.identifier:<16}  {found.published[:10]}  {found.title}")
        return 0

    with connect_kernel(config) as bridge:
        if action == "seed":
            committed = seeds.commit(bridge)
            print(f"committed {len(committed)} seed claims as unverified hypotheses")
            return 0
        done = seeds.audit(
            bridge=bridge,
            fetcher=http,
            ledger=Ledger(config, session="audit", campaign="c-1", phase="6b"),
            wager_id=AUDIT_WAGER,
        )
    _print_audit(done)
    return 0


def _print_audit(done: seeds.Audited) -> None:
    sources = ", ".join(str(source) for source in done.ingested.sources) or "(none)"
    print(f"seeded {len(done.seeded)}, committed {len(done.ingested.assertions)} from {sources}")
    print(f"fetching took {done.ingested.cost.seconds:.1f}s\n")
    for seed, confidence in done.standing:
        print(f"  {confidence:.2f}  {seed.hypothesis.name}")
    if done.unverified:
        print("\nnot corroborated, and not retracted — no source found is not a source that")
        print("disagrees:")
        for seed, why in done.unverified:
            print(f"  {seed.hypothesis.name}\n      {why}")


def _portfolio(config: Config, action: str) -> int:
    """Seed the candidate families, read the board, or rank what to run next.

    Every action needs the Charter's question, and `seed` additionally needs that question to
    be *in the kernel*: committing families under a question nobody committed would create the
    entity by side effect and leave a portfolio hanging off a charter that was never signed.
    "No Wager without a parent Question" (AGENTS.md §4), one level up.
    """
    question = charter_document.load(config.charter_path, config.charter_definitions).ref
    with connect_kernel(config) as bridge:
        if action == "seed":
            if not bridge.assertions_for(question):
                print(
                    f"portfolio: {question} is not in the kernel. Sign CHARTER.md and run "
                    "`g0rd0n charter commit` first — a portfolio hanging off an uncommitted "
                    "question is a field of candidates nobody asked a question about.",
                    file=sys.stderr,
                )
                return 1
            committed = portfolio.commit(bridge, question)
            print(f"committed {len(committed)} assertions for {len(portfolio.FAMILIES)} families")
            return 0
        board = allocator.read(bridge, question, portfolio.FAMILIES)

    if action == "status":
        _print_board(board)
        return 0
    _print_allocation(allocator.allocate(board, portfolio.surveys(question)))
    return 0


def _print_board(board: Board) -> None:
    print(f"question   {board.question}\n")
    for standing in board.standings:
        flags = [
            flag
            for flag, on in (
                ("REFUTED", standing.refuted),
                ("untested", standing.untested),
                ("out of patience", standing.out_of_patience),
                ("control arm", standing.family.control_arm),
            )
            if on
        ]
        tried = f"{standing.attempts} tried, {standing.conclusive} settled it"
        print(
            f"  {standing.belief:.2f}  {standing.family.slug:<30}  {tried:<26}  {'; '.join(flags)}"
        )
    print(
        "\nA family flagged `untested` is standing because nothing has tried to kill it, "
        "which\nis not the same as having survived (AGENTS.md §Phase 7)."
    )


def _print_allocation(allocation: Next | Exhausted) -> None:
    """What to run next, or why nothing is worth running."""
    if isinstance(allocation, Next):
        best = allocation.run
        print(f"run next   {best.wager.id}")
        print(f"           {best.why}")
        print(f"           P(flip) {best.flip:.2f} x value {best.value:.2f} / ${best.price:.2f}")
        print(f"           kill: {best.wager.kill}\n")
    else:
        print(f"EXHAUSTED  {allocation.reason}\n")
        print("This question returns to the Question Engine. A superseding CHARTER.md needs a")
        print("`## Criticisms` section, and these are the ones its own record earned:\n")
        for criticism in allocation.criticisms:
            print(f"  - {criticism}")
        print()
    for ranked in allocation.ranking:
        print(f"  {ranked.score:8.5f}  {ranked.wager.label:<38}  {ranked.why}")


def _bench(action: str, slug: str, size: int, seed: int, answer: str | None) -> int:
    """List the chartered families, or print one instance and optionally grade an answer.

    Neither action runs an arm, reaches the network, or touches the kernel. The Charter's
    `cap` needs a meter and a budget beside it; what this prints is the questions and the
    checker, which is the half a person can verify unaided.
    """
    if action == "families":
        for chartered in tasks.FAMILIES:
            print(f"{chartered.slug}  {chartered.version}  {chartered.what}")
            print(
                f"      size is {chartered.size_is}; threshold {chartered.threshold:g}; "
                f"ceiling {chartered.ceiling_seconds:g}s per instance"
            )
            print(f"      answer: {chartered.answers}\n")
        print("A family is added by superseding CHARTER.md, never by appending to this list.")
        return 0

    chartered = tasks.family(slug)
    instance = chartered.instance(size, seed)
    print(f"{chartered.slug}@{chartered.version}  size {size}  seed {seed}\n")
    print(instance.question)
    print(f"\nchecker reads   {instance.data}")
    if answer is not None:
        print(f"answer          {answer!r}")
        print(f"score           {chartered.score(instance, answer):.4f}")
    return 0


def _charter_command(config: Config, action: str, *, dry_run: bool) -> int:
    """Show the current question, or put it into the kernel.

    `commit` under `--dry-run` does every check and touches no kernel, so "would this be
    accepted?" is answerable without a running `knk` and without writing anything.
    """
    current = charter_document.load(config.charter_path, config.charter_definitions)
    if action == "show":
        _print_charter(config, current)
        return 0

    if dry_run:
        print(f"would commit {current.name}: {len(charter_document.ELEMENTS)} asks edges")
        if current.supersedes is not None:
            print(f"...and {len(current.criticisms)} refines edges to {current.supersedes}")
        return 0
    with connect_kernel(config) as bridge:
        committed = charter_document.commit(bridge, current)
    print(f"committed {current.name} as {len(committed)} assertions")
    return 0


def _print_charter(config: Config, current: charter_document.Charter) -> None:
    signature = f"signed by {current.signatory}" if current.signed else "UNSIGNED"
    print(f"charter          {current.name}  ({signature})")
    print(f"file             {config.charter_path}")
    print(f"definitions      {current.definitions}  ({config.charter_definitions})")
    print(f"supersedes       {current.supersedes or '(nothing: this is the first charter)'}")
    for criticism in current.criticisms:
        print(f"  criticism      {criticism}")
    for heading, body in current.elements.items():
        print(f"\n## {heading}\n{body}")
    if not current.signed:
        print(
            f"\nUnsigned. A human reviewer signs the Charter before it can enter the kernel: "
            f"add a '## {charter_document.SIGNATURE}' section naming you, the date, and "
            f"{current.name}."
        )


def _charter(config: Config) -> Check:
    """Is there a well-posed question, does it agree with its definitions, and did a human
    sign it?

    Unsigned is a failing check rather than a note. AGENTS.md §Phase 5 makes the signature a
    gate, and a gate that reports itself as fine when it is shut is not a gate.
    """
    try:
        current = charter_document.load(config.charter_path, config.charter_definitions)
    except CharterError as exc:
        return Check("charter", False, str(exc))
    if not current.signed:
        return Check("charter", False, f"{current.name} is unsigned (see `g0rd0n charter show`)")
    return Check("charter", True, f"{current.name}, signed by {current.signatory}")


def _directory(name: str, path: Path) -> Check:
    if path.is_dir():
        return Check(name, True, str(path))
    return Check(name, False, f"{path} does not exist (create it, or fix the config)")


def _api_key(config: Config) -> Check:
    """Is there a key, and is it only readable by its owner?

    The mode check is a finding rather than a refusal: a world-readable key is the user's to
    fix, and `doctor` exists to say what is wrong on a machine, not to change it.
    """
    path = config.model_api_key_file
    if not path.is_file():
        return Check("model api key", False, f"{path} does not exist (create it, or fix config)")
    if not path.read_text(encoding="utf-8").strip():
        return Check("model api key", False, f"{path} is empty")
    mode = path.stat().st_mode & 0o077
    if mode:
        return Check("model api key", False, f"{path} is readable by others (chmod 600 it)")
    return Check("model api key", True, str(path))


def _endpoint(config: Config) -> Check:
    """A model endpoint off the allowlist is a run that will refuse at the first call."""
    try:
        fetch.check_host(config.model_endpoint, config.network_allowlist)
    except fetch.NetworkRefused as exc:
        return Check("model endpoint", False, str(exc))
    return Check("model endpoint", True, config.model_endpoint)


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
    print(f"ledger journal   {config.ledger_journal}")
    print(
        f"budget usd       session {config.session_usd:g}"
        f" / campaign {config.campaign_usd:g}"
        f" / standing {config.standing_usd:g}"
    )
    print(f"charter          {config.charter_path}")
    print(f"definitions      {config.charter_definitions}")
    print(f"allowlist        {allowlist}")
