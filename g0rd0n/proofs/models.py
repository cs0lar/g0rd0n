"""Typed formal claims, obligations, bounds, and proof results."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


class BoundKind(StrEnum):
    UPPER = "upper"
    LOWER = "lower"


class BoundTemplate(StrEnum):
    CONSTANT = "constant"
    CEIL_LOG2_N_PLUS_1 = "ceil_log2_n_plus_1"


@dataclass(frozen=True, slots=True)
class ComplexityBound:
    kind: BoundKind
    resource: str
    template: BoundTemplate
    constant: int | None = None

    def __post_init__(self) -> None:
        if not self.resource.strip():
            raise ValueError("complexity bound resource is required")
        if self.template is BoundTemplate.CONSTANT:
            if self.constant is None or self.constant < 0:
                raise ValueError("constant template requires a non-negative constant")
        elif self.constant is not None:
            raise ValueError("non-constant template cannot declare a constant")

    def evaluate(self, n: int) -> int:
        if n <= 0:
            raise ValueError("bound domain requires n > 0")
        if self.template is BoundTemplate.CONSTANT:
            assert self.constant is not None
            return self.constant
        return math.ceil(math.log2(n + 1))


@dataclass(frozen=True, slots=True)
class ProofObligation:
    id: str
    statement: str

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.statement.strip():
            raise ValueError("proof obligation id and statement are required")


@dataclass(frozen=True, slots=True)
class FormalClaim:
    id: str
    task_family: str
    architecture_x: str
    architecture_y: str
    assumptions: tuple[str, ...]
    x_bound: ComplexityBound
    y_bound: ComplexityBound
    domain_min_n: int
    obligations: tuple[ProofObligation, ...]
    verifier: str

    def __post_init__(self) -> None:
        for value in (self.id, self.task_family, self.architecture_x, self.architecture_y, self.verifier):
            if not value.strip():
                raise ValueError("formal claim text fields are required")
        if not self.assumptions or self.domain_min_n <= 0 or not self.obligations:
            raise ValueError("claim assumptions, positive domain, and obligations are required")
        if self.x_bound.kind is not BoundKind.UPPER or self.y_bound.kind is not BoundKind.LOWER:
            raise ValueError("separation requires an X upper bound and Y lower bound")
        if self.x_bound.resource != self.y_bound.resource:
            raise ValueError("separation bounds must concern the same resource")
        ids = [item.id for item in self.obligations]
        if len(ids) != len(set(ids)):
            raise ValueError("proof obligation ids must be unique")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FormalClaim":
        def bound(item: Mapping[str, Any]) -> ComplexityBound:
            return ComplexityBound(
                BoundKind(item["kind"]),
                _text(item.get("resource"), "bound.resource"),
                BoundTemplate(item["template"]),
                None if item.get("constant") is None else int(item["constant"]),
            )

        return cls(
            _text(value.get("id"), "id"),
            _text(value.get("task_family"), "task_family"),
            _text(value.get("architecture_x"), "architecture_x"),
            _text(value.get("architecture_y"), "architecture_y"),
            tuple(_text(item, "assumption") for item in value["assumptions"]),
            bound(value["x_bound"]),
            bound(value["y_bound"]),
            int(value["domain_min_n"]),
            tuple(ProofObligation(_text(item.get("id"), "obligation.id"), _text(item.get("statement"), "obligation.statement")) for item in value["obligations"]),
            _text(value.get("verifier"), "verifier"),
        )


@dataclass(frozen=True, slots=True)
class ProofBundle:
    claim: FormalClaim
    certificate: Mapping[str, Any]

    @classmethod
    def from_json(cls, path: Path) -> "ProofBundle":
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, Mapping) or not isinstance(value.get("claim"), Mapping) or not isinstance(value.get("certificate"), Mapping):
            raise ValueError("proof bundle requires claim and certificate objects")
        return cls(FormalClaim.from_dict(value["claim"]), dict(value["certificate"]))


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    verifier: str
    discharged_obligations: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Counterexample:
    n: int
    x_cost: int
    y_cost: int
    reason: str
