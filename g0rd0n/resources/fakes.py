"""Deterministic fake resources for unit tests and synthetic research worlds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .adapters import AdapterResult, CancellationToken
from .models import Capability, Cost


@dataclass(slots=True)
class DeterministicFakeAdapter:
    responses: Mapping[str, AdapterResult]
    invocations: list[tuple[str, Mapping[str, Any]]] = field(default_factory=list)

    def invoke(
        self,
        capability: Capability,
        payload: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> AdapterResult:
        cancellation.raise_if_cancelled()
        self.invocations.append((capability.id, dict(payload)))
        try:
            return self.responses[capability.id]
        except KeyError as error:
            raise RuntimeError(f"no fake response for {capability.id}") from error


def fixed_result(output: Mapping[str, Any], *, calls: int = 1) -> AdapterResult:
    return AdapterResult(dict(output), Cost(calls=calls))
