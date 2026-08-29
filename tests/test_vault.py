"""The vault, as a projection. The four Phase 3 minimum tests, and what makes them bite.

The determinism tests run against a real kernel, because determinism against a fake kernel is
determinism of the fake. The rendering tests build a `Snapshot` by hand, because that is the
point of `render` being pure: most of what the vault does can be checked without a subprocess.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from g0rd0n import vault
from g0rd0n.config import Config
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref, VocabularyError, connect
from g0rd0n.kernel.vocabulary import KINDS
from g0rd0n.vault import note
from g0rd0n.vault.note import FOLDERS, MARKER_PATH, Edge, Snapshot, render

SEED = Provenance(source=Ref("source", "agents-md-seed"), method="AGENTS.md seed, unverified")


def an_edge(
    assertion_id: int = 1,
    subject: Ref | None = None,
    predicate: str = "hypothesises",
    obj: Ref | None = None,
    provenance: Provenance | None = SEED,
) -> Edge:
    return Edge(
        assertion_id=assertion_id,
        subject=subject or Ref("question", "q-001"),
        predicate=predicate,
        object=obj or Ref("hypothesis", "h-001"),
        status="Hypothesis",
        confidence=0.6,
        observed_at=1_700_000_000,
        supersedes_id=0,
        retracts_id=0,
        provenance=provenance,
    )


# --------------------------------------------------------------------------------------
# The four minimum tests
# --------------------------------------------------------------------------------------


def test_vault_rebuilds_deterministically_from_an_empty_directory(
    bridge: Bridge, tmp_path: Path
) -> None:
    """Same kernel, two empty directories, identical bytes. The permanent CI invariant.

    Built twice into *different* directories rather than twice into one, so that a projector
    which happened to leave the previous build in place could not pass.
    """
    _seed(bridge)
    first, second = tmp_path / "one", tmp_path / "two"

    vault.rebuild(bridge, first)
    vault.rebuild(bridge, second)

    assert _tree(first) == _tree(second)
    assert _tree(first), "the projection is empty, so this test proves nothing"


def test_rebuild_is_idempotent_byte_for_byte(bridge: Bridge, tmp_path: Path) -> None:
    """A second rebuild over the first changes nothing, and knows it changed nothing."""
    _seed(bridge)
    root = tmp_path / "vault"

    vault.rebuild(bridge, root)
    before = _tree(root)
    again = vault.rebuild(bridge, root)

    assert _tree(root) == before
    assert not again.edits, f"a clean rebuild reported edits: {again.edits.describe()}"


def test_refuted_hypothesis_note_shows_its_refutation_and_is_never_deleted(
    bridge: Bridge, tmp_path: Path
) -> None:
    """Append-only epistemics, projected: the refutation is *on* the note, not instead of it."""
    subject = Ref("hypothesis", "h-001")
    bridge.hypothesise(Claim(Ref("question", "q-001"), "hypothesises", subject, 0.6), SEED)
    bridge.hypothesise(
        Claim(Ref("result", "r-1"), "refutes", subject, 0.9),
        Provenance(Ref("source", "bench-run-7"), "measured, RAPL"),
    )
    root = tmp_path / "vault"

    vault.rebuild(bridge, root)
    text = (root / "Hypotheses" / "h-001.md").read_text(encoding="utf-8")

    assert "`refutes` this" in text
    assert "[[Results/r-1|result:r-1]]" in text
    assert "from [[Sources/bench-run-7|source:bench-run-7]] (measured, RAPL)" in text
    assert "`hypothesises` this" in text, "the refuted claim itself is still on the note"
    assert (root / "Results" / "r-1.md").is_file()


def test_superseded_charter_remains_linked_from_its_successor(
    bridge: Bridge, tmp_path: Path
) -> None:
    """A Charter is a `question`, and `refines` is how Phase 5 supersedes one.

    The old version keeps its note, names its successor in `superseded_by`, and is reachable
    from it — so "why did we stop asking it that way" always has somewhere to be answered.
    """
    old, new = Ref("question", "charter-001"), Ref("question", "charter-002")
    bridge.hypothesise(Claim(new, "refines", old, 0.8), SEED)
    root = tmp_path / "vault"

    vault.rebuild(bridge, root)
    superseded = (root / "Questions" / "charter-001.md").read_text(encoding="utf-8")
    successor = (root / "Questions" / "charter-002.md").read_text(encoding="utf-8")

    assert 'superseded_by: ["question:charter-002"]' in superseded
    assert "[[Questions/charter-002|question:charter-002]] `refines` this" in superseded
    assert "[[Questions/charter-001|question:charter-001]]" in successor


# --------------------------------------------------------------------------------------
# Determinism, where it could actually break
# --------------------------------------------------------------------------------------


def test_the_projection_does_not_depend_on_python_hash_ordering() -> None:
    """The determinism failure a same-process test cannot see.

    `render` walks sets on its way to a note — the entities in the snapshot, an entity's
    successors — and set iteration order depends on `PYTHONHASHSEED`, which is randomised per
    *process*. Two `render` calls in one test therefore agree even when the sort that makes
    them agree has been deleted. Two processes with different seeds do not.

    Cheap enough to keep: it renders a hand-built snapshot and needs no kernel.
    """
    seeds = [_render_under(seed) for seed in ("0", "1", "12345")]

    assert len(set(seeds)) == 1, "the projection depends on set iteration order"


#: Four successors refining one question, so `_superseded_by` has a set worth ordering.
RENDER_A_SNAPSHOT = """
from g0rd0n.kernel import Provenance, Ref
from g0rd0n.vault.note import Edge, Snapshot, render

def edge(assertion_id, successor):
    return Edge(
        assertion_id, Ref("question", successor), "refines", Ref("question", "c-001"),
        "Hypothesis", 0.5, 1700000000, 0, 0,
        Provenance(Ref("source", f"s-{assertion_id}"), "m"),
    )

snapshot = Snapshot(tuple(edge(i, f"c-00{i + 1}") for i in range(1, 5)))
print(repr(sorted(render(snapshot).items())))
"""


def _render_under(hash_seed: str) -> str:
    """Render a fixed snapshot in a fresh interpreter with `PYTHONHASHSEED` set."""
    return subprocess.run(
        [sys.executable, "-c", RENDER_A_SNAPSHOT],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    ).stdout


def test_render_is_a_pure_function_of_its_snapshot() -> None:
    """Twice from the same value, and once more with the edges shuffled."""
    edges = (an_edge(1), an_edge(2, obj=Ref("hypothesis", "h-002")), an_edge(3))

    assert render(Snapshot(edges)) == render(Snapshot(edges))
    assert render(Snapshot(edges)) == render(Snapshot(tuple(reversed(edges))))


def test_no_note_records_when_it_was_generated() -> None:
    """A rebuild timestamp would make every rebuild differ from the last, silently.

    The snapshot's only timestamp is 2023, so today's date appearing anywhere means the
    projection has read a clock — the one impurity that would break both minimum tests at
    once, and the one hardest to notice by eye.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    rendered = render(Snapshot((an_edge(),)))

    for path, text in rendered.items():
        assert today not in text, f"{path} records when the rebuild ran"


def test_a_note_carries_the_five_frontmatter_fields_agents_md_names() -> None:
    """`assertion_id`, `status`, `confidence`, `provenance` per claim; `superseded_by` once."""
    text = render(Snapshot((an_edge(),)))["Hypotheses/h-001.md"]

    assert "assertion_id: 1" in text
    assert 'status: "Hypothesis"' in text
    assert "confidence: 0.6" in text
    assert 'provenance: "source:agents-md-seed (AGENTS.md seed, unverified)"' in text
    assert "superseded_by: []" in text


def test_every_kind_has_a_folder() -> None:
    """A kind with nowhere to live would be dropped from the projection without a word."""
    assert KINDS - set(FOLDERS) == set()


def test_every_entity_mentioned_anywhere_gets_exactly_one_note() -> None:
    """Subjects, objects, and provenance sources alike: the index covers what the kernel has."""
    rendered = render(Snapshot((an_edge(),)))
    notes = set(rendered) - {MARKER_PATH, note.README_PATH}

    assert notes == {
        "Questions/q-001.md",
        "Hypotheses/h-001.md",
        "Sources/agents-md-seed.md",
    }


def test_a_method_with_yaml_metacharacters_does_not_break_the_frontmatter() -> None:
    """`method` is free text written by a cell, and ends up in YAML."""
    nasty = Provenance(Ref("source", "s-1"), 'table 3: "at the wall", 40% \\ 60%\nsecond line')
    text = render(Snapshot((an_edge(provenance=nasty),)))["Hypotheses/h-001.md"]

    assert '\\"at the wall\\"' in text
    assert "\\\\" in text
    assert "\\n" in text
    assert len([line for line in text.splitlines() if line == "---"]) == 2


# --------------------------------------------------------------------------------------
# Hand-edits, and not destroying things that are not vaults
# --------------------------------------------------------------------------------------


def test_a_hand_edit_is_reported_before_it_is_overwritten(bridge: Bridge, tmp_path: Path) -> None:
    """AGENTS.md §Phase 3: a rebuild may overwrite human prose, but never quietly."""
    _seed(bridge)
    root = tmp_path / "vault"
    vault.rebuild(bridge, root)
    edited = root / "Hypotheses" / "h-001.md"
    edited.write_text("I think this one is right\n", encoding="utf-8")
    (root / "Questions" / "notes-to-self.md").write_text("mine\n", encoding="utf-8")

    done = vault.rebuild(bridge, root)

    assert done.edits.modified == ("Hypotheses/h-001.md",)
    assert done.edits.extra == ("Questions/notes-to-self.md",)
    assert edited.read_text(encoding="utf-8") != "I think this one is right\n"
    assert not (root / "Questions" / "notes-to-self.md").exists()


def test_dry_run_reports_what_would_be_lost_and_writes_nothing(
    bridge: Bridge, tmp_path: Path
) -> None:
    _seed(bridge)
    root = tmp_path / "vault"
    vault.rebuild(bridge, root)
    (root / "Hypotheses" / "h-001.md").write_text("mine\n", encoding="utf-8")

    done = vault.rebuild(bridge, root, dry_run=True)

    assert done.dry_run and done.edits.modified == ("Hypotheses/h-001.md",)
    assert (root / "Hypotheses" / "h-001.md").read_text(encoding="utf-8") == "mine\n"


def test_rebuild_refuses_to_drop_a_directory_it_did_not_build(
    bridge: Bridge, tmp_path: Path
) -> None:
    """`vault.root` is a config value, and a config value can be wrong."""
    someone_elses = tmp_path / "documents"
    someone_elses.mkdir()
    (someone_elses / "thesis.md").write_text("years of work\n", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="refusing to drop it"):
        vault.rebuild(bridge, someone_elses)

    assert (someone_elses / "thesis.md").read_text(encoding="utf-8") == "years of work\n"


def test_an_empty_or_missing_directory_is_a_first_run_not_a_refusal(
    bridge: Bridge, tmp_path: Path
) -> None:
    _seed(bridge)
    empty = tmp_path / "empty"
    empty.mkdir()

    assert vault.rebuild(bridge, empty).notes > 0
    assert vault.rebuild(bridge, tmp_path / "absent").notes > 0


def test_the_marker_is_what_makes_the_next_rebuild_possible(bridge: Bridge, tmp_path: Path) -> None:
    """Losing the marker is a refusal, not a silent reformat of whatever is there."""
    _seed(bridge)
    root = tmp_path / "vault"
    vault.rebuild(bridge, root)
    (root / MARKER_PATH).unlink()

    with pytest.raises(vault.VaultError, match=MARKER_PATH):
        vault.rebuild(bridge, root)


# --------------------------------------------------------------------------------------
# One-way, and unbuildable names kept out of the kernel
# --------------------------------------------------------------------------------------


def test_the_vault_package_never_reads_a_note_back_as_fact() -> None:
    """The arrow points one way. The only read is `differences`, and it warns and forgets."""
    readers = [
        name
        for name in dir(vault)
        if not name.startswith("_") and name in {"load", "parse", "read", "import_notes"}
    ]

    assert readers == []


def test_an_entity_name_that_would_escape_the_vault_is_rejected_at_the_bridge() -> None:
    """The kernel is append-only, so an unprojectable name is permanent. Reject it upstream."""
    for name in ["../etc/passwd", "a/b", "..", ".hidden", " leading", "trailing ", "nul\x00"]:
        with pytest.raises(VocabularyError, match="not a usable entity name"):
            Ref("hypothesis", name)


def test_a_kernel_with_nothing_in_it_still_projects_a_readable_vault(
    kernel_config: Config, tmp_path: Path
) -> None:
    """Rebuilding from an empty kernel is a real case: it is what `--dry-run` hits on day one."""
    root = tmp_path / "vault"
    with connect(kernel_config) as empty:
        done = vault.rebuild(empty, root)

    assert done.notes == 2
    assert (root / MARKER_PATH).is_file()
    assert "nothing yet" in (root / "README.md").read_text(encoding="utf-8")


def _seed(bridge: Bridge) -> None:
    """A small argument: a question, a hypothesis, a prediction, an experiment, a result."""
    question = Ref("question", "q-001")
    hypothesis = Ref("hypothesis", "h-001")
    bridge.hypothesise(Claim(question, "hypothesises", hypothesis, 0.6), SEED)
    bridge.hypothesise(
        Claim(hypothesis, "predicts", Ref("observation", "o-lower-joules"), 0.7), SEED
    )
    bridge.hypothesise(
        Claim(Ref("experiment", "e-1"), "tests", hypothesis, 0.9),
        Provenance(Ref("source", "bench-run-7"), "measured, RAPL"),
    )


def _tree(root: Path) -> dict[str, str]:
    """Every file under `root`, as `{relative path: content}`. The unit of comparison."""
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
