"""Deterministic in-memory KnowledgeStore reference implementation."""

from __future__ import annotations

from dataclasses import replace

from .contract import (
    AssertionRecord,
    AssertionStatus,
    Conflict,
    OPEN_ENDED,
    ProvenanceRecord,
    Query,
    WriteContext,
)


class InMemoryKnowledgeStore:
    def __init__(self) -> None:
        self._assertions: list[AssertionRecord] = []
        self._provenance: dict[str, ProvenanceRecord] = {}

    def _next_id(self) -> str:
        return str(len(self._assertions) + 1)

    def _record_provenance(self, assertion_id: str, context: WriteContext) -> None:
        self._provenance[assertion_id] = ProvenanceRecord(
            assertion_id, context.source, context.observed_at, context.method
        )

    def _require(self, assertion_id: str) -> tuple[int, AssertionRecord]:
        for index, assertion in enumerate(self._assertions):
            if assertion.id == assertion_id:
                return index, assertion
        raise KeyError(assertion_id)

    def assert_(
        self, subject: str, predicate: str, object: str, context: WriteContext
    ) -> AssertionRecord:
        if not subject.strip() or not predicate.strip() or not object.strip():
            raise ValueError("subject, predicate, and object are required")
        assertion = AssertionRecord(
            self._next_id(),
            subject,
            predicate,
            object,
            context.valid_from,
            context.valid_to,
            context.observed_at,
            context.confidence,
            AssertionStatus.ACTIVE,
        )
        self._assertions.append(assertion)
        self._record_provenance(assertion.id, context)
        return assertion

    def retract(self, assertion_id: str, context: WriteContext) -> AssertionRecord:
        index, target = self._require(assertion_id)
        if target.status is not AssertionStatus.ACTIVE:
            raise ValueError("only active assertions can be retracted")
        self._assertions[index] = replace(target, status=AssertionStatus.RETRACTED)
        retraction = AssertionRecord(
            self._next_id(),
            target.subject,
            target.predicate,
            target.object,
            context.valid_from,
            context.valid_to,
            context.observed_at,
            context.confidence,
            AssertionStatus.RETRACTION,
            retracts_id=target.id,
        )
        self._assertions.append(retraction)
        self._record_provenance(retraction.id, context)
        return retraction

    def supersede(
        self, assertion_id: str, new_object: str, context: WriteContext
    ) -> AssertionRecord:
        index, target = self._require(assertion_id)
        if target.status is not AssertionStatus.ACTIVE:
            raise ValueError("only active assertions can be superseded")
        if not new_object.strip():
            raise ValueError("new_object is required")
        self._assertions[index] = replace(target, status=AssertionStatus.SUPERSEDED)
        replacement = AssertionRecord(
            self._next_id(),
            target.subject,
            target.predicate,
            new_object,
            context.valid_from,
            context.valid_to,
            context.observed_at,
            context.confidence,
            AssertionStatus.ACTIVE,
            supersedes_id=target.id,
        )
        self._assertions.append(replacement)
        self._record_provenance(replacement.id, context)
        return replacement

    def query(self, query: Query) -> tuple[AssertionRecord, ...]:
        matches: list[AssertionRecord] = []
        for assertion in self._assertions:
            if assertion.status is not AssertionStatus.ACTIVE or assertion.subject != query.subject:
                continue
            if query.predicate is not None and assertion.predicate != query.predicate:
                continue
            if query.valid_at is not None and not (
                assertion.valid_from <= query.valid_at
                and (assertion.valid_to == OPEN_ENDED or query.valid_at < assertion.valid_to)
            ):
                continue
            if query.known_at is not None and assertion.observed_at > query.known_at:
                continue
            matches.append(assertion)
        return tuple(matches)

    def history(self, subject: str, predicate: str) -> tuple[AssertionRecord, ...]:
        return tuple(
            assertion
            for assertion in self._assertions
            if assertion.subject == subject and assertion.predicate == predicate
        )

    def provenance(self, assertion_id: str) -> ProvenanceRecord | None:
        return self._provenance.get(assertion_id)

    def conflicts(self, subject: str, predicate: str) -> tuple[Conflict, ...]:
        assertions = self.query(Query(subject, predicate))
        conflicts: list[Conflict] = []
        for left_index, left in enumerate(assertions):
            for right in assertions[left_index + 1 :]:
                overlaps = (left.valid_to == OPEN_ENDED or right.valid_from < left.valid_to) and (
                    right.valid_to == OPEN_ENDED or left.valid_from < right.valid_to
                )
                if overlaps and left.object != right.object:
                    conflicts.append(Conflict(left, right))
        return tuple(conflicts)
