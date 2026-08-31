"""The Razor, as tests: structural invariants over the source itself.

Cheap, mechanical, and no later phase may delete them. They enforce the rules in AGENTS.md
that are otherwise pure exhortation: every module justifies its own existence, no component
reaches around its caller for configuration, and the kernel bridge has exactly the write
paths it says it has.

They are here rather than in `test_bridge.py` on purpose. The kernel tests need a built `knk`
and skip without one, and an invariant that can be skipped is an invariant that will be. These
parse source and need nothing.
"""

import ast
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "g0rd0n"
SUITE = Path(__file__).resolve().parent

BRIDGE = PACKAGE / "kernel" / "bridge.py"

MARKER = "Deletion criterion:"

#: A backticked identifier in a deletion criterion. Spaces are allowed inside because a long
#: test name gets wrapped across two lines of a docstring, and folding the line puts a space
#: where the wrap was; `_named` strips them back out. Criteria name tests without the `test_`
#: prefix, which is how they read as sentences: "`x` loses its verdict".
IDENTIFIER = re.compile(r"`([a-z0-9_][a-z0-9_ ]*)`")

#: Names that mean "this module went looking for its configuration instead of being handed
#: it". `os.path.expanduser` is not on this list on purpose: expanding `~` is path
#: resolution, not configuration — the value being expanded still came from the config file.
ENV_NAMES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv"})

#: Every knk tool that creates or alters an assertion, from `docs/mcp_server.md` §Mutating.
#: Interning an entity, a predicate, or a document is deliberately not here: those make a
#: name, not a claim, and the bridge needs them on every path including the read ones.
ASSERTING_TOOLS = frozenset(
    {
        "commit",
        "commit_by_name",
        "commit_hypothesis",
        "commit_retraction",
        "commit_superseding",
        "record_provenance",
        "merge_entities",
        "archive_segments_before",
        "write_snapshot",
    }
)

#: The bridge's entire write surface, as data. `hypothesise` is the only way a claim enters
#: (Phase 2) and `retract` the only way one leaves (Phase 6); knk gives a retraction its own
#: `Retraction` status, so neither can make g0rd0n *believe* anything — promotion needs Phase
#: 10's three keys and is not reachable from here at all.
#:
#: Widening this table is the point at which someone has to argue for a third write path in a
#: diff, rather than in a docstring nobody re-reads. `merge_entities` is the one to watch: knk
#: offers it, it is "not a belief" by the same argument that admits `retract`, and it would let
#: g0rd0n silently collapse two entities.
WRITE_PATHS: dict[str, set[str]] = {
    "hypothesise": {"commit_hypothesis"},
    "retract": {"commit_retraction", "record_provenance"},
}


def modules() -> list[Path]:
    """Every module in the package, razor included."""
    return sorted(PACKAGE.rglob("*.py"))


def test_the_package_has_modules_to_check() -> None:
    """A razor with nothing to cut passes vacuously, which is worse than failing."""
    assert modules(), f"no modules found under {PACKAGE}"


def test_every_module_declares_a_deletion_criterion() -> None:
    """AGENTS.md, The Imperative (2): no settled Wager would be lost, no module.

    Tightened in Phase 7 from a length floor to a **resolvable identifier**: the criterion
    must name at least one test that exists in this suite. ADR 0001 promised that tightening
    and expected the identifier to be a `WagerId` looked up in the kernel; ADR 0011 records
    why it resolves against the test suite instead, and why the length floor was the wrong
    check to keep — "every Phase 4 minimum test" clears forty characters and points at
    nothing.
    """
    known = named_tests()
    for module in modules():
        where = module.relative_to(PACKAGE.parents[1])
        docstring = ast.get_docstring(ast.parse(module.read_text(encoding="utf-8")))
        assert docstring, f"{where} has no module docstring"
        assert MARKER in docstring, f"{where} does not declare a '{MARKER}'"
        _, _, criterion = docstring.partition(MARKER)
        named = _named(criterion)
        assert named & known, (
            f"{where} declares a deletion criterion naming no test that exists. Name at least "
            f"one thing that loses its verdict without this module, in backticks: {sorted(named)}"
        )


def named_tests() -> set[str]:
    """Every test in this suite, by name, with and without its `test_` prefix."""
    found: set[str] = set()
    for path in sorted(SUITE.glob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                found |= {node.name, node.name.removeprefix("test_")}
    return found


def _named(criterion: str) -> set[str]:
    """The backticked identifiers a deletion criterion names, unwrapped."""
    folded = " ".join(criterion.split())
    return {match.replace(" ", "") for match in IDENTIFIER.findall(folded)}


def test_config_is_injected_never_read_from_env_inside_components() -> None:
    """AGENTS.md, Phase 0: config is injected, never discovered.

    Ambient configuration is how two runs that look identical in the log turn out to have
    been different runs. The config file is the only channel.
    """
    offenders = [
        f"{module.relative_to(PACKAGE.parents[1])}:{line}"
        for module in modules()
        for line in _env_reads(module)
    ]
    assert not offenders, "configuration read from the environment at: " + ", ".join(offenders)


def test_the_bridge_has_exactly_the_write_paths_it_declares() -> None:
    """AGENTS.md §Phase 2, and ADR 0008: two write paths, and a third is a decision.

    Structural rather than behavioural, because the rule is about the *surface*. A test that
    committed something and checked the status would pass happily beside a newly added
    `Bridge.merge` that nobody exercised.
    """
    assert _asserting_calls(BRIDGE) == WRITE_PATHS, (
        "the bridge's write surface has changed. A third way to alter an assertion is a "
        "decision that needs an ADR, not a method: see docs/adr/0008 and AGENTS.md §Phase 2."
    )


def test_no_module_reaches_past_the_bridge_to_the_kernel_client() -> None:
    """AGENTS.md §6: the Cortex must not know about MCP framing.

    `_client` is the JSON-RPC seam. Anything above `kernel/` touching it would be speaking
    protocol to a subprocess, which is both a layering inversion and a way around every check
    in this file.
    """
    allowed = {BRIDGE, PACKAGE / "kernel" / "mcp.py"}
    offenders = [
        f"{module.relative_to(PACKAGE.parents[1])}:{line}"
        for module in modules()
        if module not in allowed
        for line in _client_reads(module)
    ]

    assert not offenders, "the MCP client is reached directly at: " + ", ".join(offenders)


def _env_reads(module: Path) -> list[int]:
    """Line numbers where `module` reaches for the environment rather than its caller."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    accesses = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
        and node.attr in ENV_NAMES
    ]
    imports = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom) and _imports_env(node)
    ]
    return sorted(accesses + imports)


def _imports_env(node: ast.Import | ast.ImportFrom) -> bool:
    """True if the statement pulls the environment, or a .env loader, into scope."""
    module = node.module if isinstance(node, ast.ImportFrom) else None
    names = {alias.name for alias in node.names}
    if module == "os" and names & ENV_NAMES:
        return True
    roots = {(module or "").split(".")[0]} | {name.split(".")[0] for name in names}
    return "dotenv" in roots


def _asserting_calls(module: Path) -> dict[str, set[str]]:
    """Which of `module`'s methods call which assertion-altering knk tools."""
    found: dict[str, set[str]] = {}
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        tools = {
            call.args[0].value
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and _is_client_call(call.func)
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value in ASSERTING_TOOLS
        }
        if tools:
            found[node.name] = tools
    return found


def _is_client_call(func: ast.expr) -> bool:
    """True for `self._client.call(...)`, and nothing else."""
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "call"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "_client"
    )


def _client_reads(module: Path) -> list[int]:
    """Line numbers where `module` touches the MCP client rather than the bridge."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "_client"
    )
