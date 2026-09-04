"""Concurrent append-only journal and deterministic research-memory views."""

from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from g0rd0n.evaluation import EvaluationPurpose
from g0rd0n.methods import ExecutionStatus
from g0rd0n.programs import ProgramCost
from g0rd0n.research.ledger import GENESIS_HASH, IntegrityError, canonical_json, content_hash

from .models import (
    Finding,
    FindingScore,
    FindingStatus,
    FindingsForum,
    LeaderboardEntry,
    LiteratureEntry,
    MemoryEvent,
    MemoryEventKind,
    Proposal,
    ProposalDecision,
    ReviewPosition,
    ReviewRecord,
    ReviewerKind,
    SourceReference,
    StopAction,
    StopDecision,
)


@dataclass
class _State:
    events: list[MemoryEvent]
    literature: dict[str, LiteratureEntry]
    proposals: dict[str, Proposal]
    findings: dict[str, Finding]
    reviews: dict[str, ReviewRecord]


def _empty() -> _State:
    return _State([], {}, {}, {}, {})


def _event(sequence: int, kind: MemoryEventKind, payload: Mapping[str, Any], previous: str) -> MemoryEvent:
    normalized = json.loads(canonical_json(payload))
    unsigned = {"sequence": sequence, "kind": kind, "payload": normalized, "previous_hash": previous}
    return MemoryEvent(sequence, kind, normalized, previous, content_hash(unsigned))


def _when(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("persisted timestamp has no timezone")
    return parsed


def _cost(value: Mapping[str, Any]) -> ProgramCost:
    return ProgramCost.from_dict(value)


def _literature(value: Mapping[str, Any]) -> LiteratureEntry:
    return LiteratureEntry(
        str(value["id"]), str(value["title"]), str(value["applicability"]), str(value["mechanism"]),
        tuple(str(item) for item in value["reproduction_recipe"]),
        tuple(str(item) for item in value["limitations"]),
        tuple(SourceReference(str(item["citation"]), str(item["locator"])) for item in value["sources"]),
        str(value["recorded_by"]), _when(value["recorded_at"]), bool(value.get("briefing_safe", True)),
    )


def _proposal(value: Mapping[str, Any]) -> Proposal:
    return Proposal(
        str(value["id"]), str(value["method_id"]), str(value["summary"]),
        str(value["proposed_by"]), _when(value["proposed_at"]),
    )


def _finding(value: Mapping[str, Any]) -> Finding:
    return Finding(
        str(value["id"]), str(value["proposal_id"]), str(value["method_id"]),
        str(value["protocol_hash"]), str(value["code_hash"]), str(value["execution_receipt_id"]),
        str(value["result_artifact_hash"]), ExecutionStatus(value["execution_status"]),
        EvaluationPurpose(value["evaluation_purpose"]), FindingStatus(value["status"]),
        bool(value["eligible"]), None if value.get("aggregate_score") is None else float(value["aggregate_score"]),
        tuple(
            FindingScore(
                str(item["benchmark_id"]), str(item["role"]), float(item["mean"]),
                float(item["headroom_closed"]), tuple(float(point) for point in item["confidence_interval_95"]),
            )
            for item in value["scores"]
        ),
        _cost(value["cost"]), tuple(str(item) for item in value["failures"]),
        str(value["interpretation"]), str(value["recorded_by"]), _when(value["recorded_at"]),
    )


def _review(value: Mapping[str, Any]) -> ReviewRecord:
    return ReviewRecord(
        str(value["id"]), str(value["finding_id"]), str(value["reviewer_id"]),
        ReviewerKind(value["reviewer_kind"]), ReviewPosition(value["position"]), str(value["comment"]),
        bool(value["resolved"]), _when(value["recorded_at"]),
    )


def _signature(text: str) -> frozenset[str]:
    stop_words = {"a", "an", "the", "from", "to", "of", "and"}
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        if token in stop_words:
            continue
        if token.endswith("s") and len(token) > 3:
            token = token[:-1]
        tokens.add(token)
    if not tokens:
        raise ValueError("novelty check requires substantive text")
    return frozenset(tokens)


def _nearest(text: str, candidates: Mapping[str, str]) -> tuple[str | None, float]:
    signature = _signature(text)
    nearest_id: str | None = None
    best = 0.0
    for candidate_id, candidate in sorted(candidates.items()):
        other = _signature(candidate)
        similarity = len(signature & other) / len(signature | other)
        if similarity > best:
            nearest_id, best = candidate_id, similarity
    return nearest_id, best


class ResearchMemoryJournal:
    """The journal is source of truth; every public view is rebuilt from it."""

    def __init__(self, path: Path, *, similarity_threshold: float = 0.9) -> None:
        if not 0 < similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be in (0, 1]")
        self.path = path
        self.lock_path = path.with_name(f"{path.name}.lock")
        self.similarity_threshold = similarity_threshold
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

    def events(self) -> tuple[MemoryEvent, ...]:
        self.refresh()
        return tuple(self._state.events)

    def survey(self) -> tuple[LiteratureEntry, ...]:
        self.refresh()
        return tuple(self._state.literature[key] for key in sorted(self._state.literature))

    def findings(self) -> tuple[Finding, ...]:
        self.refresh()
        return tuple(self._state.findings[key] for key in sorted(self._state.findings))

    def proposals(self) -> tuple[Proposal, ...]:
        self.refresh()
        return tuple(self._state.proposals[key] for key in sorted(self._state.proposals))

    def reviews(self) -> tuple[ReviewRecord, ...]:
        self.refresh()
        return tuple(self._state.reviews[key] for key in sorted(self._state.reviews))

    def forum(self) -> FindingsForum:
        self.refresh()
        return FindingsForum(
            tuple(self._state.findings[key] for key in sorted(self._state.findings)),
            tuple(self._state.reviews[key] for key in sorted(self._state.reviews)),
        )

    def add_literature(self, entry: LiteratureEntry) -> None:
        with self._locked(exclusive=True):
            state = self._read()
            nearest_id, similarity = _nearest(
                entry.novelty_text, {key: item.novelty_text for key, item in state.literature.items()}
            )
            if similarity >= self.similarity_threshold:
                raise ValueError(f"duplicate literature entry matches {nearest_id} ({similarity:.3f})")
            self._append_locked(state, MemoryEventKind.LITERATURE_ADDED, asdict(entry))

    def propose(self, proposal: Proposal) -> ProposalDecision:
        with self._locked(exclusive=True):
            state = self._read()
            prior_work = {key: item.novelty_text for key, item in state.literature.items()}
            prior_work.update({key: item.summary for key, item in state.proposals.items()})
            nearest_id, similarity = _nearest(
                proposal.summary, prior_work
            )
            if similarity >= self.similarity_threshold:
                self._append_locked(
                    state,
                    MemoryEventKind.DUPLICATE_REJECTED,
                    {
                        "proposal_id": proposal.id,
                        "nearest_id": nearest_id,
                        "similarity": similarity,
                        "proposed_by": proposal.proposed_by,
                        "proposed_at": proposal.proposed_at,
                    },
                )
                return ProposalDecision(False, proposal.id, nearest_id, similarity)
            self._append_locked(state, MemoryEventKind.PROPOSAL_ADDED, asdict(proposal))
            return ProposalDecision(True, proposal.id, nearest_id, similarity)

    def add_finding(self, finding: Finding) -> None:
        self._append(MemoryEventKind.FINDING_ADDED, asdict(finding))

    def add_review(self, review: ReviewRecord) -> None:
        self._append(MemoryEventKind.REVIEW_ADDED, asdict(review))

    def leaderboard(self) -> tuple[LeaderboardEntry, ...]:
        self.refresh()
        eligible = [
            item for item in self._state.findings.values()
            if item.status is FindingStatus.VALID
            and item.aggregate_score is not None
        ]
        eligible.sort(key=lambda item: (-float(item.aggregate_score), item.id))
        return tuple(
            LeaderboardEntry(
                rank, item.id, item.proposal_id, item.method_id, item.evaluation_purpose,
                float(item.aggregate_score),
                item.cost, item.execution_receipt_id, item.result_artifact_hash,
            )
            for rank, item in enumerate(eligible, 1)
        )

    def briefing(self, *, mission: str, remaining_budget: ProgramCost) -> str:
        if not mission.strip():
            raise ValueError("mission is required")
        self.refresh()
        lines = ["# Fresh Research Session", "", "## Mission", "", mission.strip(), "", "## Remaining budget", ""]
        lines.append(
            f"{remaining_budget.currency_micros} currency µunits; {remaining_budget.tokens} tokens; "
            f"{remaining_budget.compute_ms} compute ms; {remaining_budget.energy_joules:g} J; "
            f"{remaining_budget.human_minutes:g} human min"
        )
        lines.extend(["", "## Shared survey", ""])
        safe_entries = [item for item in self._state.literature.values() if item.briefing_safe]
        lines.extend(
            f"- {item.id}: {item.title} — {item.applicability} Limitation: {item.limitations[0]}"
            for item in sorted(safe_entries, key=lambda entry: entry.id)
        )
        if not safe_entries:
            lines.append("- No briefing-safe literature entries.")
        lines.extend(["", "## Approved findings", ""])
        safe_findings = [
            item for item in self._state.findings.values()
            if item.status is FindingStatus.VALID and item.evaluation_purpose is not EvaluationPurpose.CONFIRM
        ]
        lines.extend(
            f"- {item.id} ({item.method_id}): {item.interpretation} [receipt {item.execution_receipt_id}; "
            f"cost {item.cost.currency_micros} currency µunits]"
            for item in sorted(safe_findings, key=lambda finding: finding.id)
        )
        if not safe_findings:
            lines.append("- No valid non-test findings.")
        lines.extend(["", "## Unresolved disagreements", ""])
        disagreements = [
            item for item in self._state.reviews.values()
            if item.position is ReviewPosition.CHALLENGE and not item.resolved
            and self._state.findings[item.finding_id].evaluation_purpose is not EvaluationPurpose.CONFIRM
        ]
        lines.extend(
            f"- {item.finding_id}: {item.comment} — {item.reviewer_id} ({item.reviewer_kind.value})"
            for item in sorted(disagreements, key=lambda review: review.id)
        )
        if not disagreements:
            lines.append("- None recorded.")
        return "\n".join(lines) + "\n"

    def stopping_decision(
        self, *, plateau_window: int = 3, minimum_improvement: float = 0.01, duplicate_limit: int = 3
    ) -> StopDecision:
        if plateau_window < 2 or minimum_improvement < 0 or duplicate_limit < 1:
            raise ValueError("stopping thresholds are invalid")
        self.refresh()
        proposal_events = [
            event for event in self._state.events
            if event.kind in {MemoryEventKind.PROPOSAL_ADDED, MemoryEventKind.DUPLICATE_REJECTED}
        ]
        if len(proposal_events) >= duplicate_limit and all(
            item.kind is MemoryEventKind.DUPLICATE_REJECTED for item in proposal_events[-duplicate_limit:]
        ):
            return StopDecision(StopAction.STOP, f"last {duplicate_limit} proposals duplicated durable work")
        valid = [
            self._state.findings[str(event.payload["id"])]
            for event in self._state.events if event.kind is MemoryEventKind.FINDING_ADDED
            and self._state.findings[str(event.payload["id"])].status is FindingStatus.VALID
            and self._state.findings[str(event.payload["id"])].evaluation_purpose is not EvaluationPurpose.CONFIRM
        ]
        if len(valid) > plateau_window:
            previous_best = max(float(item.aggregate_score) for item in valid[:-plateau_window])
            recent_best = max(float(item.aggregate_score) for item in valid[-plateau_window:])
            if recent_best <= previous_best + minimum_improvement:
                return StopDecision(StopAction.STOP, f"no material improvement across {plateau_window} findings")
        return StopDecision(StopAction.CONTINUE, "no plateau or duplicate streak reached")

    def _append(self, kind: MemoryEventKind, payload: Mapping[str, Any]) -> None:
        with self._locked(exclusive=True):
            self._append_locked(self._read(), kind, payload)

    def _append_locked(self, state: _State, kind: MemoryEventKind, payload: Mapping[str, Any]) -> None:
        previous = state.events[-1].event_hash if state.events else GENESIS_HASH
        event = _event(len(state.events), kind, payload, previous)
        self._apply(state, event)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND)
        try:
            content = memoryview(canonical_json(asdict(event)) + b"\n")
            while content:
                written = os.write(descriptor, content)
                if written == 0:
                    raise OSError("research memory write made no progress")
                content = content[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        state.events.append(event)
        self._state = state

    @staticmethod
    def _apply(state: _State, event: MemoryEvent) -> None:
        if event.kind is MemoryEventKind.LITERATURE_ADDED:
            item = _literature(event.payload)
            if item.id in state.literature:
                raise IntegrityError("literature id already exists")
            state.literature[item.id] = item
        elif event.kind is MemoryEventKind.PROPOSAL_ADDED:
            item = _proposal(event.payload)
            if item.id in state.proposals:
                raise IntegrityError("proposal id already exists")
            state.proposals[item.id] = item
        elif event.kind is MemoryEventKind.DUPLICATE_REJECTED:
            proposal_id = str(event.payload.get("proposal_id", "")).strip()
            nearest_id = str(event.payload.get("nearest_id", "")).strip()
            actor = str(event.payload.get("proposed_by", "")).strip()
            similarity = float(event.payload.get("similarity", -1))
            _when(event.payload.get("proposed_at"))
            if not proposal_id or not actor or not 0 <= similarity <= 1:
                raise IntegrityError("duplicate rejection metadata is invalid")
            if nearest_id not in state.proposals and nearest_id not in state.literature:
                raise IntegrityError("duplicate rejection must identify durable prior work")
        elif event.kind is MemoryEventKind.FINDING_ADDED:
            item = _finding(event.payload)
            proposal = state.proposals.get(item.proposal_id)
            if item.id in state.findings or proposal is None or proposal.method_id != item.method_id:
                raise IntegrityError("finding must uniquely bind an accepted matching proposal")
            state.findings[item.id] = item
        else:
            item = _review(event.payload)
            if item.id in state.reviews or item.finding_id not in state.findings:
                raise IntegrityError("review must uniquely reference a finding")
            state.reviews[item.id] = item

    def _read(self) -> _State:
        state = _empty()
        previous = GENESIS_HASH
        with self.path.open(encoding="utf-8") as stream:
            for sequence, line in enumerate(stream):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete research-memory event at line {sequence + 1}")
                try:
                    value = json.loads(line)
                    event = MemoryEvent(
                        int(value["sequence"]), MemoryEventKind(value["kind"]), dict(value["payload"]),
                        str(value["previous_hash"]), str(value["event_hash"]),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise IntegrityError(f"invalid research-memory event at line {sequence + 1}") from error
                expected = _event(sequence, event.kind, event.payload, previous)
                if event != expected:
                    raise IntegrityError("research-memory event sequence or hash chain is invalid")
                try:
                    self._apply(state, event)
                except (KeyError, TypeError, ValueError) as error:
                    raise IntegrityError(f"invalid research-memory payload at line {sequence + 1}") from error
                state.events.append(event)
                previous = event.event_hash
        return state
