"""The projection itself: a pure function from a kernel snapshot to a set of notes.

Nothing here touches a filesystem, a subprocess, or a clock. That is the whole design. The
vault must rebuild byte-for-byte identically from empty, and the cheapest way to be sure of
that is for the thing being rebuilt to be a value — `render` takes data and returns
`{path: text}`, so determinism is a property of a function that can be called twice in one
test rather than a property of a directory that has to be built twice to check.

It follows that there is no "generated at" line anywhere in a note. A timestamp of the
*rebuild* would make every rebuild differ from the last, which is exactly the drift the vault
exists to make impossible. The timestamps that do appear are the kernel's own `observed_at`,
which are facts about the assertion rather than about the run.

Notes are per **entity**, not per assertion: AGENTS.md §Phase 3 names folders after entity
kinds and asks that the graph view *be* the argument structure, and a graph of assertions
linked to assertions is not that. The per-assertion fields it lists — `assertion_id`,
`status`, `confidence`, `provenance` — are carried in frontmatter under `claims`, one entry
per assertion touching the entity, so they stay machine-readable without pretending an entity
has a single confidence.

Deletion criterion: this module holds the wager that the vault is derived and never
authoritative. Delete it and `vault_rebuilds_deterministically_from_an_empty_directory` and
`rebuild_is_idempotent_byte_for_byte` both lose their verdicts, and the prose in the vault
becomes a second place a claim can live — the drift between ledger and narrative that
AGENTS.md §Phase 3 exists to prevent.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from g0rd0n.kernel import Provenance, Ref

#: Where a note of each kind lives. Explicit rather than derived, because two of the folder
#: names AGENTS.md §Phase 3 asks for — `Sessions/` for `run`, `Playbooks/` for
#: `playbook_version` — do not fall out of any rule for pluralising a kind. Total over
#: `KINDS`, and `every_kind_has_a_folder` fails if a thirteenth kind arrives without one:
#: a homeless kind would be silently dropped from the projection, which is the one thing an
#: index over the kernel may never do.
FOLDERS: dict[str, str] = {
    "question": "Questions",
    "statement": "Statements",
    "hypothesis": "Hypotheses",
    "observation": "Observations",
    "experiment": "Experiments",
    "result": "Results",
    "source": "Sources",
    "claim": "Claims",
    "wager": "Wagers",
    "cost": "Costs",
    "run": "Sessions",
    "playbook_version": "Playbooks",
}

#: Written at the vault root. Its presence is what makes dropping the directory safe: a
#: rebuild refuses to delete a non-empty directory that does not carry it, so a `vault.root`
#: pointed at the wrong place costs an error message rather than someone's home directory.
MARKER_PATH = ".g0rd0n-vault"

README_PATH = "README.md"


@dataclass(frozen=True)
class Edge:
    """One assertion from the kernel, with its entity ids already resolved into names.

    Resolution happens in the projector, so that this module never needs the kernel and can
    be handed a snapshot built by hand in a test.
    """

    assertion_id: int
    subject: Ref
    predicate: str
    object: Ref
    status: str
    confidence: float
    observed_at: int
    supersedes_id: int
    retracts_id: int
    provenance: Provenance | None


@dataclass(frozen=True)
class Snapshot:
    """Everything the vault is projected from: the kernel, read once, as a value."""

    edges: tuple[Edge, ...]


def render(snapshot: Snapshot) -> dict[str, str]:
    """Project a snapshot into `{relative path: file content}`.

    Pure and total: the same snapshot renders the same bytes, and every entity mentioned by
    any edge — as a subject, an object, or a provenance source — gets exactly one note.
    """
    edges = tuple(sorted(snapshot.edges, key=lambda edge: edge.assertion_id))
    notes = {_path(ref): _note(ref, edges) for ref in _entities(edges)}
    return {MARKER_PATH: _marker(), README_PATH: _readme(notes), **notes}


def _entities(edges: tuple[Edge, ...]) -> list[Ref]:
    """Every entity the snapshot mentions, in a stable order."""
    seen: set[Ref] = set()
    for edge in edges:
        seen.update({edge.subject, edge.object})
        if edge.provenance is not None:
            seen.add(edge.provenance.source)
    return sorted(seen, key=lambda ref: (ref.kind, ref.name))


def _path(ref: Ref) -> str:
    return f"{FOLDERS[ref.kind]}/{ref.name}.md"


def _link(ref: Ref) -> str:
    """A wikilink by full path, aliased to `kind:name`.

    By path because two entities of different kinds may share a name, and a bare `[[h-001]]`
    would resolve to whichever Obsidian saw first. Aliased because the kind travelling with
    the name is the same convention the kernel's entity log uses (ADR 0003).
    """
    return f"[[{FOLDERS[ref.kind]}/{ref.name}|{ref}]]"


def _note(ref: Ref, edges: tuple[Edge, ...]) -> str:
    """One entity's note: frontmatter carrying the claims, body carrying the graph."""
    asserts = [edge for edge in edges if edge.subject == ref]
    asserted_of = [edge for edge in edges if edge.object == ref]
    cited_by = [
        edge for edge in edges if edge.provenance is not None and edge.provenance.source == ref
    ]
    touching = sorted(
        {edge.assertion_id: edge for edge in asserts + asserted_of + cited_by}.values(),
        key=lambda edge: edge.assertion_id,
    )

    lines = [_frontmatter(ref, touching, _superseded_by(asserted_of)), "", f"# {ref}", ""]
    lines += _section(
        "Asserts", [f"`{e.predicate}` {_link(e.object)} — {_detail(e)}" for e in asserts]
    )
    lines += _section(
        "Asserted of",
        [f"{_link(e.subject)} `{e.predicate}` this — {_detail(e)}" for e in asserted_of],
    )
    lines += _section(
        "Cited by",
        [f"{_link(e.subject)} `{e.predicate}` {_link(e.object)} — {_detail(e)}" for e in cited_by],
    )
    return "\n".join(lines)


def _superseded_by(asserted_of: list[Edge]) -> list[Ref]:
    """Successors of this entity, read off incoming `refines` edges.

    AGENTS.md §Phase 5: the Charter is criticised by committing a `refines` edge and is
    superseded, never overwritten. `refines` runs question → question, so an incoming one
    names the version that replaced this one — and because the old note is still projected,
    "why did we stop asking it that way" keeps an answer.

    A list, not a single value, because the record is append-only: nothing stops two
    successors from refining the same question, and silently showing one of them would be a
    lie of exactly the kind this vault exists to prevent.
    """
    return sorted(
        {edge.subject for edge in asserted_of if edge.predicate == "refines"},
        key=lambda ref: (ref.kind, ref.name),
    )


def _frontmatter(ref: Ref, touching: list[Edge], superseded_by: list[Ref]) -> str:
    lines = [
        "---",
        f"kind: {_quote(ref.kind)}",
        f"name: {_quote(ref.name)}",
        f"superseded_by: [{', '.join(_quote(str(s)) for s in superseded_by)}]",
        "claims:" if touching else "claims: []",
    ]
    for edge in touching:
        lines += [
            f"  - assertion_id: {edge.assertion_id}",
            f"    status: {_quote(edge.status)}",
            f"    confidence: {edge.confidence!r}",
            f"    provenance: {_quote(_provenance(edge))}",
        ]
    lines.append("---")
    return "\n".join(lines)


def _section(title: str, items: list[str]) -> list[str]:
    """A body section, or nothing at all when there is nothing to put in it."""
    if not items:
        return []
    return [f"## {title}", "", *(f"- {item}" for item in items), ""]


def _detail(edge: Edge) -> str:
    """The per-assertion facts, in the body, next to the edge they belong to."""
    parts = [
        f"assertion {edge.assertion_id}",
        edge.status,
        f"confidence {edge.confidence!r}",
        f"observed {_when(edge.observed_at)}",
        _cited(edge),
    ]
    if edge.supersedes_id:
        parts.append(f"supersedes assertion {edge.supersedes_id}")
    if edge.retracts_id:
        parts.append(f"retracts assertion {edge.retracts_id}")
    return ", ".join(parts)


def _cited(edge: Edge) -> str:
    """Provenance in the body, with the source as a link so the graph carries it too.

    Where a claim came from is part of the argument, not a footnote to it: a reader following
    the graph should be able to reach the paper without leaving Obsidian.
    """
    if edge.provenance is None:
        return "no provenance recorded"
    return f"from {_link(edge.provenance.source)} ({edge.provenance.method})"


def _provenance(edge: Edge) -> str:
    """Provenance in frontmatter: plain text, because a wikilink is not a queryable value."""
    if edge.provenance is None:
        return "none recorded"
    return f"{edge.provenance.source} ({edge.provenance.method})"


def _when(observed_at: int) -> str:
    """The kernel's Unix seconds as ISO-8601 UTC. A fact about the assertion, not the run."""
    return datetime.fromtimestamp(observed_at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _marker() -> str:
    return (
        "g0rd0n vault marker.\n"
        "\n"
        "This directory is a derived projection of the knk kernel and is dropped and\n"
        "regenerated in full by `g0rd0n vault rebuild`. Nothing here is read back as fact.\n"
        "Deleting this file does not protect your edits; it only makes rebuild refuse to run.\n"
    )


def _readme(notes: dict[str, str]) -> str:
    """A human's first page: what this is, and what is in it."""
    counts: dict[str, int] = {}
    for path in notes:
        counts[path.split("/")[0]] = counts.get(path.split("/")[0], 0) + 1
    inventory = [f"- `{folder}/` — {count}" for folder, count in sorted(counts.items())]
    return "\n".join(
        [
            "# g0rd0n vault",
            "",
            "A **derived projection** of the kernel, rebuilt in full by `g0rd0n vault rebuild`.",
            "The kernel is the source of truth; nothing here is ever read back as fact.",
            "",
            "Hand-edits are welcome and are treated as human input, but they do not survive a",
            "rebuild — the next one overwrites them, after telling you which files it would",
            "lose. Prose that should last gets committed to the kernel first.",
            "",
            "## Notes",
            "",
            *(inventory or ["- (nothing yet: the kernel has no assertions)"]),
            "",
        ]
    )


def _quote(text: str) -> str:
    """A YAML double-quoted scalar.

    Hand-rolled because the alternative is a dependency for one function, and because the
    escaping rules for a double-quoted scalar are short enough to get right here: backslash
    and quote, then anything that is not printable.
    """
    out = ['"']
    for char in text:
        if char in {"\\", '"'}:
            out.append("\\" + char)
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)
