"""Immutable method specifications, approvals, receipts, and journal events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _texts(value: Any, field: str, *, minimum: int = 1) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be an array")
    items = tuple(_text(item, field) for item in value)
    if len(items) < minimum:
        raise ValueError(f"{field} requires at least {minimum} item(s)")
    return items


def _timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


_PROTOCOL_FIELDS = frozenset(
    {
        "id",
        "title",
        "abstract",
        "motivation",
        "related_work",
        "mechanism",
        "data_construction",
        "configuration",
        "assumptions",
        "expected_result",
        "falsifiers",
        "compliance_declarations",
    }
)
_RESULT_REFERENCE_FIELDS = frozenset(
    {"result", "results", "result_id", "observation", "observation_id", "execution_id", "receipt_id", "actual_score"}
)


def _reject_result_references(value: Any, path: str = "configuration") -> None:
    if isinstance(value, Mapping):
        forbidden = set(value) & _RESULT_REFERENCE_FIELDS
        if forbidden:
            raise ValueError(f"{path} contains result-bearing fields: {sorted(forbidden)}")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            _reject_result_references(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_result_references(item, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{path} must contain JSON-compatible values")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class MethodProtocol:
    id: str
    title: str
    abstract: str
    motivation: str
    related_work: tuple[str, ...]
    mechanism: str
    data_construction: str
    configuration: Mapping[str, Any]
    assumptions: tuple[str, ...]
    expected_result: str
    falsifiers: tuple[str, ...]
    compliance_declarations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("id", "title", "abstract", "motivation", "mechanism", "data_construction", "expected_result"):
            value = getattr(self, field)
            if _text(value, field) != value:
                raise ValueError(f"{field} must not have surrounding whitespace")
        for field in ("related_work", "assumptions", "falsifiers", "compliance_declarations"):
            values = getattr(self, field)
            if not values or any(not item.strip() or item != item.strip() for item in values):
                raise ValueError(f"{field} requires non-empty canonical text items")
        if not isinstance(self.configuration, Mapping) or not self.configuration:
            raise ValueError("configuration must be a non-empty object")
        _reject_result_references(self.configuration)
        object.__setattr__(self, "configuration", _freeze_json(self.configuration))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "motivation": self.motivation,
            "related_work": list(self.related_work),
            "mechanism": self.mechanism,
            "data_construction": self.data_construction,
            "configuration": _thaw_json(self.configuration),
            "assumptions": list(self.assumptions),
            "expected_result": self.expected_result,
            "falsifiers": list(self.falsifiers),
            "compliance_declarations": list(self.compliance_declarations),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MethodProtocol":
        unknown = set(value) - _PROTOCOL_FIELDS
        if unknown:
            raise ValueError(f"unknown or result-bearing protocol fields: {sorted(unknown)}")
        missing = _PROTOCOL_FIELDS - set(value)
        if missing:
            raise ValueError(f"missing protocol fields: {sorted(missing)}")
        configuration = value["configuration"]
        if not isinstance(configuration, Mapping):
            raise ValueError("configuration must be an object")
        return cls(
            _text(value["id"], "id"),
            _text(value["title"], "title"),
            _text(value["abstract"], "abstract"),
            _text(value["motivation"], "motivation"),
            _texts(value["related_work"], "related_work"),
            _text(value["mechanism"], "mechanism"),
            _text(value["data_construction"], "data_construction"),
            dict(configuration),
            _texts(value["assumptions"], "assumptions"),
            _text(value["expected_result"], "expected_result"),
            _texts(value["falsifiers"], "falsifiers"),
            _texts(value["compliance_declarations"], "compliance_declarations"),
        )


@dataclass(frozen=True, slots=True)
class FrozenMethod:
    protocol: MethodProtocol
    protocol_hash: str
    frozen_at: datetime
    frozen_by: str


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    id: str
    method_id: str
    reviewer: str
    policy_version: str
    protocol_hash: str
    code_hash: str
    approved_at: datetime


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    id: str
    method_id: str
    approval_id: str
    protocol_hash: str
    code_hash: str
    result_artifact_hash: str
    status: ExecutionStatus
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class SupersessionRecord:
    prior_method_id: str
    replacement_method_id: str
    actor: str
    reason: str
    superseded_at: datetime


class MethodEventKind(StrEnum):
    FROZEN = "frozen"
    APPROVED = "approved"
    EXECUTION_RECORDED = "execution_recorded"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class MethodEvent:
    sequence: int
    kind: MethodEventKind
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str


def frozen_from_dict(value: Mapping[str, Any]) -> FrozenMethod:
    return FrozenMethod(
        MethodProtocol.from_dict(value["protocol"]),
        _text(value.get("protocol_hash"), "protocol_hash"),
        _timestamp(value.get("frozen_at"), "frozen_at"),
        _text(value.get("frozen_by"), "frozen_by"),
    )


def approval_from_dict(value: Mapping[str, Any]) -> ApprovalRecord:
    return ApprovalRecord(
        *(_text(value.get(field), field) for field in ("id", "method_id", "reviewer", "policy_version", "protocol_hash", "code_hash")),
        _timestamp(value.get("approved_at"), "approved_at"),
    )


def receipt_from_dict(value: Mapping[str, Any]) -> ExecutionReceipt:
    return ExecutionReceipt(
        *(_text(value.get(field), field) for field in ("id", "method_id", "approval_id", "protocol_hash", "code_hash", "result_artifact_hash")),
        ExecutionStatus(value["status"]),
        _timestamp(value.get("recorded_at"), "recorded_at"),
    )


def supersession_from_dict(value: Mapping[str, Any]) -> SupersessionRecord:
    return SupersessionRecord(
        *(_text(value.get(field), field) for field in ("prior_method_id", "replacement_method_id", "actor", "reason")),
        _timestamp(value.get("superseded_at"), "superseded_at"),
    )
