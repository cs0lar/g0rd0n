"""Declarative candidate-paradigm specifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _texts(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = tuple(_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} cannot contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ComplexityClaim:
    resource: str
    bound: str
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.resource.strip() or not self.bound.strip() or not self.assumptions:
            raise ValueError("complexity claims require resource, bound, and assumptions")


@dataclass(frozen=True, slots=True)
class Falsifier:
    observation: str
    consequence: str

    def __post_init__(self) -> None:
        if not self.observation.strip() or not self.consequence.strip():
            raise ValueError("falsifiers require an observation and consequence")


@dataclass(frozen=True, slots=True)
class ParadigmSpec:
    id: str
    version: str
    runner: str
    primitives: tuple[str, ...]
    state: tuple[str, ...]
    memory: tuple[str, ...]
    learning_rule: str
    inference_rule: str
    communication: str
    adaptation: str
    hardware_assumptions: tuple[str, ...]
    complexity_claims: tuple[ComplexityClaim, ...]
    energy_hypothesis: str
    falsifiers: tuple[Falsifier, ...]

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "id"),
            (self.version, "version"),
            (self.runner, "runner"),
            (self.learning_rule, "learning_rule"),
            (self.inference_rule, "inference_rule"),
            (self.communication, "communication"),
            (self.adaptation, "adaptation"),
            (self.energy_hypothesis, "energy_hypothesis"),
        ):
            _text(value, field)
        if not self.primitives or not self.state or not self.memory:
            raise ValueError("primitives, state, and memory cannot be empty")
        if not self.hardware_assumptions or not self.complexity_claims or not self.falsifiers:
            raise ValueError("hardware assumptions, complexity claims, and falsifiers are required")

    @classmethod
    def from_json(cls, path: Path) -> "ParadigmSpec":
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, Mapping):
            raise ValueError("paradigm spec root must be an object")
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ParadigmSpec":
        claims = value.get("complexity_claims")
        falsifiers = value.get("falsifiers")
        if not isinstance(claims, list) or not isinstance(falsifiers, list):
            raise ValueError("complexity_claims and falsifiers must be lists")
        return cls(
            _text(value.get("id"), "id"),
            _text(value.get("version"), "version"),
            _text(value.get("runner"), "runner"),
            _texts(value.get("primitives"), "primitives"),
            _texts(value.get("state"), "state"),
            _texts(value.get("memory"), "memory"),
            _text(value.get("learning_rule"), "learning_rule"),
            _text(value.get("inference_rule"), "inference_rule"),
            _text(value.get("communication"), "communication"),
            _text(value.get("adaptation"), "adaptation"),
            _texts(value.get("hardware_assumptions"), "hardware_assumptions"),
            tuple(
                ComplexityClaim(
                    _text(item.get("resource"), "complexity_claim.resource"),
                    _text(item.get("bound"), "complexity_claim.bound"),
                    _texts(item.get("assumptions"), "complexity_claim.assumptions"),
                )
                for item in claims
            ),
            _text(value.get("energy_hypothesis"), "energy_hypothesis"),
            tuple(
                Falsifier(
                    _text(item.get("observation"), "falsifier.observation"),
                    _text(item.get("consequence"), "falsifier.consequence"),
                )
                for item in falsifiers
            ),
        )
