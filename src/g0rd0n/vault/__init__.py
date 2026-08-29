"""The Vault: Obsidian as a one-way, rebuildable projection of the kernel.

Two modules, split along the line that matters: `note` is the projection as a pure function
from a snapshot to `{path: text}`, and `projector` is everything that touches a kernel or a
disk. The split is what makes "rebuilds byte-for-byte identically" a property you can test by
calling a function twice.

The arrow only ever points kernel → vault. Nothing in this package turns a note back into a
claim. A vault that could be read back would be a second store of beliefs without the
kernel's provenance, status, or history — which is the failure AGENTS.md §1 names first.

Deletion criterion: this package holds the wager that the human-readable record and the
machine-readable one cannot drift, because one is generated from the other. Delete it and
`vault_rebuilds_deterministically_from_an_empty_directory` loses its verdict, and the
argument a person reads stops being evidence about what g0rd0n actually believes.
"""

from g0rd0n.vault.note import FOLDERS, MARKER_PATH, Edge, Snapshot, render
from g0rd0n.vault.projector import Edits, Rebuild, VaultError, differences, rebuild, snapshot

__all__ = [
    "FOLDERS",
    "MARKER_PATH",
    "Edge",
    "Edits",
    "Rebuild",
    "Snapshot",
    "VaultError",
    "differences",
    "rebuild",
    "render",
    "snapshot",
]
