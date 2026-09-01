"""The Question Engine: what a charter must fix, and how one replaces another.

Phase 5's three minimum tests are here, plus the gates around them. The tests that touch the
kernel use a real `knk` and a throwaway storage root, like every other kernel test in this
repository: a supersession chain verified against a mock is a chain verified against what its
author believed knk does.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from g0rd0n.content import version_of
from g0rd0n.cortex import charter
from g0rd0n.kernel import Bridge, Ref

REPO = Path(__file__).resolve().parents[1]

#: Placeholder prose for the eight things a charter must fix. Deliberately not the real
#: Charter's text: these tests are about the machine, and the shipped documents get their own
#: test below.
ELEMENT_TEXT: Mapping[str, str] = {
    heading: f"What this charter fixes under {heading}, said in one line."
    for heading in charter.ELEMENTS
}


def written(
    *,
    elements: Mapping[str, str] | None = None,
    definitions: str = "0123456789ab",
    supersedes: str | None = None,
    criticisms: Sequence[str] = (),
    extra: Mapping[str, str] | None = None,
    preamble: str = "# Charter\n",
) -> str:
    """Render a charter document. Unsigned; `signed` adds the signature that names it."""
    sections = dict(elements if elements is not None else ELEMENT_TEXT)
    sections[charter.DEFINITIONS] = definitions
    if supersedes is not None:
        sections[charter.SUPERSEDES] = supersedes
    if criticisms:
        sections[charter.CRITICISMS] = "\n".join(f"- {item}" for item in criticisms)
    sections.update(extra or {})
    body = "\n\n".join(f"## {heading}\n\n{text}" for heading, text in sections.items())
    return f"{preamble}\n{body}\n"


def signed(text: str, who: str = "A Reviewer, 2026-08-30") -> str:
    """Sign a charter the way a human does: one line naming them and the version they read."""
    version = charter.parse(text).version
    return f"{text}\n## {charter.SIGNATURE}\n\n{who}, charter-{version}\n"


def edges(bridge: Bridge, subject: Ref) -> list[tuple[str, Ref, str]]:
    """Every assertion about `subject`, as (predicate, object, provenance method)."""
    resolved = []
    for assertion in bridge.assertions_for(subject):
        provenance = bridge.provenance_for(assertion.id)
        resolved.append(
            (
                bridge.predicate_of(assertion.predicate),
                bridge.name_of(assertion.object),
                provenance.method if provenance else "",
            )
        )
    return resolved


# --- the three minimum tests -----------------------------------------------------------


def test_charter_without_a_named_fixed_resource_is_rejected() -> None:
    """AGENTS.md §Phase 5: the Charter must fix the resource held fixed.

    Both ways of not fixing it are the same failure: the section can be absent, or it can be
    a heading with nothing under it, and a heading with nothing under it fixes nothing.
    """
    missing = dict(ELEMENT_TEXT)
    del missing["Resource held fixed"]
    with pytest.raises(charter.CharterError, match="Resource held fixed"):
        charter.parse(written(elements=missing))

    with pytest.raises(charter.CharterError, match="empty"):
        charter.parse(written(elements={**ELEMENT_TEXT, "Resource held fixed": ""}))

    # ...and the other seven are checked the same way, from the same table.
    for heading in charter.ELEMENTS:
        without = {name: text for name, text in ELEMENT_TEXT.items() if name != heading}
        with pytest.raises(charter.CharterError, match=heading):
            charter.parse(written(elements=without))


def test_charter_revision_supersedes_and_never_overwrites(bridge: Bridge) -> None:
    """A new charter is a new question, linked to the old one by one edge per criticism.

    The old charter is not edited, not retracted, and not replaced: its assertions are still
    there afterwards, with the same ids, which is what makes "why did we stop asking it that
    way" answerable rather than a thing somebody remembers.
    """
    first = charter.parse(signed(written()))
    charter.commit(bridge, first)
    before = bridge.assertions_for(first.ref)
    assert len(before) == len(charter.ELEMENTS)

    complaints = (
        "it fixes a resource nobody can measure with the instrument it names",
        "its capability metric is a single accuracy, which hides the size dependence",
    )
    second = charter.parse(
        signed(
            written(
                elements={**ELEMENT_TEXT, "Energy instrument": "A wall meter at 1 Hz."},
                supersedes=first.name,
                criticisms=complaints,
            )
        )
    )
    assert second.version != first.version
    charter.commit(bridge, second)

    after = bridge.assertions_for(first.ref)
    assert [assertion.id for assertion in after] == [assertion.id for assertion in before]
    assert all(assertion.status == "Hypothesis" for assertion in after)

    refines = [edge for edge in edges(bridge, second.ref) if edge[0] == "refines"]
    assert [edge[1] for edge in refines] == [first.ref, first.ref]
    assert [complaint in edge[2] for complaint, edge in zip(complaints, refines, strict=True)] == [
        True,
        True,
    ], "each criticism travels with the edge it caused"


def test_every_definition_has_a_worked_example() -> None:
    """AGENTS.md §Phase 5: a definition that cannot be applied to one is not yet a definition.

    Checked against the file this repository actually ships, so the rule cannot pass on
    synthetic input while the real document quietly stops obeying it.
    """
    shipped = charter.definitions((REPO / "docs" / "charter" / "definitions.md").read_text("utf-8"))
    assert len(shipped) >= 8
    assert all(definition.example for definition in shipped)
    assert all(definition.body for definition in shipped)

    with pytest.raises(charter.CharterError, match="no worked example"):
        charter.definitions("## Joules\n\nEnergy, in the SI unit.\n")
    with pytest.raises(charter.CharterError, match="empty worked example"):
        charter.definitions(f"## Joules\n\nEnergy.\n\n{charter.WORKED_EXAMPLE}\n")
    with pytest.raises(charter.CharterError, match="nothing defined"):
        charter.definitions(f"## Joules\n\n{charter.WORKED_EXAMPLE} 1 J is a joule.\n")
    with pytest.raises(charter.CharterError, match="defines nothing"):
        charter.definitions("# Definitions\n\nComing soon.\n")


# --- the gates around them -------------------------------------------------------------


def test_the_shipped_charter_and_definitions_are_one_document() -> None:
    """The repository's own Charter loads, and names the definitions file it ships with.

    Not asserted to be signed: a human reviewer signs it, and until they do `charter commit`
    refuses. That refusal is the Phase 5 gate working, not a broken test.

    What it supersedes is deliberately not pinned by name. Supersession is the expected
    lifecycle of this file, so pinning the predecessor would make every new question a test
    edit and would assert nothing that `parse` does not already enforce. The shape is what
    matters: it replaces something, and it says why.
    """
    current = charter.load(REPO / "CHARTER.md", REPO / "docs" / "charter" / "definitions.md")

    assert current.supersedes is not None, "the seed framing is not the operative question"
    assert current.criticisms, "no supersession without a criticism"
    assert set(current.elements) == set(charter.ELEMENTS)
    assert "Turing" in current.elements["Question"], "the Turing trap is what this first attacks"


def test_a_charter_that_supersedes_without_a_criticism_is_rejected() -> None:
    """No supersession without a reason, and no reason pointing at nothing.

    Both directions, because either half alone produces a record that cannot be read later:
    a `refines` edge with no criticism, or a criticism with no edge to travel on.
    """
    with pytest.raises(charter.CharterError, match="what was wrong"):
        charter.parse(written(supersedes="charter-0123456789ab"))
    with pytest.raises(charter.CharterError, match="nothing to point at"):
        charter.parse(written(criticisms=("it fixes nothing measurable",)))


def test_an_unsigned_charter_is_never_committed(bridge: Bridge) -> None:
    """AGENTS.md §Phase 5: the human reviewer signs the Charter. A gate, not a notification."""
    unsigned = charter.parse(written())
    assert not unsigned.signed

    with pytest.raises(charter.CharterError, match="unsigned"):
        charter.commit(bridge, unsigned)
    assert not bridge.assertions_for(unsigned.ref), "a refused charter leaves no trace"


def test_the_signature_names_the_version_it_signed() -> None:
    """Signing does not change the version, so the signature carries the version instead.

    Without that, editing the body after a signature would leave the name attached to text
    nobody read. The version moves, the signature does not, and the mismatch is the alarm.
    """
    text = written()
    assert charter.parse(text).version == charter.parse(signed(text)).version

    edited = signed(text).replace("said in one line", "said in one line, revised")
    with pytest.raises(charter.CharterError, match="changed after it was signed"):
        charter.parse(edited)


def test_a_charter_is_never_committed_twice(bridge: Bridge) -> None:
    """Recommitting would double every edge and make the record say it twice."""
    current = charter.parse(signed(written()))
    charter.commit(bridge, current)

    with pytest.raises(charter.CharterError, match="already in the kernel"):
        charter.commit(bridge, current)
    assert len(bridge.assertions_for(current.ref)) == len(charter.ELEMENTS)


def test_a_committed_charter_asks_one_statement_per_thing_it_fixes(bridge: Bridge) -> None:
    """The eight commitments become eight `asks` edges, each citing the section it came from."""
    current = charter.parse(signed(written()))
    charter.commit(bridge, current)

    committed = edges(bridge, current.ref)
    assert [edge[0] for edge in committed] == ["asks"] * len(charter.ELEMENTS)
    assert [edge[1] for edge in committed] == [
        Ref("statement", f"{current.name}-{slug}") for slug in charter.ELEMENTS.values()
    ]
    assert all("knk document" in edge[2] for edge in committed), "the charter's text is citable"
    assert any("§Resource held fixed" in edge[2] for edge in committed)


def test_editing_a_definition_supersedes_the_charter_rather_than_amending_it(
    tmp_path: Path,
) -> None:
    """The Charter names its definitions by version, so redefining a term breaks the pair."""
    definitions_path = tmp_path / "definitions.md"
    definitions_path.write_text(
        f"## Joule\n\nThe SI unit of energy.\n\n{charter.WORKED_EXAMPLE} 20 W for 1 s is 20 J.\n",
        encoding="utf-8",
    )
    charter_path = tmp_path / "CHARTER.md"
    version = version_of(definitions_path.read_bytes())
    charter_path.write_text(written(definitions=version), encoding="utf-8")
    assert charter.load(charter_path, definitions_path).definitions == version

    definitions_path.write_text(
        f"## Joule\n\nThe SI unit of work.\n\n{charter.WORKED_EXAMPLE} 20 W for 1 s is 20 J.\n",
        encoding="utf-8",
    )
    with pytest.raises(charter.CharterError, match="changed meaning"):
        charter.load(charter_path, definitions_path)


def test_a_section_nobody_reads_is_rejected() -> None:
    """Closed sections, like the config file's keys and the kernel's predicates."""
    with pytest.raises(charter.CharterError, match="Appendix"):
        charter.parse(written(extra={"Appendix": "Some further thoughts."}))
    with pytest.raises(charter.CharterError, match="twice"):
        charter.parse(written() + "\n## Question\n\nAgain.\n")


def test_prose_outside_a_section_is_rejected() -> None:
    """A charter is its commitments. A paragraph above them is a claim nobody committed."""
    with pytest.raises(charter.CharterError, match="prose above"):
        charter.parse(written(preamble="# Charter\n\nA note on how to read this.\n"))


def test_the_version_does_not_depend_on_the_order_of_the_sections() -> None:
    """Reordering a document is not a new question, so it must not be a new version.

    The version hashes a canonical rendering rather than the file, which is also what lets
    the signature sit outside it without the two disagreeing about what "the charter" is.
    """
    forwards = written(elements=ELEMENT_TEXT)
    backwards = written(elements=dict(reversed(list(ELEMENT_TEXT.items()))))

    assert backwards != forwards
    assert charter.parse(backwards).version == charter.parse(forwards).version
