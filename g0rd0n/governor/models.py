"""Small immutable data model for one bounded research cycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from g0rd0n.resources.models import Cost


def require_stable_id(value: str, field: str = "id") -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"{field} must be a path-safe stable id")
    return value


@dataclass(frozen=True, slots=True)
class QuestionProposal:
    id: str
    text: str
    mission_relevance: float
    clarity: float
    falsifiability: float

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.text.strip():
            raise ValueError("question text is required")
        if any(not 0 <= value <= 1 for value in (self.mission_relevance, self.clarity, self.falsifiability)):
            raise ValueError("question scores must be in [0, 1]")

    @property
    def score(self) -> float:
        return (self.mission_relevance + self.clarity + self.falsifiability) / 3


@dataclass(frozen=True, slots=True)
class HypothesisProposal:
    id: str
    statement: str

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.statement.strip():
            raise ValueError("hypothesis statement is required")


@dataclass(frozen=True, slots=True)
class ExperimentProposal:
    id: str
    description: str
    predictions: Mapping[str, str]
    cost_units: float
    maximum_cost: Cost

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.description.strip() or self.cost_units <= 0:
            raise ValueError("experiment description and positive cost_units are required")
        if len(self.predictions) < 2 or any(not key or not value for key, value in self.predictions.items()):
            raise ValueError("experiment requires predictions for at least two hypotheses")
        object.__setattr__(self, "predictions", MappingProxyType(dict(self.predictions)))


class CycleDecision(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class CycleOutcome:
    decision: CycleDecision
    reason: str
    selected_question_id: str | None
    surviving_hypothesis_ids: tuple[str, ...]
    experiments_run: tuple[str, ...]
