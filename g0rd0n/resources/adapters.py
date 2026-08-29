"""Adapter APIs for models, programs, humans, and other invocable resources."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from .models import Capability, Cost


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise InvocationCancelled("invocation was cancelled")


class InvocationCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterResult:
    output: Mapping[str, Any]
    actual_cost: Cost | None = None


@runtime_checkable
class ResourceAdapter(Protocol):
    def invoke(
        self,
        capability: Capability,
        payload: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> AdapterResult: ...


Backend = Callable[[Mapping[str, Any], CancellationToken], AdapterResult]


@dataclass(frozen=True, slots=True)
class ModelResourceAdapter:
    complete: Backend

    def invoke(self, capability: Capability, payload: Mapping[str, Any], cancellation: CancellationToken) -> AdapterResult:
        return self.complete(payload, cancellation)


@dataclass(frozen=True, slots=True)
class ProgramResourceAdapter:
    run: Backend

    def invoke(self, capability: Capability, payload: Mapping[str, Any], cancellation: CancellationToken) -> AdapterResult:
        return self.run(payload, cancellation)


@dataclass(frozen=True, slots=True)
class HumanResourceAdapter:
    request: Backend

    def invoke(self, capability: Capability, payload: Mapping[str, Any], cancellation: CancellationToken) -> AdapterResult:
        return self.request(payload, cancellation)
