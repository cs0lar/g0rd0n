"""Reading the kernel, and putting the projection on disk. The only impure half of the vault.

Three things happen here and nowhere else: the kernel is read into a `Snapshot`, an existing
vault is compared against what it *should* contain, and the directory is dropped and written
again. The projection itself is `note.render`, which is pure — so everything below is I/O,
and every question about what the vault contains is answered without touching a disk.

The direction is one-way, permanently. Nothing in this module reads a note back and turns it
into a claim: `differences` reads the vault only to warn about what a rebuild is about to
destroy, and the answer is thrown away. AGENTS.md §1 — the vault is derived, and a projection
that can be read back as fact is a second source of truth with none of the kernel's guarantees.

Dropping a directory named by a config file is the one genuinely dangerous act in g0rd0n so
far, so it is gated: a non-empty directory that does not carry `note.MARKER_PATH` is refused,
not emptied. A `vault.root` typo then costs an error message.

Deletion criterion: this module holds the wager that a human can read the argument in
Obsidian and be reading the kernel. Delete it and `refuted_hypothesis_note_shows_its_
refutation_and_is_never_deleted` loses its verdict, `g0rd0n vault rebuild` has nothing to
call, and the projection becomes a thing someone maintains by hand — at which point it is
prose, not an index.
"""

import shutil
from pathlib import Path
from typing import NamedTuple

from g0rd0n.kernel import Bridge, Ref
from g0rd0n.vault.note import MARKER_PATH, Edge, Snapshot, render


class VaultError(Exception):
    """The vault could not be rebuilt, and nothing was changed."""


class Edits(NamedTuple):
    """Hand-edits a rebuild is about to overwrite. Empty when the vault matches the kernel."""

    modified: tuple[str, ...]
    extra: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.modified or self.extra)

    def describe(self) -> list[str]:
        return [f"modified: {path}" for path in self.modified] + [
            f"not from the kernel: {path}" for path in self.extra
        ]


class Rebuild(NamedTuple):
    """What a rebuild did, or would have done."""

    notes: int
    edits: Edits
    dry_run: bool


def snapshot(bridge: Bridge) -> Snapshot:
    """Read the whole kernel, once, resolving ids to names as it goes.

    `changes_since(0)` is the enumeration path: every assertion the kernel has ever recorded,
    in commit order, whatever its status. Superseded and refuted claims come back too, which
    is the point — the vault has to show how the programme changed its mind, not its current
    conclusions.
    """
    names: dict[int, Ref] = {}
    predicates: dict[int, str] = {}

    def name(entity_id: int) -> Ref:
        if entity_id not in names:
            names[entity_id] = bridge.name_of(entity_id)
        return names[entity_id]

    def predicate(predicate_id: int) -> str:
        if predicate_id not in predicates:
            predicates[predicate_id] = bridge.predicate_of(predicate_id)
        return predicates[predicate_id]

    return Snapshot(
        edges=tuple(
            Edge(
                assertion_id=assertion.id,
                subject=name(assertion.subject),
                predicate=predicate(assertion.predicate),
                object=name(assertion.object),
                status=assertion.status,
                confidence=assertion.confidence,
                observed_at=assertion.observed_at,
                supersedes_id=assertion.supersedes_id,
                retracts_id=assertion.retracts_id,
                provenance=bridge.provenance_for(assertion.id),
            )
            for assertion in bridge.changes_since(0)
        )
    )


def differences(vault_root: Path, notes: dict[str, str]) -> Edits:
    """What is on disk that the kernel did not put there.

    Because the projection is deterministic, it *is* the checksum: no manifest, no stored
    hashes, no state that could itself go stale. Anything that differs from what `render`
    produces right now is a hand-edit, by definition.
    """
    if not vault_root.is_dir():
        return Edits((), ())
    on_disk = {
        path.relative_to(vault_root).as_posix() for path in vault_root.rglob("*") if path.is_file()
    }
    modified = sorted(
        path for path in on_disk & set(notes) if _read(vault_root / path) != notes[path]
    )
    return Edits(tuple(modified), tuple(sorted(on_disk - set(notes))))


def rebuild(bridge: Bridge, vault_root: Path, *, dry_run: bool = False) -> Rebuild:
    """Drop the vault and project it again from the kernel.

    Reports hand-edits before destroying them, which is the whole of the warning AGENTS.md
    §Phase 3 asks for: a rebuild is allowed to overwrite human prose, but never quietly.
    """
    notes = render(snapshot(bridge))
    edits = differences(vault_root, notes)
    if dry_run:
        return Rebuild(len(notes), edits, dry_run=True)

    _check_droppable(vault_root)
    if vault_root.exists():
        shutil.rmtree(vault_root)
    for path, content in sorted(notes.items()):
        target = vault_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return Rebuild(len(notes), edits, dry_run=False)


def _check_droppable(vault_root: Path) -> None:
    """Refuse to delete a directory that was not built by a previous rebuild.

    An empty or absent directory is fine — that is a first run. A directory with things in it
    and no marker is somebody's data, and `vault.root` is a config value that can be wrong.
    """
    if not vault_root.exists():
        return
    if not vault_root.is_dir():
        raise VaultError(f"{vault_root} is not a directory")
    if not any(vault_root.iterdir()):
        return
    if not (vault_root / MARKER_PATH).is_file():
        raise VaultError(
            f"{vault_root} is not empty and has no {MARKER_PATH}, so it was not built by "
            "g0rd0n; refusing to drop it. Point vault.root somewhere else, or empty it "
            "yourself if this really is the vault."
        )


def _read(path: Path) -> str | None:
    """The file as text, or `None` if it is not readable as text — which counts as edited."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
