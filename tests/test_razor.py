"""The Razor, as tests: structural invariants over the source itself.

These are the two Phase 0 tests that no later phase may delete. They are cheap, they are
mechanical, and they enforce the two rules in AGENTS.md that are otherwise pure exhortation:
every module justifies its own existence, and no component reaches around its caller for
configuration.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "g0rd0n"

MARKER = "Deletion criterion:"

#: Names that mean "this module went looking for its configuration instead of being handed
#: it". `os.path.expanduser` is not on this list on purpose: expanding `~` is path
#: resolution, not configuration — the value being expanded still came from the config file.
ENV_NAMES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv"})


def modules() -> list[Path]:
    """Every module in the package, razor included."""
    return sorted(PACKAGE.rglob("*.py"))


def test_the_package_has_modules_to_check() -> None:
    """A razor with nothing to cut passes vacuously, which is worse than failing."""
    assert modules(), f"no modules found under {PACKAGE}"


def test_every_module_declares_a_deletion_criterion() -> None:
    """AGENTS.md, The Imperative (2): no settled Wager would be lost, no module.

    Until Phase 7 gives us `WagerId`s to point at, the criterion is prose naming the
    invariant the module protects. Phase 7 tightens this to a resolvable identifier; see
    docs/adr/0001-the-wager-is-the-primitive.md.
    """
    for module in modules():
        where = module.relative_to(PACKAGE.parents[1])
        docstring = ast.get_docstring(ast.parse(module.read_text(encoding="utf-8")))
        assert docstring, f"{where} has no module docstring"
        assert MARKER in docstring, f"{where} does not declare a '{MARKER}'"
        _, _, criterion = docstring.partition(MARKER)
        words = " ".join(criterion.split())
        assert len(words) >= 40, f"{where} declares a deletion criterion that says nothing"


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
