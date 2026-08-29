"""Immutable resource, capability, invocation, and cost models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class ResourceKind(StrEnum):
    HUMAN = "human"
    MODEL = "model"
    PROGRAM = "program"
    THEOREM_PROVER = "theorem_prover"
    SIMULATOR = "simulator"
    BENCHMARK = "benchmark"
    KNOWLEDGE_SOURCE = "knowledge_source"
    EXTERNAL_CHANNEL = "external_channel"
    HARDWARE_TARGET = "hardware_target"


class Permission(StrEnum):
    READ_LOCAL = "read_local"
    WRITE_LOCAL = "write_local"
    EXECUTE = "execute"
    NETWORK = "network"
    EXTERNAL_WRITE = "external_write"
    HUMAN_ATTENTION = "human_attention"


class InvocationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DENIED = "denied"
    RATE_LIMITED = "rate_limited"


_TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "object": lambda value: isinstance(value, Mapping),
    "array": lambda value: isinstance(value, (list, tuple)),
}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    type: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("field name is required")
        if self.type not in _TYPE_CHECKS:
            raise ValueError(f"unsupported field type: {self.type}")


@dataclass(frozen=True, slots=True)
class Cost:
    currency_micros: int = 0
    tokens: int = 0
    calls: int = 0
    wall_time_ms: int = 0

    def __post_init__(self) -> None:
        if min(self.currency_micros, self.tokens, self.calls, self.wall_time_ms) < 0:
            raise ValueError("cost values cannot be negative")

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(
            self.currency_micros + other.currency_micros,
            self.tokens + other.tokens,
            self.calls + other.calls,
            self.wall_time_ms + other.wall_time_ms,
        )


@dataclass(frozen=True, slots=True)
class CostModel:
    per_call: Cost = field(default_factory=lambda: Cost(calls=1))
    description: str = "fixed per-call estimate"


@dataclass(frozen=True, slots=True)
class ContextLimits:
    max_input_bytes: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        if self.max_input_bytes <= 0 or self.max_output_bytes <= 0:
            raise ValueError("context limits must be positive")


@dataclass(frozen=True, slots=True)
class RateLimit:
    calls: int
    period_seconds: float

    def __post_init__(self) -> None:
        if self.calls <= 0 or self.period_seconds <= 0:
            raise ValueError("rate-limit values must be positive")


@dataclass(frozen=True, slots=True)
class LatencyModel:
    expected_ms: int
    maximum_ms: int
    description: str = "declared estimate"

    def __post_init__(self) -> None:
        if self.expected_ms < 0 or self.maximum_ms <= 0:
            raise ValueError("latency values must be non-negative with a positive maximum")
        if self.expected_ms > self.maximum_ms:
            raise ValueError("expected latency cannot exceed maximum latency")


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    description: str
    inputs: tuple[FieldSpec, ...]
    outputs: tuple[FieldSpec, ...]
    required_permissions: frozenset[Permission] = frozenset()
    default_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.description.strip():
            raise ValueError("capability id and description are required")
        if self.default_timeout_seconds <= 0:
            raise ValueError("capability timeout must be positive")
        for fields, label in ((self.inputs, "input"), (self.outputs, "output")):
            names = [item.name for item in fields]
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {label} field")

    def validate_input(self, payload: Mapping[str, Any]) -> None:
        self._validate(payload, self.inputs, "input")

    def validate_output(self, payload: Mapping[str, Any]) -> None:
        self._validate(payload, self.outputs, "output")

    @staticmethod
    def _validate(payload: Mapping[str, Any], fields: tuple[FieldSpec, ...], label: str) -> None:
        specs = {item.name: item for item in fields}
        unknown = set(payload) - set(specs)
        if unknown:
            raise ValueError(f"unknown {label} fields: {sorted(unknown)}")
        missing = {name for name, spec in specs.items() if spec.required and name not in payload}
        if missing:
            raise ValueError(f"missing {label} fields: {sorted(missing)}")
        for name, value in payload.items():
            if not _TYPE_CHECKS[specs[name].type](value):
                raise ValueError(f"{label} field {name!r} must be {specs[name].type}")


@dataclass(frozen=True, slots=True)
class Resource:
    id: str
    kind: ResourceKind
    capabilities: tuple[Capability, ...]
    cost_model: CostModel
    reliability: float
    rate_limit: RateLimit
    latency_model: LatencyModel
    context_limits: ContextLimits
    permissions: frozenset[Permission]
    provenance: str
    context_description: str = ""
    historical_performance: str = "no observations"

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.provenance.strip():
            raise ValueError("resource id and provenance are required")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("resource reliability must be in [0, 1]")
        if not self.capabilities:
            raise ValueError("resource requires at least one capability")
        ids = [capability.id for capability in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("resource capability ids must be unique")
        for capability in self.capabilities:
            if not capability.required_permissions <= self.permissions:
                raise ValueError("capability requires permission not declared by resource")

    def capability(self, capability_id: str) -> Capability:
        for capability in self.capabilities:
            if capability.id == capability_id:
                return capability
        raise KeyError(capability_id)


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    resource_id: str
    capability_id: str
    payload: Mapping[str, Any]
    granted_permissions: frozenset[Permission]
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not self.resource_id.strip() or not self.capability_id.strip():
            raise ValueError("resource_id and capability_id are required")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class InvocationResult:
    invocation_id: str
    resource_id: str
    capability_id: str
    status: InvocationStatus
    output: Mapping[str, Any] | None
    error: str | None
    estimated_cost: Cost
    actual_cost: Cost
    started_at: float
    finished_at: float

    def __post_init__(self) -> None:
        if self.output is not None:
            object.__setattr__(self, "output", MappingProxyType(dict(self.output)))


def encoded_size(value: Mapping[str, Any]) -> int:
    try:
        return len(
            json.dumps(
                dict(value),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as error:
        raise ValueError("invocation payload must be finite JSON data") from error
