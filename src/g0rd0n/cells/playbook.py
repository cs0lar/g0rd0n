"""Playbooks: the prompts a cell plays, versioned by their own content.

A playbook is a file in `playbooks/`, not runtime state and not a string built at the call
site. AGENTS.md §Phase 12 makes them versioned artifacts in the repo so that a change to how
g0rd0n thinks arrives as a diff someone reviews.

**A playbook's version is the hash of its bytes** (`content.version_of`). Not a number in a
field someone remembers to bump: an edited prompt with a stale version number would attribute
a run to text that never produced it, and there is no test that could catch it — the record
would be internally consistent and wrong. Hashing removes the possibility rather than warning
about it. The hash covers the raw bytes, so a whitespace-only edit is still a new version:
whitespace changes prompts.

Deletion criterion: this module holds the wager that any result can be traced to the exact
prompt that produced it. Delete it and `transcript_is_interned_and_linked_to_its_playbook_
version` loses its verdict, prompts go back to being string literals at call sites, and
"which version of the critic said that?" stops having an answer.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from g0rd0n.content import version_of
from g0rd0n.kernel import Ref

KNOWN_KEYS = frozenset({"role", "system", "model", "max_turns"})


class PlaybookError(Exception):
    """A playbook is missing, malformed, or says something a cell cannot play."""


@dataclass(frozen=True)
class Playbook:
    """One versioned prompt, and the role it is written for.

    `version` is derived, never declared. `ref` is what gets committed to the kernel, so the
    `plays` edge points at bytes rather than at a name someone could reuse.
    """

    name: str
    role: str
    system: str
    model: str
    max_turns: int
    version: str

    @property
    def ref(self) -> Ref:
        """The kernel entity for this exact text: `playbook_version:critic-9f2a1c…`."""
        return Ref("playbook_version", f"{self.name}-{self.version}")


def load(path: Path) -> Playbook:
    """Read one playbook file, and hash it.

    The hash covers the raw bytes, so a whitespace-only edit is still a new version. That is
    deliberate: whitespace changes prompts.
    """
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise PlaybookError(f"cannot read playbook {path}: {exc}") from exc
    try:
        raw = tomllib.loads(content.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PlaybookError(f"{path} is not a valid playbook: {exc}") from exc

    unknown = set(raw) - KNOWN_KEYS
    if unknown:
        raise PlaybookError(f"{path}: unknown setting {', '.join(sorted(unknown))}")

    playbook = Playbook(
        name=path.stem,
        role=_text(raw, path, "role"),
        system=_text(raw, path, "system"),
        model=_text(raw, path, "model"),
        max_turns=_turns(raw, path),
        version=version_of(content),
    )
    if not playbook.system.strip():
        raise PlaybookError(f"{path}: system prompt is empty")
    return playbook


def _text(raw: dict[str, object], path: Path, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise PlaybookError(f"{path}: {key} must be a string")
    return value


def _turns(raw: dict[str, object], path: Path) -> int:
    value = raw.get("max_turns", 8)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlaybookError(f"{path}: max_turns must be a positive integer")
    return value
