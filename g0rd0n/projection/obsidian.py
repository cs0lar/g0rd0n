"""Deterministic Obsidian projection with explicit ownership boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from g0rd0n.core.research import ResearchObject, ResearchObjectKind
from g0rd0n.research.ledger import ResearchState, Relation

GENERATOR = "g0rd0n.obsidian.v1"
MANUAL_START = "<!-- g0rd0n:manual:start -->"
MANUAL_END = "<!-- g0rd0n:manual:end -->"

_FOLDERS: Mapping[ResearchObjectKind, str] = {
    ResearchObjectKind.QUESTION: "01-questions",
    ResearchObjectKind.DEFINITION: "02-definitions",
    ResearchObjectKind.ASSUMPTION: "02-definitions",
    ResearchObjectKind.HYPOTHESIS: "03-hypotheses",
    ResearchObjectKind.PREDICTION: "03-hypotheses",
    ResearchObjectKind.EXPERIMENT: "04-experiments",
    ResearchObjectKind.OBSERVATION: "04-experiments",
    ResearchObjectKind.RESULT: "05-results",
    ResearchObjectKind.CLAIM: "06-theories",
    ResearchObjectKind.PROOF_ATTEMPT: "07-proofs",
    ResearchObjectKind.PROOF: "07-proofs",
    ResearchObjectKind.COUNTEREXAMPLE: "08-failures",
    ResearchObjectKind.FAILURE: "08-failures",
    ResearchObjectKind.DECISION: "09-decisions",
    ResearchObjectKind.RESEARCH_PROGRAM: "30-candidates",
}


class ProjectionError(ValueError):
    """Raised when a vault cannot be projected without losing ownership data."""


@dataclass(frozen=True, slots=True)
class HumanEdit:
    object_id: str
    note_path: Path
    markdown: str


def _validate_id(object_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", object_id):
        raise ProjectionError(f"unsafe research object id: {object_id!r}")


def _manual_content(markdown: str) -> str:
    starts = markdown.count(MANUAL_START)
    ends = markdown.count(MANUAL_END)
    if starts != 1 or ends != 1:
        raise ProjectionError("generated note must contain exactly one manual ownership region")
    start_index = markdown.index(MANUAL_START)
    end_index = markdown.index(MANUAL_END)
    if end_index < start_index:
        raise ProjectionError("manual ownership markers are out of order")
    remainder = markdown[start_index + len(MANUAL_START) :]
    content = remainder[: remainder.index(MANUAL_END)]
    return content.strip("\n")


class ObsidianProjector:
    def __init__(
        self,
        vault: Path,
        *,
        artifact_loader: Callable[[str], bytes] | None = None,
    ) -> None:
        self.vault = vault
        self.artifact_loader = artifact_loader

    def note_path(self, obj: ResearchObject) -> Path:
        _validate_id(obj.id)
        return self.vault / _FOLDERS[obj.kind] / f"{obj.id}.md"

    def wikilink(self, obj: ResearchObject) -> str:
        _validate_id(obj.id)
        target = f"{_FOLDERS[obj.kind]}/{obj.id}"
        label = obj.title.replace("|", "—").replace("]", "")
        return f"[[{target}|{label}]]"

    def project(self, state: ResearchState) -> tuple[Path, ...]:
        self.vault.mkdir(parents=True, exist_ok=True)
        self._validate_state(state)
        manual_by_id: dict[str, str] = {}
        for object_id in sorted(state.objects):
            path = self.note_path(state.objects[object_id])
            manual_by_id[object_id] = (
                _manual_content(path.read_text(encoding="utf-8")) if path.exists() else ""
            )
        artifacts = self._load_artifacts(state)
        written: list[Path] = []
        for object_id in sorted(state.objects):
            obj = state.objects[object_id]
            path = self.note_path(obj)
            markdown = self._render(obj, state, manual_by_id[object_id])
            self._atomic_write(path, markdown.encode("utf-8"))
            written.append(path)
        for digest, content in artifacts.items():
            path = self.vault / "99-generated" / "artifacts" / digest
            self._atomic_write(path, content)
            written.append(path)
        return tuple(written)

    def collect_manual_edits(self, state: ResearchState) -> tuple[HumanEdit, ...]:
        edits: list[HumanEdit] = []
        for object_id in sorted(state.objects):
            path = self.note_path(state.objects[object_id])
            if not path.exists():
                continue
            content = _manual_content(path.read_text(encoding="utf-8"))
            if content.strip():
                edits.append(HumanEdit(object_id, path, content))
        return tuple(edits)

    def _validate_state(self, state: ResearchState) -> None:
        for object_id, obj in state.objects.items():
            _validate_id(object_id)
            if obj.id != object_id:
                raise ProjectionError("state object key does not match stable object id")
        for relation in state.relations:
            if relation.subject_id not in state.objects or relation.object_id not in state.objects:
                raise ProjectionError("relation references an unknown object")
        if set(state.statuses) != set(state.objects):
            raise ProjectionError("every projected object must have exactly one status")
        if any(object_id not in state.objects for object_id in state.artifacts):
            raise ProjectionError("artifact references an unknown object")

    def _render(self, obj: ResearchObject, state: ResearchState, manual: str) -> str:
        relations = sorted(
            (
                relation
                for relation in state.relations
                if relation.subject_id == obj.id or relation.object_id == obj.id
            ),
            key=lambda item: (item.subject_id, item.predicate, item.object_id),
        )
        lines = [
            "---",
            f"g0rd0n_id: {json.dumps(obj.id, ensure_ascii=False)}",
            f"kind: {json.dumps(obj.kind.value)}",
            "generated: true",
            f"generator: {json.dumps(GENERATOR)}",
            "---",
            "",
            f"# {obj.title}",
            "",
            "> [!warning] Generated projection",
            "> Edit only the Human notes region; generated content is replaced on regeneration.",
            "",
            "## Scientific content",
            "",
            "```json",
            json.dumps(obj.content, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
            "```",
            "",
            "## Status",
            "",
            f"- `{state.statuses[obj.id].value}`",
            "",
            "## Relationships",
            "",
        ]
        if relations:
            lines.extend(self._relation_line(obj.id, relation, state) for relation in relations)
        else:
            lines.append("- None recorded")
        lines.extend(["", "## Evidence artifacts", ""])
        digests = sorted(state.artifacts.get(obj.id, ()))
        if digests:
            lines.extend(
                f"- [[99-generated/artifacts/{digest}|sha256:{digest}]]" for digest in digests
            )
        else:
            lines.append("- None recorded")
        provenance = obj.provenance
        lines.extend(
            [
                "",
                "## Provenance",
                "",
                f"- Actor: {json.dumps(provenance.actor, ensure_ascii=False)}",
                f"- Created: `{provenance.created_at.isoformat(timespec='microseconds')}`",
                f"- Source: {json.dumps(provenance.source, ensure_ascii=False)}",
                "",
                "## Human notes",
                "",
                MANUAL_START,
            ]
        )
        if manual:
            lines.extend(manual.splitlines())
        lines.extend([MANUAL_END, ""])
        return "\n".join(lines)

    def _relation_line(self, current_id: str, relation: Relation, state: ResearchState) -> str:
        if relation.subject_id == current_id:
            target = state.objects[relation.object_id]
            return f"- `{relation.predicate}` → {self.wikilink(target)}"
        source = state.objects[relation.subject_id]
        return f"- {self.wikilink(source)} → `{relation.predicate}` → this"

    def _load_artifacts(self, state: ResearchState) -> dict[str, bytes]:
        digests = sorted({digest for values in state.artifacts.values() for digest in values})
        if digests and self.artifact_loader is None:
            raise ProjectionError("artifact_loader is required when research state references evidence")
        artifacts: dict[str, bytes] = {}
        for digest in digests:
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ProjectionError(f"invalid artifact digest: {digest}")
            assert self.artifact_loader is not None
            content = self.artifact_loader(digest)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ProjectionError(f"artifact content does not match digest: {digest}")
            artifacts[digest] = content
        return artifacts

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
