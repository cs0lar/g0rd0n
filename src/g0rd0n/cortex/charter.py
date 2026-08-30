"""The Charter: the well-posed version of the task, and the only thing that may replace it.

AGENTS.md §Phase 5. The seed framing in AGENTS.md §The Question is not a question anything can
be spent against — it names three separation shapes and picks none, and its central term
("more powerful") is one that two Turing-complete systems cannot be separated on. The Charter
is the version that can be spent against, and this module is the machine that decides whether
a document is one.

Four rules, and the whole module is those four rules:

- **The Charter must fix what AGENTS.md says it must fix.** Eight named sections, closed: a
  missing one is a rejection naming it, and a section nobody declared is a rejection too. A
  charter that leaves the resource unfixed cannot pre-register an experiment, so it is not a
  charter.
- **A charter is superseded, never overwritten.** Its identity is the hash of its own
  substance, exactly as a playbook's is (`version_of`), so a charter cannot be edited — an
  edit produces a different charter. Replacing one commits `refines` edges from the new
  question to the old, which is why the old stays readable.
- **No supersession without a criticism.** One `refines` edge per criticism, each carrying its
  text in provenance. "Why did we stop asking it that way" is answerable because there is no
  way to stop asking it that way without writing the answer down first.
- **A human signs, and the signature names what was signed.** The signature is the one section
  outside the version hash — you cannot sign a document whose identity changes when you sign
  it — so it carries the version it signed instead. A charter whose signature names a
  different version is refused: the text changed after somebody put their name to it.

`docs/charter/definitions.md` is handled here too, because it is half of one document: the
Charter names its definitions file by hash, so redefining a term changes the Charter's version
and costs a fresh signature. A definition with no worked example is not a definition and is
rejected on the way in.

Deletion criterion: this module holds the wager that g0rd0n is working on a question somebody
made well-posed and signed. Delete it and `charter_revision_supersedes_and_never_overwrites`,
`charter_without_a_named_fixed_resource_is_rejected`, and `every_definition_has_a_worked_
example` all lose their verdicts at once, the Charter becomes a file that can be edited in
place, and the chain AGENTS.md §4 requires — no spend without a Wager, no Wager without a
Question — loses the only link that a human ever signs.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from g0rd0n.cells.playbook import version_of
from g0rd0n.kernel import AssertionId, Bridge, Claim, Provenance, Ref, VocabularyError

#: What the Charter must fix, per AGENTS.md §Phase 5, and the statement each one becomes in
#: the kernel. Explicit rather than slugified on the fly so that renaming a heading is a
#: change to this table, which renames an entity, which is a thing a reviewer sees.
#:
#: AGENTS.md lists six items, one of which is compound ("the energy metric and instrument").
#: It is checked as two, because a metric with no named instrument is exactly the failure the
#: Charter exists to prevent: joules per solved instance is a number until something measures
#: it, and then it is a result.
ELEMENTS: dict[str, str] = {
    "Question": "question",
    "Separation shape": "separation-shape",
    "Resource held fixed": "resource-held-fixed",
    "Task families": "task-families",
    "Capability metric": "capability-metric",
    "Energy metric": "energy-metric",
    "Energy instrument": "energy-instrument",
    "Matched-capability protocol": "matched-capability-protocol",
}

#: Names the definitions file by version. Required, and inside the version hash: a Charter
#: whose terms can be redefined underneath it is a Charter that can be changed without being
#: superseded, which is the one thing this module exists to prevent.
DEFINITIONS = "Definitions"

#: The question this charter replaces, as an entity name, and why. Optional — the first
#: charter replaces nothing — but the two travel together in both directions.
SUPERSEDES = "Supersedes"
CRITICISMS = "Criticisms"

#: The one section outside the version hash. See the module docstring.
SIGNATURE = "Signed-off-by"

#: Every heading the Charter may carry, in the order the version hash canonicalises them to.
#: Closed, like the config file's keys and the kernel's predicates: a section nobody declared
#: is prose that looks like a commitment.
SECTIONS: tuple[str, ...] = (*ELEMENTS, DEFINITIONS, SUPERSEDES, CRITICISMS, SIGNATURE)

#: What a definition must contain to be one. AGENTS.md §Phase 5: "A definition that cannot be
#: applied to a worked example is not yet a definition."
WORKED_EXAMPLE = "**Worked example:**"

_VERSION = re.compile(r"\A[0-9a-f]{12}\Z")


class CharterError(Exception):
    """A charter, or its definitions, says something a charter may not say."""


@dataclass(frozen=True)
class Charter:
    """One version of the well-posed question, as a value.

    `elements` is keyed by `ELEMENTS`' headings rather than spread into eight named fields,
    so that the list of what a Charter must fix lives in exactly one place and validation
    reads from the same table the kernel commit does.
    """

    elements: Mapping[str, str]
    definitions: str
    supersedes: str | None
    criticisms: tuple[str, ...]
    signatory: str | None
    version: str
    text: str

    @property
    def name(self) -> str:
        """The entity name of this charter: `charter-9f2a1c3d4e5f`."""
        return f"charter-{self.version}"

    @property
    def ref(self) -> Ref:
        """The kernel entity for this exact question: `question:charter-9f2a1c3d4e5f`."""
        return Ref("question", self.name)

    @property
    def signed(self) -> bool:
        return self.signatory is not None


@dataclass(frozen=True)
class Definition:
    """One term the Charter uses, what it means, and one case of it applied."""

    term: str
    body: str
    example: str


def parse(text: str) -> Charter:
    """Read a charter, or raise `CharterError` naming the first thing wrong with it.

    Never returns a partial Charter: either the document fixes everything AGENTS.md §Phase 5
    says it must, or nothing downstream sees it at all.
    """
    sections = _sections(text, preamble=False, what="charter")

    unknown = sorted(set(sections) - set(SECTIONS))
    if unknown:
        raise CharterError(f"charter has sections nothing reads: {', '.join(unknown)}")
    for heading in (*ELEMENTS, DEFINITIONS):
        if heading not in sections:
            raise CharterError(f"charter does not fix {heading!r}; it must have a '## {heading}'")
        if not sections[heading]:
            raise CharterError(f"charter's '## {heading}' section is empty, so it fixes nothing")

    definitions = sections[DEFINITIONS].strip()
    if not _VERSION.match(definitions):
        raise CharterError(
            f"charter's '## {DEFINITIONS}' must name the definitions file's version — twelve "
            f"hex characters, as `g0rd0n charter show` prints it — not {definitions!r}"
        )

    supersedes = _supersedes(sections)
    criticisms = _criticisms(sections)
    if supersedes and not criticisms:
        raise CharterError(
            f"charter supersedes {supersedes!r} without saying what was wrong with it; "
            f"a '## {CRITICISMS}' list is what makes the supersession readable later"
        )
    if criticisms and not supersedes:
        raise CharterError(
            f"charter criticises something without a '## {SUPERSEDES}' saying what, so the "
            "criticisms have nothing to point at"
        )

    # No self-supersession check: `Supersedes` is inside the substance, so a charter naming
    # itself would need a fixed point of the hash. The structure rules it out; a check here
    # would be an unreachable branch pretending to be a safeguard.
    version = version_of(_substance(sections).encode("utf-8"))
    return Charter(
        elements={heading: sections[heading] for heading in ELEMENTS},
        definitions=definitions,
        supersedes=supersedes,
        criticisms=criticisms,
        signatory=_signatory(sections, version),
        version=version,
        text=text,
    )


def definitions(text: str) -> tuple[Definition, ...]:
    """Read a definitions file, or raise `CharterError`.

    A term with no worked example is rejected here rather than reported later: the whole claim
    of the file is that its terms can be applied, and one that cannot be applied is a word the
    Charter uses without meaning it.
    """
    sections = _sections(text, preamble=True, what="definitions")
    if not sections:
        raise CharterError("definitions file defines nothing; a '## Term' section defines one")

    defined: list[Definition] = []
    for term, body in sections.items():
        head, marker, example = body.partition(WORKED_EXAMPLE)
        if not marker:
            raise CharterError(
                f"definition of {term!r} has no worked example; every definition needs a "
                f"'{WORKED_EXAMPLE}' and a case of it applied"
            )
        if not head.strip():
            raise CharterError(f"definition of {term!r} is a worked example with nothing defined")
        if not example.strip():
            raise CharterError(f"definition of {term!r} has an empty worked example")
        defined.append(Definition(term=term, body=head.strip(), example=example.strip()))
    return tuple(defined)


def load(charter_path: Path, definitions_path: Path) -> Charter:
    """Read both halves of the Charter and check they are the same document.

    One loader rather than two, because a charter without the definitions it names is a set of
    terms nobody has fixed the meaning of, and there should be no way to get one by accident.
    """
    charter = parse(_read(charter_path, "charter"))
    text = _read(definitions_path, "definitions")
    definitions(text)
    version = version_of(text.encode("utf-8"))
    if version != charter.definitions:
        raise CharterError(
            f"{charter.name} names definitions {charter.definitions}, but {definitions_path} "
            f"is {version}; a term changed meaning, so the charter is superseded, not amended"
        )
    return charter


def commit(bridge: Bridge, charter: Charter) -> tuple[AssertionId, ...]:
    """Put a signed charter into the kernel: what it fixes, and what it replaces.

    Eight `asks` edges, one per thing AGENTS.md requires the Charter to fix, and one `refines`
    edge per criticism of the question being replaced. The charter's own text is interned once
    and cited from every edge's provenance — knk leaves document entities unnamed, so a
    document is cited, never asserted about (ADR 0003).

    Refuses an unsigned charter. That is the Phase 5 gate: an unsigned charter can be read,
    printed, and reviewed, but it never becomes something a Wager can descend from.
    """
    if charter.signatory is None:
        raise CharterError(
            f"{charter.name} is unsigned; a human reviewer signs the Charter before it enters "
            f"the kernel (add a '## {SIGNATURE}' naming you, a date, and {charter.name})"
        )
    if bridge.assertions_for(charter.ref) or bridge.hypotheses(charter.ref):
        raise CharterError(
            f"{charter.name} is already in the kernel; supersede it, do not recommit it"
        )

    document = bridge.intern_document(charter.text.encode("utf-8"))
    source = Ref("source", charter.name)
    committed = [
        bridge.hypothesise(
            Claim(charter.ref, "asks", Ref("statement", f"{charter.name}-{slug}"), 1.0),
            Provenance(source, f"CHARTER.md §{heading}, knk document {document}"),
        )
        for heading, slug in ELEMENTS.items()
    ]
    if charter.supersedes is not None:
        previous = Ref("question", charter.supersedes)
        committed += [
            bridge.hypothesise(
                Claim(charter.ref, "refines", previous, 1.0),
                Provenance(
                    source,
                    f"CHARTER.md §{CRITICISMS} of {charter.supersedes}, knk document "
                    f"{document}: {criticism}",
                ),
            )
            for criticism in charter.criticisms
        ]
    return tuple(committed)


def _sections(text: str, *, preamble: bool, what: str) -> dict[str, str]:
    """Split a document on its `## ` headings.

    The charter allows no preamble: anything above the first heading would be a commitment
    nobody committed, in a document whose whole job is to be the list of commitments. The
    definitions file allows one, because it asserts nothing about the world and its preamble
    is a note to the reader.
    """
    heading: str | None = None
    bodies: dict[str, list[str]] = {}
    above: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading in bodies:
                raise CharterError(f"{what} says '## {heading}' twice")
            bodies[heading] = []
        elif heading is None:
            above.append(line)
        else:
            bodies[heading].append(line)

    stray = [line for line in above if line.strip() and not line.startswith("# ")]
    if stray and not preamble:
        raise CharterError(
            f"{what} has prose above its first section: {stray[0].strip()!r}. Everything a "
            "charter says belongs under one of its headings, or it is a claim nobody made."
        )
    return {name: "\n".join(body).strip() for name, body in bodies.items()}


def _substance(sections: Mapping[str, str]) -> str:
    """What the version hashes: every section except the signature, in canonical order.

    Canonical, so that reordering the document does not produce a different charter, and so
    that the one section left out is left out by name rather than by where it happened to sit.
    """
    return "\n\n".join(
        f"## {heading}\n\n{sections[heading].strip()}"
        for heading in SECTIONS
        if heading != SIGNATURE and heading in sections
    )


def _supersedes(sections: Mapping[str, str]) -> str | None:
    name = sections.get(SUPERSEDES, "").strip()
    if not name:
        return None
    try:
        Ref("question", name)
    except VocabularyError as exc:
        raise CharterError(f"'## {SUPERSEDES}' does not name a question: {exc}") from exc
    return name


def _criticisms(sections: Mapping[str, str]) -> tuple[str, ...]:
    """The `- ` items of the criticisms section, one per `refines` edge.

    Continuation lines are folded in, so a criticism may wrap. Anything before the first item
    is refused rather than dropped: an unbulleted paragraph in this section is a criticism
    that would never reach the kernel.
    """
    body = sections.get(CRITICISMS, "").strip()
    if not body:
        return ()

    items: list[list[str]] = []
    for line in body.splitlines():
        if line.startswith("- "):
            items.append([line[2:].strip()])
        elif line.strip():
            if not items:
                raise CharterError(
                    f"'## {CRITICISMS}' starts with prose rather than a '- ' item: "
                    f"{line.strip()!r}. Only list items become `refines` edges."
                )
            items[-1].append(line.strip())
    criticisms = tuple(" ".join(" ".join(item).split()) for item in items)
    if any(not criticism for criticism in criticisms):
        raise CharterError(f"'## {CRITICISMS}' has an empty item")
    return criticisms


def _signatory(sections: Mapping[str, str], version: str) -> str | None:
    """Who signed, having checked that they signed *this*.

    The signature sits outside the version hash — a document cannot contain the hash of
    itself-including-the-signature — so it names the version instead. A signature naming a
    different one is refused rather than ignored: the text changed after somebody put their
    name to it, and silently treating the charter as unsigned would lose the fact that
    someone had signed something.
    """
    line = sections.get(SIGNATURE, "").strip()
    if not line:
        return None
    if "\n" in line:
        raise CharterError(f"'## {SIGNATURE}' must be one line: a name, a date, and a version")
    token = f"charter-{version}"
    if token not in line:
        raise CharterError(
            f"signature {line!r} does not name {token}; either it signs a charter this is not, "
            "or the text was changed after it was signed"
        )
    signatory = " ".join(line.replace(token, "").split()).strip(" ,")
    if not signatory:
        raise CharterError(f"'## {SIGNATURE}' names {token} but nobody signed it")
    return signatory


def _read(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CharterError(f"cannot read {what} {path}: {exc}") from exc
