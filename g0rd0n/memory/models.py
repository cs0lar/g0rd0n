"""Durable records shared by otherwise isolated research sessions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from g0rd0n.evaluation import EvaluationPurpose, EvaluationReport
from g0rd0n.methods import ExecutionReceipt, ExecutionStatus
from g0rd0n.programs import ProgramCost


def _required(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _timestamp(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _digest(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class SourceReference:
    citation: str
    locator: str

    def __post_init__(self) -> None:
        _required(self.citation, "source citation")
        _required(self.locator, "source locator")


@dataclass(frozen=True, slots=True)
class LiteratureEntry:
    id: str
    title: str
    applicability: str
    mechanism: str
    reproduction_recipe: tuple[str, ...]
    limitations: tuple[str, ...]
    sources: tuple[SourceReference, ...]
    recorded_by: str
    recorded_at: datetime
    briefing_safe: bool = True

    def __post_init__(self) -> None:
        for field in ("id", "title", "applicability", "mechanism", "recorded_by"):
            _required(getattr(self, field), field)
        if not self.reproduction_recipe or not self.limitations or not self.sources:
            raise ValueError("literature entries require a recipe, limitations, and source provenance")
        if any(not item.strip() for item in (*self.reproduction_recipe, *self.limitations)):
            raise ValueError("literature recipe and limitations cannot contain empty text")
        _timestamp(self.recorded_at, "recorded_at")

    @property
    def novelty_text(self) -> str:
        return " ".join((self.title, self.applicability, self.mechanism))


@dataclass(frozen=True, slots=True)
class Proposal:
    id: str
    method_id: str
    summary: str
    proposed_by: str
    proposed_at: datetime

    def __post_init__(self) -> None:
        for field in ("id", "method_id", "summary", "proposed_by"):
            _required(getattr(self, field), field)
        _timestamp(self.proposed_at, "proposed_at")


class FindingStatus(StrEnum):
    VALID = "valid"
    FAILED = "failed"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class FindingScore:
    benchmark_id: str
    role: str
    mean: float
    headroom_closed: float
    confidence_interval_95: tuple[float, float]

    def __post_init__(self) -> None:
        _required(self.benchmark_id, "benchmark_id")
        _required(self.role, "score role")
        values = (self.mean, self.headroom_closed, *self.confidence_interval_95)
        if len(self.confidence_interval_95) != 2 or any(not math.isfinite(item) for item in values):
            raise ValueError("finding scores and intervals must be finite")


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    proposal_id: str
    method_id: str
    protocol_hash: str
    code_hash: str
    execution_receipt_id: str
    result_artifact_hash: str
    execution_status: ExecutionStatus
    evaluation_purpose: EvaluationPurpose
    status: FindingStatus
    eligible: bool
    aggregate_score: float | None
    scores: tuple[FindingScore, ...]
    cost: ProgramCost
    failures: tuple[str, ...]
    interpretation: str
    recorded_by: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        for field in ("id", "proposal_id", "method_id", "execution_receipt_id", "interpretation", "recorded_by"):
            _required(getattr(self, field), field)
        for field in ("protocol_hash", "code_hash", "result_artifact_hash"):
            _digest(getattr(self, field), field)
        _timestamp(self.recorded_at, "recorded_at")
        if self.aggregate_score is not None and not math.isfinite(self.aggregate_score):
            raise ValueError("aggregate_score must be finite")
        if self.status is FindingStatus.VALID:
            if self.execution_status is not ExecutionStatus.SUCCEEDED or not self.eligible or self.aggregate_score is None:
                raise ValueError("valid findings require a successful, eligible scored execution")
        elif not self.failures:
            raise ValueError("failed and invalid findings require explicit failure reasons")

    @classmethod
    def from_evaluation(
        cls,
        *,
        finding_id: str,
        proposal_id: str,
        receipt: ExecutionReceipt,
        report: EvaluationReport,
        status: FindingStatus,
        cost: ProgramCost,
        failures: tuple[str, ...],
        interpretation: str,
        recorded_by: str,
        recorded_at: datetime,
    ) -> "Finding":
        if report.request.artifact_hash != receipt.result_artifact_hash:
            raise ValueError("evaluation artifact does not match execution receipt")
        scores = tuple(
            FindingScore(
                item.benchmark_id,
                item.role.value,
                item.mean,
                item.headroom_closed,
                item.confidence_interval_95,
            )
            for item in report.scores
        )
        return cls(
            finding_id,
            proposal_id,
            receipt.method_id,
            receipt.protocol_hash,
            receipt.code_hash,
            receipt.id,
            receipt.result_artifact_hash,
            receipt.status,
            report.request.purpose,
            status,
            report.eligible,
            report.aggregate_headroom_closed,
            scores,
            cost,
            failures,
            interpretation,
            recorded_by,
            recorded_at,
        )


class ReviewerKind(StrEnum):
    HUMAN = "human"
    RESOURCE = "resource"


class ReviewPosition(StrEnum):
    SUPPORT = "support"
    CHALLENGE = "challenge"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    id: str
    finding_id: str
    reviewer_id: str
    reviewer_kind: ReviewerKind
    position: ReviewPosition
    comment: str
    resolved: bool
    recorded_at: datetime

    def __post_init__(self) -> None:
        for field in ("id", "finding_id", "reviewer_id", "comment"):
            _required(getattr(self, field), field)
        _timestamp(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    rank: int
    finding_id: str
    proposal_id: str
    method_id: str
    evaluation_purpose: EvaluationPurpose
    aggregate_score: float
    cost: ProgramCost
    execution_receipt_id: str
    result_artifact_hash: str


@dataclass(frozen=True, slots=True)
class FindingsForum:
    """A replayed view, deliberately containing no independently mutable state."""

    findings: tuple[Finding, ...]
    reviews: tuple[ReviewRecord, ...]


class StopAction(StrEnum):
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class StopDecision:
    action: StopAction
    reason: str


class MemoryEventKind(StrEnum):
    LITERATURE_ADDED = "literature_added"
    PROPOSAL_ADDED = "proposal_added"
    DUPLICATE_REJECTED = "duplicate_rejected"
    FINDING_ADDED = "finding_added"
    REVIEW_ADDED = "review_added"


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    sequence: int
    kind: MemoryEventKind
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    accepted: bool
    proposal_id: str
    nearest_id: str | None
    similarity: float
