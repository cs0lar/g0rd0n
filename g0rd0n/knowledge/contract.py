"""Provider-neutral contract for temporal, provenance-aware assertions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

OPEN_ENDED = 0


class AssertionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    RETRACTION = "retraction"


@dataclass(frozen=True, slots=True)
class WriteContext:
    valid_from: int
    observed_at: int
    source: str
    method: str
    valid_to: int = OPEN_ENDED
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.valid_from < 0 or self.valid_to < 0 or self.observed_at < 0:
            raise ValueError("timestamps must be non-negative Unix seconds")
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from or open-ended")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not self.source.strip() or not self.method.strip():
            raise ValueError("source and method are required")


@dataclass(frozen=True, slots=True)
class AssertionRecord:
    id: str
    subject: str
    predicate: str
    object: str
    valid_from: int
    valid_to: int
    observed_at: int
    confidence: float
    status: AssertionStatus
    supersedes_id: str | None = None
    retracts_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    assertion_id: str
    source: str
    recorded_at: int
    method: str


@dataclass(frozen=True, slots=True)
class Query:
    subject: str
    predicate: str | None = None
    valid_at: int | None = None
    known_at: int | None = None

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("query subject is required")
        if self.valid_at is not None and self.valid_at < 0:
            raise ValueError("valid_at must be non-negative")
        if self.known_at is not None and self.known_at < 0:
            raise ValueError("known_at must be non-negative")


@dataclass(frozen=True, slots=True)
class Conflict:
    left: AssertionRecord
    right: AssertionRecord


@runtime_checkable
class KnowledgeStore(Protocol):
    def assert_(
        self, subject: str, predicate: str, object: str, context: WriteContext
    ) -> AssertionRecord: ...

    def retract(self, assertion_id: str, context: WriteContext) -> AssertionRecord: ...

    def supersede(
        self, assertion_id: str, new_object: str, context: WriteContext
    ) -> AssertionRecord: ...

    def query(self, query: Query) -> tuple[AssertionRecord, ...]: ...

    def history(self, subject: str, predicate: str) -> tuple[AssertionRecord, ...]: ...

    def provenance(self, assertion_id: str) -> ProvenanceRecord | None: ...

    def conflicts(self, subject: str, predicate: str) -> tuple[Conflict, ...]: ...
