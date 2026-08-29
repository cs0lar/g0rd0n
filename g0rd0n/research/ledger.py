"""Append-only, deterministic research ledger with content-addressed artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping

from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind

GENESIS_HASH = "0" * 64


class IntegrityError(ValueError):
    """Raised when ledger history is malformed or has been altered."""


class EventKind(StrEnum):
    OBJECT_RECORDED = "object_recorded"
    STATUS_TRANSITIONED = "status_transitioned"
    RELATION_RECORDED = "relation_recorded"
    ARTIFACT_ATTACHED = "artifact_attached"


class ObjectStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    COMPLETED = "completed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


ALLOWED_TRANSITIONS: Mapping[ObjectStatus, frozenset[ObjectStatus]] = {
    ObjectStatus.PROPOSED: frozenset(
        {ObjectStatus.ACTIVE, ObjectStatus.REJECTED, ObjectStatus.SUPERSEDED}
    ),
    ObjectStatus.ACTIVE: frozenset(
        {ObjectStatus.COMPLETED, ObjectStatus.REJECTED, ObjectStatus.SUPERSEDED}
    ),
    ObjectStatus.COMPLETED: frozenset({ObjectStatus.SUPERSEDED}),
    ObjectStatus.REJECTED: frozenset({ObjectStatus.SUPERSEDED}),
    ObjectStatus.SUPERSEDED: frozenset(),
}


def _normalize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.isoformat(timespec="microseconds")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical mappings require string keys")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not canonical JSON")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Serialize a value deterministically for hashing and persistence."""
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written == 0:
            raise OSError("file write made no progress")
        view = view[written:]


def _provenance_dict(provenance: Provenance) -> dict[str, Any]:
    return {
        "actor": provenance.actor,
        "created_at": provenance.created_at,
        "source": provenance.source,
    }


def _object_dict(obj: ResearchObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "kind": obj.kind,
        "title": obj.title,
        "content": obj.content,
        "provenance": _provenance_dict(obj.provenance),
    }


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    sequence: int
    kind: EventKind
    occurred_at: datetime
    actor: str
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        kind: EventKind,
        occurred_at: datetime,
        actor: str,
        payload: Mapping[str, Any],
        previous_hash: str,
    ) -> "LedgerEvent":
        unsigned = {
            "sequence": sequence,
            "kind": kind,
            "occurred_at": occurred_at,
            "actor": actor,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        return cls(event_hash=content_hash(unsigned), **unsigned)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "occurred_at": self.occurred_at,
            "actor": self.actor,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LedgerEvent":
        try:
            occurred_at = datetime.fromisoformat(str(data["occurred_at"]))
            event = cls(
                sequence=int(data["sequence"]),
                kind=EventKind(data["kind"]),
                occurred_at=occurred_at,
                actor=str(data["actor"]),
                payload=dict(data["payload"]),
                previous_hash=str(data["previous_hash"]),
                event_hash=str(data["event_hash"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("invalid ledger event") from error
        return event

    def expected_hash(self) -> str:
        return content_hash(
            {
                "sequence": self.sequence,
                "kind": self.kind,
                "occurred_at": self.occurred_at,
                "actor": self.actor,
                "payload": self.payload,
                "previous_hash": self.previous_hash,
            }
        )


@dataclass(frozen=True, slots=True)
class Relation:
    subject_id: str
    predicate: str
    object_id: str


@dataclass(slots=True)
class ResearchState:
    objects: dict[str, ResearchObject] = field(default_factory=dict)
    statuses: dict[str, ObjectStatus] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    artifacts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    event_count: int = 0
    head_hash: str = GENESIS_HASH

    def trace_sources(self, object_id: str) -> tuple[ResearchObject, ...]:
        """Return all transitively linked upstream objects in stable traversal order."""
        if object_id not in self.objects:
            raise KeyError(object_id)
        upstream: dict[str, list[str]] = {}
        for relation in self.relations:
            upstream.setdefault(relation.subject_id, []).append(relation.object_id)
        visited: set[str] = set()
        ordered: list[ResearchObject] = []

        def visit(current_id: str) -> None:
            for source_id in upstream.get(current_id, []):
                if source_id in visited:
                    continue
                visited.add(source_id)
                ordered.append(self.objects[source_id])
                visit(source_id)

        visit(object_id)
        return tuple(ordered)


def replay(events: Iterable[LedgerEvent]) -> ResearchState:
    state = ResearchState()
    for expected_sequence, event in enumerate(events):
        if event.sequence != expected_sequence:
            raise IntegrityError("ledger sequence is not contiguous")
        if event.previous_hash != state.head_hash:
            raise IntegrityError("ledger hash chain is broken")
        if event.expected_hash() != event.event_hash:
            raise IntegrityError("event content hash does not match")
        _apply(state, event)
        state.event_count += 1
        state.head_hash = event.event_hash
    return state


def _apply(state: ResearchState, event: LedgerEvent) -> None:
    payload = event.payload
    if event.kind is EventKind.OBJECT_RECORDED:
        object_data = payload.get("object")
        if not isinstance(object_data, Mapping):
            raise IntegrityError("object event has no object")
        object_id = str(object_data.get("id", ""))
        if object_id in state.objects:
            raise IntegrityError(f"research object already exists: {object_id}")
        provenance_data = object_data.get("provenance")
        if not isinstance(provenance_data, Mapping):
            raise IntegrityError("research object has no provenance")
        obj = ResearchObject(
            id=object_id,
            kind=ResearchObjectKind(object_data["kind"]),
            title=str(object_data["title"]),
            content=dict(object_data["content"]),
            provenance=Provenance(
                actor=str(provenance_data["actor"]),
                created_at=datetime.fromisoformat(str(provenance_data["created_at"])),
                source=str(provenance_data["source"]),
            ),
        )
        state.objects[obj.id] = obj
        state.statuses[obj.id] = ObjectStatus(payload["initial_status"])
        return
    if event.kind is EventKind.STATUS_TRANSITIONED:
        object_id = str(payload.get("object_id", ""))
        if object_id not in state.objects:
            raise IntegrityError(f"unknown research object: {object_id}")
        old_status = ObjectStatus(payload["from"])
        new_status = ObjectStatus(payload["to"])
        if state.statuses[object_id] is not old_status:
            raise IntegrityError("transition source does not match replayed state")
        if new_status not in ALLOWED_TRANSITIONS[old_status]:
            raise IntegrityError(f"invalid status transition: {old_status} -> {new_status}")
        state.statuses[object_id] = new_status
        return
    if event.kind is EventKind.RELATION_RECORDED:
        subject_id = str(payload.get("subject_id", ""))
        object_id = str(payload.get("object_id", ""))
        if subject_id not in state.objects or object_id not in state.objects:
            raise IntegrityError("relations require existing research objects")
        relation = Relation(subject_id, str(payload.get("predicate", "")), object_id)
        if not relation.predicate:
            raise IntegrityError("relation predicate is required")
        if relation in state.relations:
            raise IntegrityError("duplicate relation")
        state.relations.append(relation)
        return
    if event.kind is EventKind.ARTIFACT_ATTACHED:
        object_id = str(payload.get("object_id", ""))
        digest = str(payload.get("digest", ""))
        if object_id not in state.objects:
            raise IntegrityError(f"unknown research object: {object_id}")
        state.artifacts[object_id] = (*state.artifacts.get(object_id, ()), digest)
        return
    raise IntegrityError(f"unsupported event kind: {event.kind}")


class FileResearchLedger:
    """File-backed reference ledger; the JSONL log is its only state source."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.log_path = directory / "events.jsonl"
        self.artifact_directory = directory / "artifacts" / "sha256"
        directory.mkdir(parents=True, exist_ok=True)
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self.state = replay(self.events())

    def events(self) -> tuple[LedgerEvent, ...]:
        events: list[LedgerEvent] = []
        with self.log_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete event at line {line_number}")
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise IntegrityError(f"invalid JSON at line {line_number}") from error
                if not isinstance(value, Mapping):
                    raise IntegrityError(f"event at line {line_number} is not an object")
                events.append(LedgerEvent.from_dict(value))
        return tuple(events)

    def _append(
        self,
        kind: EventKind,
        occurred_at: datetime,
        actor: str,
        payload: Mapping[str, Any],
    ) -> LedgerEvent:
        if not actor.strip():
            raise ValueError("event actor is required")
        event = LedgerEvent.create(
            sequence=self.state.event_count,
            kind=kind,
            occurred_at=occurred_at,
            actor=actor,
            payload=payload,
            previous_hash=self.state.head_hash,
        )
        candidate_state = replay((*self.events(), event))
        encoded = canonical_json(event.to_dict()) + b"\n"
        descriptor = os.open(self.log_path, os.O_WRONLY | os.O_APPEND)
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.state = candidate_state
        return event

    def record(self, obj: ResearchObject) -> LedgerEvent:
        return self._append(
            EventKind.OBJECT_RECORDED,
            obj.provenance.created_at,
            obj.provenance.actor,
            {"object": _object_dict(obj), "initial_status": ObjectStatus.PROPOSED},
        )

    def transition(
        self,
        object_id: str,
        new_status: ObjectStatus,
        provenance: Provenance,
        *,
        reason: str,
    ) -> LedgerEvent:
        if object_id not in self.state.statuses:
            raise KeyError(object_id)
        if not reason.strip():
            raise ValueError("transition reason is required")
        return self._append(
            EventKind.STATUS_TRANSITIONED,
            provenance.created_at,
            provenance.actor,
            {
                "object_id": object_id,
                "from": self.state.statuses[object_id],
                "to": new_status,
                "reason": reason,
                "provenance": _provenance_dict(provenance),
            },
        )

    def relate(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        provenance: Provenance,
    ) -> LedgerEvent:
        return self._append(
            EventKind.RELATION_RECORDED,
            provenance.created_at,
            provenance.actor,
            {
                "subject_id": subject_id,
                "predicate": predicate,
                "object_id": object_id,
                "provenance": _provenance_dict(provenance),
            },
        )

    def attach_artifact(
        self,
        object_id: str,
        content: bytes,
        provenance: Provenance,
        *,
        media_type: str = "application/octet-stream",
    ) -> str:
        if object_id not in self.state.objects:
            raise KeyError(object_id)
        if not media_type.strip():
            raise ValueError("artifact media_type is required")
        digest = hashlib.sha256(content).hexdigest()
        path = self.artifact_directory / digest
        if path.exists():
            if path.read_bytes() != content:
                raise IntegrityError("artifact digest collision")
        else:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            try:
                _write_all(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        self._append(
            EventKind.ARTIFACT_ATTACHED,
            provenance.created_at,
            provenance.actor,
            {
                "object_id": object_id,
                "digest": digest,
                "size_bytes": len(content),
                "media_type": media_type,
                "provenance": _provenance_dict(provenance),
            },
        )
        return digest

    def read_artifact(self, digest: str) -> bytes:
        content = (self.artifact_directory / digest).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise IntegrityError("artifact content hash does not match")
        return content
