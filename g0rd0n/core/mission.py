"""Machine-readable, falsifiable mission contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .vocabulary import BaselineFamily, ScientificDimension, VerificationMode


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class BaselineSpec:
    id: str
    family: BaselineFamily
    version_policy: str
    reproducibility_requirements: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaselineSpec":
        requirements = tuple(data.get("reproducibility_requirements", ()))
        if not requirements or any(not str(item).strip() for item in requirements):
            raise ValueError("baseline reproducibility_requirements cannot be empty")
        return cls(
            id=_required_text(data.get("id"), "baseline.id"),
            family=BaselineFamily(data.get("family")),
            version_policy=_required_text(data.get("version_policy"), "baseline.version_policy"),
            reproducibility_requirements=requirements,
        )


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    description: str
    dimension: ScientificDimension
    verification: VerificationMode
    indicator: str
    threshold: str
    falsifier: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Criterion":
        return cls(
            id=_required_text(data.get("id"), "criterion.id"),
            description=_required_text(data.get("description"), "criterion.description"),
            dimension=ScientificDimension(data.get("dimension")),
            verification=VerificationMode(data.get("verification")),
            indicator=_required_text(data.get("indicator"), "criterion.indicator"),
            threshold=_required_text(data.get("threshold"), "criterion.threshold"),
            falsifier=_required_text(data.get("falsifier"), "criterion.falsifier"),
        )


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    term: ScientificDimension
    definition: str
    excludes: tuple[ScientificDimension, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlossaryEntry":
        term = ScientificDimension(data.get("term"))
        excludes = tuple(ScientificDimension(item) for item in data.get("excludes", ()))
        if term in excludes:
            raise ValueError(f"glossary term {term} cannot exclude itself")
        return cls(term, _required_text(data.get("definition"), "glossary.definition"), excludes)


@dataclass(frozen=True, slots=True)
class MissionSpec:
    id: str
    question: str
    interpretation: str
    target_continuous_power_watts: float
    baselines: tuple[BaselineSpec, ...]
    criteria: tuple[Criterion, ...]
    glossary: tuple[GlossaryEntry, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionSpec":
        try:
            power = float(data.get("target_continuous_power_watts"))
        except (TypeError, ValueError) as error:
            raise ValueError("target_continuous_power_watts must be numeric") from error
        if power <= 0:
            raise ValueError("target_continuous_power_watts must be positive")
        spec = cls(
            id=_required_text(data.get("id"), "id"),
            question=_required_text(data.get("question"), "question"),
            interpretation=_required_text(data.get("interpretation"), "interpretation"),
            target_continuous_power_watts=power,
            baselines=tuple(BaselineSpec.from_dict(item) for item in data.get("baselines", ())),
            criteria=tuple(Criterion.from_dict(item) for item in data.get("criteria", ())),
            glossary=tuple(GlossaryEntry.from_dict(item) for item in data.get("glossary", ())),
        )
        spec.validate()
        return spec

    @classmethod
    def from_json(cls, path: Path) -> "MissionSpec":
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError("MissionSpec root must be an object")
        return cls.from_dict(data)

    def validate(self) -> None:
        if self.interpretation != "resource_bounded_separation":
            raise ValueError("the default interpretation must be resource_bounded_separation")
        for name, values in (("baseline", self.baselines), ("criterion", self.criteria)):
            if not values:
                raise ValueError(f"at least one {name} is required")
            ids = [value.id.casefold() for value in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"contradictory duplicate {name} ids are not allowed")
        terms = [entry.term for entry in self.glossary]
        if set(terms) != set(ScientificDimension) or len(terms) != len(set(terms)):
            raise ValueError("glossary must define every scientific dimension exactly once")
