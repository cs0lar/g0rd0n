"""Immutable models for bounded, resumable research programs."""

from __future__ import annotations

import math
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


def _required(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} is required")
    return value


@dataclass(frozen=True, slots=True)
class ProgramCost:
    currency_micros: int = 0
    tokens: int = 0
    compute_ms: int = 0
    energy_joules: float = 0.0
    human_minutes: float = 0.0

    def __post_init__(self) -> None:
        values = (self.currency_micros, self.tokens, self.compute_ms, self.energy_joules, self.human_minutes)
        if any(not math.isfinite(float(item)) or item < 0 for item in values):
            raise ValueError("program costs must be finite and non-negative")

    def __add__(self, other: "ProgramCost") -> "ProgramCost":
        return ProgramCost(
            self.currency_micros + other.currency_micros,
            self.tokens + other.tokens,
            self.compute_ms + other.compute_ms,
            self.energy_joules + other.energy_joules,
            self.human_minutes + other.human_minutes,
        )

    def within(self, ceiling: "ProgramCost") -> bool:
        return all(
            getattr(self, field) <= getattr(ceiling, field)
            for field in ("currency_micros", "tokens", "compute_ms", "energy_joules", "human_minutes")
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProgramCost":
        return cls(
            int(value.get("currency_micros", 0)),
            int(value.get("tokens", 0)),
            int(value.get("compute_ms", 0)),
            float(value.get("energy_joules", 0)),
            float(value.get("human_minutes", 0)),
        )


@dataclass(frozen=True, slots=True)
class ExperimentTask:
    id: str
    description: str
    hypothesis_ids: tuple[str, ...]
    estimated_cost: ProgramCost
    maximum_cost: ProgramCost
    expected_value: str
    stop_condition: str
    max_attempts: int = 1
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        _required(self.id, "experiment id")
        _required(self.description, "experiment description")
        if not self.hypothesis_ids or not self.expected_value.strip() or not self.stop_condition.strip():
            raise ValueError("experiment hypotheses, expected value, and stop condition are required")
        if not self.estimated_cost.within(self.maximum_cost):
            raise ValueError("experiment maximum cost must cover its estimate")
        if self.max_attempts <= 0:
            raise ValueError("experiment max_attempts must be positive")


@dataclass(frozen=True, slots=True)
class EscalationPolicy:
    max_total_failures: int
    escalate_on_budget_denial: bool = True
    escalate_on_review_rejection: bool = True

    def __post_init__(self) -> None:
        if self.max_total_failures <= 0:
            raise ValueError("max_total_failures must be positive")


@dataclass(frozen=True, slots=True)
class ResearchProgramSpec:
    id: str
    question: str
    hypotheses: tuple[str, ...]
    experiments: tuple[ExperimentTask, ...]
    budget: ProgramCost
    escalation: EscalationPolicy

    def __post_init__(self) -> None:
        _required(self.id, "program id")
        _required(self.question, "program question")
        if not self.hypotheses or not self.experiments:
            raise ValueError("program requires hypotheses and experiments")
        ids = [item.id for item in self.experiments]
        if len(ids) != len(set(ids)):
            raise ValueError("experiment ids must be unique")
        known = set(self.hypotheses)
        if any(not set(item.hypothesis_ids) <= known for item in self.experiments):
            raise ValueError("experiment references an unknown hypothesis")

    @classmethod
    def from_json(cls, path: Path) -> "ResearchProgramSpec":
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, Mapping):
            raise ValueError("research program root must be an object")
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResearchProgramSpec":
        experiments = tuple(
            ExperimentTask(
                str(item["id"]),
                str(item["description"]),
                tuple(str(entry) for entry in item["hypothesis_ids"]),
                ProgramCost.from_dict(item["estimated_cost"]),
                ProgramCost.from_dict(item["maximum_cost"]),
                str(item["expected_value"]),
                str(item["stop_condition"]),
                int(item.get("max_attempts", 1)),
                bool(item.get("requires_human_review", False)),
            )
            for item in value["experiments"]
        )
        escalation = value["escalation"]
        return cls(
            str(value["id"]),
            str(value["question"]),
            tuple(str(item) for item in value["hypotheses"]),
            experiments,
            ProgramCost.from_dict(value["budget"]),
            EscalationPolicy(
                int(escalation["max_total_failures"]),
                bool(escalation.get("escalate_on_budget_denial", True)),
                bool(escalation.get("escalate_on_review_rejection", True)),
            ),
        )


class ProgramStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    PAUSED = "paused"
    COMPLETED = "completed"
    ESCALATED = "escalated"


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    success: bool
    observation: str
    evidence: tuple[str, ...]
    claims_changed: tuple[str, ...]
    failures: tuple[str, ...]
    unresolved_uncertainty: tuple[str, ...]
    best_next_question: str
    actual_cost: ProgramCost

    def __post_init__(self) -> None:
        if not self.observation.strip() or not self.best_next_question.strip():
            raise ValueError("result observation and next question are required")


@dataclass(frozen=True, slots=True)
class ProgramState:
    program_id: str
    spec_hash: str
    status: ProgramStatus
    session_number: int
    pending_experiment_ids: tuple[str, ...]
    completed_experiment_ids: tuple[str, ...]
    failed_experiment_ids: tuple[str, ...]
    attempts: tuple[tuple[str, int], ...]
    failure_count: int
    spend: ProgramCost
    observations: tuple[str, ...]
    evidence: tuple[str, ...]
    claims_changed: tuple[str, ...]
    failures: tuple[str, ...]
    unresolved_uncertainty: tuple[str, ...]
    best_next_question: str
    reason: str

    def attempt_count(self, experiment_id: str) -> int:
        return dict(self.attempts).get(experiment_id, 0)
