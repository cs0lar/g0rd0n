"""Minimal provenance-bearing schema shared by all research objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ResearchObjectKind(StrEnum):
    QUESTION = "question"
    DEFINITION = "definition"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"
    PREDICTION = "prediction"
    EXPERIMENT = "experiment"
    OBSERVATION = "observation"
    RESULT = "result"
    CLAIM = "claim"
    COUNTEREXAMPLE = "counterexample"
    PROOF_ATTEMPT = "proof_attempt"
    PROOF = "proof"
    FAILURE = "failure"
    DECISION = "decision"
    RESEARCH_PROGRAM = "research_program"


@dataclass(frozen=True, slots=True)
class Provenance:
    actor: str
    created_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class ResearchObject:
    id: str
    kind: ResearchObjectKind
    title: str
    content: dict[str, Any]
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise ValueError("research object id and title are required")
        if self.provenance.created_at.tzinfo is None:
            raise ValueError("provenance timestamp must include a timezone")
        if not self.provenance.actor.strip() or not self.provenance.source.strip():
            raise ValueError("provenance actor and source are required")
