"""Concurrency-safe preflight reservations and budgeted resource invocation."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Mapping

from g0rd0n.resources.adapters import CancellationToken
from g0rd0n.resources.models import Cost, InvocationRequest, InvocationResult, InvocationStatus
from g0rd0n.resources.registry import ResourceRegistry

from .ledger import CostLedger, CostLedgerEvent
from .models import (
    Budget,
    BudgetMetric,
    BudgetScopeKind,
    CostCeiling,
    cost_at_least,
    cost_subtract,
)


@dataclass(frozen=True, slots=True)
class ScopeUsage:
    cost: Cost = Cost()
    actions: int = 0
    failures: int = 0


@dataclass(frozen=True, slots=True)
class PreflightDecision:
    allowed: bool
    scope_ids: tuple[str, ...]
    estimated_cost: Cost
    maximum_cost: Cost
    soft_warnings: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetedResult:
    decision: PreflightDecision
    event: CostLedgerEvent
    invocation: InvocationResult | None


class BudgetEngine:
    def __init__(
        self,
        ledger: CostLedger,
        *,
        clock=time.monotonic,
        event_clock=time.time,
        action_id_factory=None,
    ) -> None:
        self.ledger = ledger
        self._clock = clock
        self._event_clock = event_clock
        self._action_counter = len(ledger.events())
        self._action_id_factory = action_id_factory or self._next_action_id
        self._budgets: dict[str, Budget] = {}
        self._reserved: dict[str, Cost] = {}
        self._lock = threading.RLock()

    def _next_action_id(self) -> str:
        self._action_counter += 1
        return f"action-{self._action_counter:08d}"

    def register(self, budget: Budget) -> None:
        with self._lock:
            if budget.id in self._budgets:
                raise ValueError(f"budget already registered: {budget.id}")
            if budget.parent_id is not None:
                parent = self._budgets.get(budget.parent_id)
                if parent is None:
                    raise ValueError("parent budget must be registered first")
                if parent.scope_kind is not BudgetScopeKind.PROGRAM:
                    raise ValueError("session parent must be a program budget")
            self._budgets[budget.id] = budget
            self._reserved[budget.id] = Cost()

    def usage(self, scope_id: str) -> ScopeUsage:
        if scope_id not in self._budgets:
            raise KeyError(scope_id)
        cost = Cost()
        actions = 0
        failures = 0
        for event in self.ledger.events():
            if scope_id not in event.scope_ids:
                continue
            cost += event.actual_cost
            actions += 1
            if event.status in {InvocationStatus.FAILED, InvocationStatus.TIMED_OUT}:
                failures += 1
        return ScopeUsage(cost, actions, failures)

    def preflight(self, scope_id: str, estimated_cost: Cost, maximum_cost: Cost) -> PreflightDecision:
        with self._lock:
            return self._preflight_locked(scope_id, estimated_cost, maximum_cost)

    def _scope_chain(self, scope_id: str) -> tuple[str, ...]:
        budget = self._budgets.get(scope_id)
        if budget is None:
            raise KeyError(scope_id)
        return (scope_id,) if budget.parent_id is None else (scope_id, budget.parent_id)

    def _preflight_locked(
        self, scope_id: str, estimated_cost: Cost, maximum_cost: Cost
    ) -> PreflightDecision:
        scope_ids = self._scope_chain(scope_id)
        if not cost_at_least(maximum_cost, estimated_cost):
            return PreflightDecision(
                False,
                scope_ids,
                estimated_cost,
                maximum_cost,
                reason="maximum_cost must cover every estimated cost dimension",
            )
        warnings: list[str] = []
        for current_scope in scope_ids:
            budget = self._budgets[current_scope]
            usage = self.usage(current_scope)
            projected = usage.cost + self._reserved[current_scope] + maximum_cost
            exceeded = budget.hard_limit.exceeded_by(projected)
            if exceeded:
                return PreflightDecision(
                    False,
                    scope_ids,
                    estimated_cost,
                    maximum_cost,
                    tuple(warnings),
                    f"hard budget exceeded for {current_scope}: {', '.join(exceeded)}",
                )
            for condition in budget.stop_conditions:
                value = self._metric_value(condition.metric, usage, projected)
                if value >= condition.threshold:
                    return PreflightDecision(
                        False,
                        scope_ids,
                        estimated_cost,
                        maximum_cost,
                        tuple(warnings),
                        f"stop condition reached for {current_scope}: {condition.description}",
                    )
            for dimension in budget.soft_limit.exceeded_by(projected):
                warnings.append(f"soft budget exceeded for {current_scope}: {dimension}")
        return PreflightDecision(True, scope_ids, estimated_cost, maximum_cost, tuple(warnings))

    @staticmethod
    def _metric_value(metric: BudgetMetric, usage: ScopeUsage, projected: Cost) -> int:
        if metric is BudgetMetric.ACTIONS:
            return usage.actions
        if metric is BudgetMetric.FAILURES:
            return usage.failures
        return int(getattr(projected, metric.value))

    def invoke(
        self,
        registry: ResourceRegistry,
        request: InvocationRequest,
        *,
        scope_id: str,
        maximum_cost: Cost,
        cancellation: CancellationToken | None = None,
    ) -> BudgetedResult:
        with self._lock:
            action_id = self._action_id_factory()
            occurred_at = self._event_clock()
        try:
            estimate = registry.resource(request.resource_id).cost_model.per_call
        except KeyError:
            estimate = Cost()
        with self._lock:
            decision = self._preflight_locked(scope_id, estimate, maximum_cost)
            if not decision.allowed:
                event = self.ledger.append(
                    action_id=action_id,
                    scope_ids=decision.scope_ids,
                    resource_id=request.resource_id,
                    capability_id=request.capability_id,
                    status=InvocationStatus.DENIED,
                    estimated_cost=estimate,
                    maximum_cost=maximum_cost,
                    actual_cost=Cost(),
                    soft_warnings=decision.soft_warnings,
                    note=decision.reason or "budget preflight denied",
                    invocation_id=None,
                    occurred_at=occurred_at,
                )
                return BudgetedResult(decision, event, None)
            for current_scope in decision.scope_ids:
                self._reserved[current_scope] += maximum_cost

        invocation_started = self._clock()
        try:
            invocation = registry.invoke(request, cancellation=cancellation)
        except Exception as error:
            with self._lock:
                event = self.ledger.append(
                    action_id=action_id,
                    scope_ids=decision.scope_ids,
                    resource_id=request.resource_id,
                    capability_id=request.capability_id,
                    status=InvocationStatus.FAILED,
                    estimated_cost=estimate,
                    maximum_cost=maximum_cost,
                    actual_cost=estimate,
                    soft_warnings=decision.soft_warnings,
                    note=f"invocation boundary failed: {error}",
                    invocation_id=None,
                    occurred_at=occurred_at,
                )
                for current_scope in decision.scope_ids:
                    self._reserved[current_scope] = cost_subtract(
                        self._reserved[current_scope], maximum_cost
                    )
            return BudgetedResult(decision, event, None)
        elapsed_ms = max(0, math.ceil((self._clock() - invocation_started) * 1000))
        actual = Cost(
            invocation.actual_cost.currency_micros,
            invocation.actual_cost.tokens,
            invocation.actual_cost.calls,
            max(invocation.actual_cost.wall_time_ms, elapsed_ms),
        )
        maximum_exceeded = not cost_at_least(maximum_cost, actual)
        note = "invocation completed"
        if maximum_exceeded:
            note = "declared maximum cost exceeded; provider contract violation"
        with self._lock:
            event = self.ledger.append(
                action_id=action_id,
                scope_ids=decision.scope_ids,
                resource_id=request.resource_id,
                capability_id=request.capability_id,
                status=invocation.status,
                estimated_cost=estimate,
                maximum_cost=maximum_cost,
                actual_cost=actual,
                soft_warnings=decision.soft_warnings,
                note=note,
                invocation_id=invocation.invocation_id,
                occurred_at=occurred_at,
            )
            for current_scope in decision.scope_ids:
                self._reserved[current_scope] = cost_subtract(
                    self._reserved[current_scope], maximum_cost
                )
        return BudgetedResult(decision, event, invocation)

    def report(self) -> str:
        lines = ["# Budget report", "", "## Scope usage", ""]
        for scope_id in sorted(self._budgets):
            budget = self._budgets[scope_id]
            usage = self.usage(scope_id)
            lines.extend(
                [
                    f"### {scope_id}",
                    "",
                    f"- Kind: `{budget.scope_kind.value}`",
                    f"- Class: `{budget.budget_class.value}`",
                    f"- Actions: {usage.actions}",
                    f"- Failures: {usage.failures}",
                    f"- Actual: {self._format_cost(usage.cost)}",
                    "",
                ]
            )
        events = self.ledger.events()
        estimated = Cost()
        actual = Cost()
        for event in events:
            estimated += event.estimated_cost
            actual += event.actual_cost
        lines.extend(
            [
                "## Estimate accuracy",
                "",
                f"- Estimated: {self._format_cost(estimated)}",
                f"- Actual: {self._format_cost(actual)}",
                f"- Currency variance (micros): {actual.currency_micros - estimated.currency_micros}",
                f"- Token variance: {actual.tokens - estimated.tokens}",
                f"- Call variance: {actual.calls - estimated.calls}",
                f"- Wall-time variance (ms): {actual.wall_time_ms - estimated.wall_time_ms}",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_cost(cost: Cost) -> str:
        return (
            f"currency={cost.currency_micros}µ, tokens={cost.tokens}, "
            f"calls={cost.calls}, wall_time={cost.wall_time_ms}ms"
        )
