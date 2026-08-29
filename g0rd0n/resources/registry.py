"""Validated, permissioned, rate-limited resource invocation registry."""

from __future__ import annotations

import queue
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterResult, CancellationToken, InvocationCancelled, ResourceAdapter
from .models import (
    Cost,
    InvocationRequest,
    InvocationResult,
    InvocationStatus,
    Resource,
    encoded_size,
)


@dataclass(frozen=True, slots=True)
class _Outcome:
    result: AdapterResult | None = None
    error: BaseException | None = None


class ResourceRegistry:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or self._sequential_id
        self._id_counter = 0
        self._resources: dict[str, Resource] = {}
        self._adapters: dict[str, ResourceAdapter] = {}
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._history: list[InvocationResult] = []
        self._lock = threading.RLock()

    def _sequential_id(self) -> str:
        self._id_counter += 1
        return f"invocation-{self._id_counter:08d}"

    def register(self, resource: Resource, adapter: ResourceAdapter) -> None:
        with self._lock:
            if resource.id in self._resources:
                raise ValueError(f"resource already registered: {resource.id}")
            if not isinstance(adapter, ResourceAdapter):
                raise TypeError("adapter does not satisfy ResourceAdapter")
            self._resources[resource.id] = resource
            self._adapters[resource.id] = adapter

    def resource(self, resource_id: str) -> Resource:
        try:
            return self._resources[resource_id]
        except KeyError as error:
            raise KeyError(f"unknown resource: {resource_id}") from error

    def resources_for(self, capability_id: str) -> tuple[Resource, ...]:
        return tuple(
            resource
            for resource in self._resources.values()
            if any(capability.id == capability_id for capability in resource.capabilities)
        )

    def history(self) -> tuple[InvocationResult, ...]:
        with self._lock:
            return tuple(self._history)

    def invoke(
        self,
        request: InvocationRequest,
        *,
        cancellation: CancellationToken | None = None,
    ) -> InvocationResult:
        invocation_id = self._id_factory()
        started_at = self._clock()
        token = cancellation or CancellationToken()
        try:
            resource = self.resource(request.resource_id)
            capability = resource.capability(request.capability_id)
        except KeyError as error:
            return self._record(
                invocation_id, request, InvocationStatus.FAILED, None, str(error), Cost(), Cost(), started_at
            )
        estimate = resource.cost_model.per_call
        if not capability.required_permissions <= request.granted_permissions:
            missing = sorted(permission.value for permission in capability.required_permissions - request.granted_permissions)
            return self._record(
                invocation_id,
                request,
                InvocationStatus.DENIED,
                None,
                f"missing permissions: {missing}",
                estimate,
                Cost(),
                started_at,
            )
        try:
            capability.validate_input(request.payload)
            if encoded_size(request.payload) > resource.context_limits.max_input_bytes:
                raise ValueError("input exceeds resource context limit")
        except ValueError as error:
            return self._record(
                invocation_id, request, InvocationStatus.FAILED, None, str(error), estimate, Cost(), started_at
            )
        if token.cancelled:
            return self._record(
                invocation_id, request, InvocationStatus.CANCELLED, None, "cancelled before start", estimate, Cost(), started_at
            )
        if not self._reserve_rate_limit(resource, started_at):
            return self._record(
                invocation_id, request, InvocationStatus.RATE_LIMITED, None, "resource rate limit exceeded", estimate, Cost(), started_at
            )

        outcomes: queue.Queue[_Outcome] = queue.Queue(maxsize=1)

        def execute() -> None:
            try:
                outcomes.put(_Outcome(result=self._adapters[resource.id].invoke(capability, request.payload, token)))
            except BaseException as error:
                outcomes.put(_Outcome(error=error))

        worker = threading.Thread(target=execute, name=f"g0rd0n-{invocation_id}", daemon=True)
        worker.start()
        timeout = request.timeout_seconds or capability.default_timeout_seconds
        deadline = started_at + timeout
        while True:
            if token.cancelled:
                return self._record(
                    invocation_id, request, InvocationStatus.CANCELLED, None, "invocation cancelled", estimate, estimate, started_at
                )
            remaining = deadline - self._clock()
            if remaining <= 0:
                token.cancel()
                return self._record(
                    invocation_id, request, InvocationStatus.TIMED_OUT, None, "invocation timed out", estimate, estimate, started_at
                )
            try:
                outcome = outcomes.get(timeout=min(remaining, 0.01))
                break
            except queue.Empty:
                continue
        if token.cancelled:
            return self._record(
                invocation_id,
                request,
                InvocationStatus.CANCELLED,
                None,
                "invocation cancelled",
                estimate,
                estimate,
                started_at,
            )
        if outcome.error is not None:
            status = InvocationStatus.CANCELLED if isinstance(outcome.error, InvocationCancelled) else InvocationStatus.FAILED
            return self._record(
                invocation_id, request, status, None, str(outcome.error), estimate, estimate, started_at
            )
        assert outcome.result is not None
        actual = outcome.result.actual_cost or estimate
        try:
            capability.validate_output(outcome.result.output)
            if encoded_size(outcome.result.output) > resource.context_limits.max_output_bytes:
                raise ValueError("output exceeds resource context limit")
        except ValueError as error:
            return self._record(
                invocation_id, request, InvocationStatus.FAILED, None, str(error), estimate, actual, started_at
            )
        return self._record(
            invocation_id, request, InvocationStatus.SUCCEEDED, outcome.result.output, None, estimate, actual, started_at
        )

    def _reserve_rate_limit(self, resource: Resource, now: float) -> bool:
        with self._lock:
            calls = self._calls[resource.id]
            cutoff = now - resource.rate_limit.period_seconds
            while calls and calls[0] <= cutoff:
                calls.popleft()
            if len(calls) >= resource.rate_limit.calls:
                return False
            calls.append(now)
            return True

    def _record(
        self,
        invocation_id: str,
        request: InvocationRequest,
        status: InvocationStatus,
        output: dict[str, Any] | Any | None,
        error: str | None,
        estimated_cost: Cost,
        actual_cost: Cost,
        started_at: float,
    ) -> InvocationResult:
        result = InvocationResult(
            invocation_id,
            request.resource_id,
            request.capability_id,
            status,
            output,
            error,
            estimated_cost,
            actual_cost,
            started_at,
            self._clock(),
        )
        with self._lock:
            self._history.append(result)
        return result
