"""Hash-chained append-only ledger for action-level resource costs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from g0rd0n.research.ledger import GENESIS_HASH, IntegrityError, canonical_json, content_hash
from g0rd0n.resources.models import Cost, InvocationStatus


def _cost_dict(cost: Cost) -> dict[str, int]:
    return {
        "currency_micros": cost.currency_micros,
        "tokens": cost.tokens,
        "calls": cost.calls,
        "wall_time_ms": cost.wall_time_ms,
    }


def _cost_from(value: Mapping[str, Any]) -> Cost:
    return Cost(
        currency_micros=int(value["currency_micros"]),
        tokens=int(value["tokens"]),
        calls=int(value["calls"]),
        wall_time_ms=int(value["wall_time_ms"]),
    )


@dataclass(frozen=True, slots=True)
class CostLedgerEvent:
    sequence: int
    action_id: str
    scope_ids: tuple[str, ...]
    resource_id: str
    capability_id: str
    status: InvocationStatus
    estimated_cost: Cost
    maximum_cost: Cost
    actual_cost: Cost
    soft_warnings: tuple[str, ...]
    note: str
    invocation_id: str | None
    occurred_at: float
    previous_hash: str
    event_hash: str

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        action_id: str,
        scope_ids: tuple[str, ...],
        resource_id: str,
        capability_id: str,
        status: InvocationStatus,
        estimated_cost: Cost,
        maximum_cost: Cost,
        actual_cost: Cost,
        soft_warnings: tuple[str, ...],
        note: str,
        invocation_id: str | None,
        occurred_at: float,
        previous_hash: str,
    ) -> "CostLedgerEvent":
        unsigned = {
            "sequence": sequence,
            "action_id": action_id,
            "scope_ids": scope_ids,
            "resource_id": resource_id,
            "capability_id": capability_id,
            "status": status,
            "estimated_cost": _cost_dict(estimated_cost),
            "maximum_cost": _cost_dict(maximum_cost),
            "actual_cost": _cost_dict(actual_cost),
            "soft_warnings": soft_warnings,
            "note": note,
            "invocation_id": invocation_id,
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
        }
        return cls(event_hash=content_hash(unsigned), **{
            "sequence": sequence,
            "action_id": action_id,
            "scope_ids": scope_ids,
            "resource_id": resource_id,
            "capability_id": capability_id,
            "status": status,
            "estimated_cost": estimated_cost,
            "maximum_cost": maximum_cost,
            "actual_cost": actual_cost,
            "soft_warnings": soft_warnings,
            "note": note,
            "invocation_id": invocation_id,
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
        })

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "action_id": self.action_id,
            "scope_ids": self.scope_ids,
            "resource_id": self.resource_id,
            "capability_id": self.capability_id,
            "status": self.status,
            "estimated_cost": _cost_dict(self.estimated_cost),
            "maximum_cost": _cost_dict(self.maximum_cost),
            "actual_cost": _cost_dict(self.actual_cost),
            "soft_warnings": self.soft_warnings,
            "note": self.note,
            "invocation_id": self.invocation_id,
            "occurred_at": self.occurred_at,
            "previous_hash": self.previous_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "event_hash": self.event_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CostLedgerEvent":
        try:
            return cls(
                sequence=int(value["sequence"]),
                action_id=str(value["action_id"]),
                scope_ids=tuple(str(item) for item in value["scope_ids"]),
                resource_id=str(value["resource_id"]),
                capability_id=str(value["capability_id"]),
                status=InvocationStatus(value["status"]),
                estimated_cost=_cost_from(value["estimated_cost"]),
                maximum_cost=_cost_from(value["maximum_cost"]),
                actual_cost=_cost_from(value["actual_cost"]),
                soft_warnings=tuple(str(item) for item in value["soft_warnings"]),
                note=str(value["note"]),
                invocation_id=None if value["invocation_id"] is None else str(value["invocation_id"]),
                occurred_at=float(value["occurred_at"]),
                previous_hash=str(value["previous_hash"]),
                event_hash=str(value["event_hash"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("invalid cost ledger event") from error


class CostLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self._events = self._read_and_validate()

    def events(self) -> tuple[CostLedgerEvent, ...]:
        return tuple(self._events)

    @property
    def head_hash(self) -> str:
        return self._events[-1].event_hash if self._events else GENESIS_HASH

    def append(self, **values: Any) -> CostLedgerEvent:
        event = CostLedgerEvent.create(
            sequence=len(self._events), previous_hash=self.head_hash, **values
        )
        encoded = canonical_json(event.to_dict()) + b"\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written == 0:
                    raise OSError("cost ledger write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._events.append(event)
        return event

    def _read_and_validate(self) -> list[CostLedgerEvent]:
        events: list[CostLedgerEvent] = []
        previous_hash = GENESIS_HASH
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete cost event at line {line_number}")
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as error:
                    raise IntegrityError(f"invalid cost JSON at line {line_number}") from error
                event = CostLedgerEvent.from_dict(raw)
                if event.sequence != len(events) or event.previous_hash != previous_hash:
                    raise IntegrityError("cost ledger sequence or hash chain is broken")
                if content_hash(event.unsigned_dict()) != event.event_hash:
                    raise IntegrityError("cost event content hash does not match")
                events.append(event)
                previous_hash = event.event_hash
        return events
