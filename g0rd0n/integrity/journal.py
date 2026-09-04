"""Append-only integrity decisions, confirmations, appeals, and quarantine state."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Mapping

from g0rd0n.memory import Finding, LeaderboardEntry, ResearchMemoryJournal
from g0rd0n.research.ledger import GENESIS_HASH, IntegrityError, canonical_json, content_hash

from .models import (
    AppealOutcome,
    AppealRecord,
    ConfirmationRecord,
    ConfirmationVerdict,
    ChunkJudgment,
    IntegrityAssessment,
    IntegrityCategory,
    IntegrityDisposition,
    IntegrityFlag,
    IntegrityPolicy,
    PreflightReport,
    TraceEvent,
    TraceReport,
)


class IntegrityEventKind(StrEnum):
    ASSESSED = "assessed"
    CONFIRMED = "confirmed"
    APPEALED = "appealed"


@dataclass(frozen=True, slots=True)
class IntegrityEvent:
    sequence: int
    kind: IntegrityEventKind
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str


@dataclass
class _State:
    events: list[IntegrityEvent]
    assessments: dict[str, IntegrityAssessment]
    confirmations: dict[str, ConfirmationRecord]
    appeals: dict[str, AppealRecord]
    finding_assessments: dict[str, list[str]]
    preflight_reports: dict[str, PreflightReport]
    trace_reports: dict[str, TraceReport]


def _empty() -> _State:
    return _State([], {}, {}, {}, {}, {}, {})


def _event(sequence: int, kind: IntegrityEventKind, payload: Mapping[str, Any], previous: str) -> IntegrityEvent:
    normalized = json.loads(canonical_json(payload))
    unsigned = {"sequence": sequence, "kind": kind, "payload": normalized, "previous_hash": previous}
    return IntegrityEvent(sequence, kind, normalized, previous, content_hash(unsigned))


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("persisted timestamp must include a timezone")
    return parsed


def _flag(value: Mapping[str, Any]) -> IntegrityFlag:
    return IntegrityFlag(
        str(value["id"]), IntegrityCategory(value["category"]), float(value["suspicion"]),
        str(value["reason"]), tuple(str(item) for item in value["evidence"]),
        bool(value["deterministic"]), str(value["raised_by"]),
    )


def _assessment(value: Mapping[str, Any]) -> IntegrityAssessment:
    return IntegrityAssessment(
        str(value["id"]), str(value["finding_id"]), str(value["policy_version"]),
        str(value["policy_hash"]), str(value["preflight_report_hash"]), str(value["trace_report_hash"]),
        tuple(_flag(item) for item in value["flags"]), IntegrityDisposition(value["disposition"]),
        str(value["assessed_by"]), _time(value["assessed_at"]),
    )


def _preflight(value: Mapping[str, Any]) -> PreflightReport:
    return PreflightReport(
        str(value["policy_version"]), str(value["policy_hash"]), str(value["method_id"]),
        str(value["protocol_hash"]), str(value["code_hash"]), str(value["data_lineage_hash"]),
        tuple(str(item) for item in value["inspected_permissions"]),
        tuple(str(item) for item in value["scanned_files"]),
        tuple(_flag(item) for item in value["flags"]),
    )


def _trace_event(value: Mapping[str, Any]) -> TraceEvent:
    return TraceEvent(
        int(value["sequence"]), str(value["kind"]), str(value["actor"]),
        str(value["target"]), dict(value["details"]),
    )


def _judgment(value: Mapping[str, Any]) -> ChunkJudgment:
    return ChunkJudgment(
        str(value["chunk_id"]), tuple(int(item) for item in value["event_sequences"]),
        float(value["suspicion"]), tuple(IntegrityCategory(item) for item in value["categories"]),
        tuple(str(item) for item in value["evidence"]), str(value["reviewer"]),
        bool(value.get("ambiguous", False)), tuple(str(item) for item in value.get("child_ids", ())),
    )


def _trace(value: Mapping[str, Any]) -> TraceReport:
    return TraceReport(
        str(value["policy_version"]), str(value["policy_hash"]), str(value["trace_hash"]),
        int(value["event_count"]), tuple(_trace_event(item) for item in value["events"]),
        tuple(_judgment(item) for item in value["judgments"]), tuple(_flag(item) for item in value["flags"]),
        float(value["maximum_suspicion"]), bool(value["complete_coverage"]),
        bool(value["binding_checked"]), bool(value["monitor_failed"]),
    )


def _confirmation(value: Mapping[str, Any]) -> ConfirmationRecord:
    return ConfirmationRecord(
        str(value["id"]), str(value["assessment_id"]), str(value["flag_id"]),
        str(value["reviewer"]), ConfirmationVerdict(value["verdict"]),
        str(value["rationale"]), _time(value["reviewed_at"]),
    )


def _appeal(value: Mapping[str, Any]) -> AppealRecord:
    return AppealRecord(
        str(value["id"]), str(value["assessment_id"]), str(value["appellant"]),
        str(value["reviewer"]), str(value["rationale"]), AppealOutcome(value["outcome"]),
        bool(value["false_positive"]), _time(value["reviewed_at"]),
    )


class IntegrityJournal:
    def __init__(self, path: Path, policy: IntegrityPolicy) -> None:
        self.path = path
        self.lock_path = path.with_name(f"{path.name}.lock")
        self.policy = policy
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self.lock_path.touch(exist_ok=True)
        with self._locked(exclusive=False):
            self._state = self._read()

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        with self.lock_path.open("rb") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def refresh(self) -> None:
        with self._locked(exclusive=False):
            self._state = self._read()

    def events(self) -> tuple[IntegrityEvent, ...]:
        self.refresh()
        return tuple(self._state.events)

    def assessments(self) -> tuple[IntegrityAssessment, ...]:
        self.refresh()
        return tuple(self._state.assessments[key] for key in sorted(self._state.assessments))

    def confirmations(self) -> tuple[ConfirmationRecord, ...]:
        self.refresh()
        return tuple(self._state.confirmations[key] for key in sorted(self._state.confirmations))

    def appeals(self) -> tuple[AppealRecord, ...]:
        self.refresh()
        return tuple(self._state.appeals[key] for key in sorted(self._state.appeals))

    def preflight_report(self, assessment_id: str) -> PreflightReport:
        self.refresh()
        return self._state.preflight_reports[assessment_id]

    def trace_report(self, assessment_id: str) -> TraceReport:
        self.refresh()
        return self._state.trace_reports[assessment_id]

    def assess(
        self,
        finding: Finding,
        preflight: PreflightReport,
        trace: TraceReport,
        *,
        assessment_id: str,
        actor: str,
        assessed_at: datetime,
    ) -> IntegrityAssessment:
        if (preflight.policy_version, preflight.policy_hash) != (self.policy.version, self.policy.policy_hash):
            raise ValueError("preflight report uses a different integrity policy")
        if (trace.policy_version, trace.policy_hash) != (self.policy.version, self.policy.policy_hash):
            raise ValueError("trace report uses a different integrity policy")
        if (preflight.method_id, preflight.protocol_hash, preflight.code_hash) != (
            finding.method_id, finding.protocol_hash, finding.code_hash
        ):
            raise ValueError("preflight report does not match the assessed finding artifact")
        if not trace.binding_checked:
            raise ValueError("trace report must include execution and evaluation binding inspection")
        flags_by_id = {item.id: item for item in (*preflight.flags, *trace.flags)}
        flags = tuple(flags_by_id[key] for key in sorted(flags_by_id))
        quarantine = any(item.suspicion >= self.policy.threshold(item.category) for item in flags)
        assessment = IntegrityAssessment(
            assessment_id,
            finding.id,
            self.policy.version,
            self.policy.policy_hash,
            preflight.report_hash,
            trace.report_hash,
            flags,
            IntegrityDisposition.QUARANTINED if quarantine else IntegrityDisposition.CLEAR,
            actor,
            assessed_at,
        )
        self._append(
            IntegrityEventKind.ASSESSED,
            {
                "assessment": asdict(assessment),
                "preflight_report": asdict(preflight),
                "trace_report": asdict(trace),
            },
        )
        return assessment

    def confirm(self, record: ConfirmationRecord) -> None:
        self._append(IntegrityEventKind.CONFIRMED, asdict(record))

    def appeal(self, record: AppealRecord) -> None:
        self._append(IntegrityEventKind.APPEALED, asdict(record))

    def is_quarantined(self, finding_id: str) -> bool:
        self.refresh()
        assessment_ids = self._state.finding_assessments.get(finding_id, [])
        if not assessment_ids:
            return True
        assessment = self._state.assessments[assessment_ids[-1]]
        if assessment.disposition is IntegrityDisposition.CLEAR:
            return False
        appeals = [item for item in self._state.appeals.values() if item.assessment_id == assessment.id]
        if appeals and appeals[-1].outcome is AppealOutcome.RELEASED:
            return False
        blocking = [
            item for item in assessment.flags
            if item.suspicion >= self.policy.threshold(item.category)
        ]
        if any(item.deterministic for item in blocking):
            return True
        confirmations = {
            item.flag_id: item for item in self._state.confirmations.values()
            if item.assessment_id == assessment.id
        }
        return not blocking or any(
            confirmations.get(item.id) is None
            or confirmations[item.id].verdict is not ConfirmationVerdict.FALSE_POSITIVE
            for item in blocking
        )

    def leaderboard(self, memory: ResearchMemoryJournal) -> tuple[LeaderboardEntry, ...]:
        return tuple(item for item in memory.leaderboard() if not self.is_quarantined(item.finding_id))

    def _append(self, kind: IntegrityEventKind, payload: Mapping[str, Any]) -> None:
        with self._locked(exclusive=True):
            state = self._read()
            previous = state.events[-1].event_hash if state.events else GENESIS_HASH
            event = _event(len(state.events), kind, payload, previous)
            self._apply(state, event)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND)
            try:
                remaining = memoryview(canonical_json(asdict(event)) + b"\n")
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written == 0:
                        raise OSError("integrity journal write made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            state.events.append(event)
            self._state = state

    def _apply(self, state: _State, event: IntegrityEvent) -> None:
        if event.kind is IntegrityEventKind.ASSESSED:
            item = _assessment(event.payload["assessment"])
            preflight = _preflight(event.payload["preflight_report"])
            trace = _trace(event.payload["trace_report"])
            if item.id in state.assessments:
                raise IntegrityError("integrity assessment id already exists")
            if (item.policy_version, item.policy_hash) != (self.policy.version, self.policy.policy_hash):
                raise IntegrityError("assessment policy does not match journal policy")
            if item.preflight_report_hash != preflight.report_hash or item.trace_report_hash != trace.report_hash:
                raise IntegrityError("assessment report hashes do not match retained evidence")
            quarantine = any(
                flag.suspicion >= self.policy.threshold(flag.category) for flag in item.flags
            )
            expected = IntegrityDisposition.QUARANTINED if quarantine else IntegrityDisposition.CLEAR
            if item.disposition is not expected:
                raise IntegrityError("assessment disposition does not match its flags")
            state.assessments[item.id] = item
            state.preflight_reports[item.id] = preflight
            state.trace_reports[item.id] = trace
            state.finding_assessments.setdefault(item.finding_id, []).append(item.id)
        elif event.kind is IntegrityEventKind.CONFIRMED:
            item = _confirmation(event.payload)
            assessment = state.assessments.get(item.assessment_id)
            if item.id in state.confirmations or assessment is None:
                raise IntegrityError("confirmation must uniquely reference an assessment")
            flags = {flag.id: flag for flag in assessment.flags}
            flag = flags.get(item.flag_id)
            if flag is None or item.reviewer in {flag.raised_by, assessment.assessed_by}:
                raise IntegrityError("flag confirmation must be independent and reference an existing flag")
            if any(
                existing.assessment_id == item.assessment_id and existing.flag_id == item.flag_id
                for existing in state.confirmations.values()
            ):
                raise IntegrityError("flag already has an independent confirmation")
            state.confirmations[item.id] = item
        else:
            item = _appeal(event.payload)
            assessment = state.assessments.get(item.assessment_id)
            if item.id in state.appeals or assessment is None:
                raise IntegrityError("appeal must uniquely reference an assessment")
            if item.reviewer == assessment.assessed_by:
                raise IntegrityError("appeal reviewer must be independent of the assessment")
            state.appeals[item.id] = item

    def _read(self) -> _State:
        state = _empty()
        previous = GENESIS_HASH
        with self.path.open(encoding="utf-8") as stream:
            for sequence, line in enumerate(stream):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete integrity event at line {sequence + 1}")
                try:
                    value = json.loads(line)
                    event = IntegrityEvent(
                        int(value["sequence"]), IntegrityEventKind(value["kind"]), dict(value["payload"]),
                        str(value["previous_hash"]), str(value["event_hash"]),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise IntegrityError(f"invalid integrity event at line {sequence + 1}") from error
                expected = _event(sequence, event.kind, event.payload, previous)
                if event != expected:
                    raise IntegrityError("integrity event sequence or hash chain is invalid")
                try:
                    self._apply(state, event)
                except (KeyError, TypeError, ValueError) as error:
                    raise IntegrityError(f"invalid integrity payload at line {sequence + 1}") from error
                state.events.append(event)
                previous = event.event_hash
        return state
