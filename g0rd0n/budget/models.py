"""Budget scopes, ceilings, classes, and stop conditions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from g0rd0n.resources.models import Cost


class BudgetScopeKind(StrEnum):
    PROGRAM = "program"
    SESSION = "session"


class BudgetClass(StrEnum):
    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EXCEPTIONAL = "exceptional"


class BudgetMetric(StrEnum):
    CURRENCY_MICROS = "currency_micros"
    TOKENS = "tokens"
    CALLS = "calls"
    WALL_TIME_MS = "wall_time_ms"
    ACTIONS = "actions"
    FAILURES = "failures"


@dataclass(frozen=True, slots=True)
class CostCeiling:
    currency_micros: int | None = None
    tokens: int | None = None
    calls: int | None = None
    wall_time_ms: int | None = None

    def __post_init__(self) -> None:
        values = (self.currency_micros, self.tokens, self.calls, self.wall_time_ms)
        if any(value is not None and value < 0 for value in values):
            raise ValueError("cost ceilings cannot be negative")

    def exceeded_by(self, cost: Cost) -> tuple[str, ...]:
        exceeded: list[str] = []
        for field in ("currency_micros", "tokens", "calls", "wall_time_ms"):
            ceiling = getattr(self, field)
            if ceiling is not None and getattr(cost, field) > ceiling:
                exceeded.append(field)
        return tuple(exceeded)


@dataclass(frozen=True, slots=True)
class StopCondition:
    metric: BudgetMetric
    threshold: int
    description: str

    def __post_init__(self) -> None:
        if self.threshold <= 0 or not self.description.strip():
            raise ValueError("stop condition threshold and description are required")


@dataclass(frozen=True, slots=True)
class Budget:
    id: str
    scope_kind: BudgetScopeKind
    budget_class: BudgetClass
    hard_limit: CostCeiling
    soft_limit: CostCeiling
    stop_conditions: tuple[StopCondition, ...] = ()
    parent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("budget id is required")
        if self.scope_kind is BudgetScopeKind.PROGRAM and self.parent_id is not None:
            raise ValueError("program budgets cannot have a parent")
        if self.scope_kind is BudgetScopeKind.SESSION and not self.parent_id:
            raise ValueError("session budgets require a parent program")
        for field in ("currency_micros", "tokens", "calls", "wall_time_ms"):
            soft = getattr(self.soft_limit, field)
            hard = getattr(self.hard_limit, field)
            if soft is not None and hard is not None and soft > hard:
                raise ValueError("soft limits cannot exceed hard limits")


def cost_at_least(left: Cost, right: Cost) -> bool:
    return all(
        getattr(left, field) >= getattr(right, field)
        for field in ("currency_micros", "tokens", "calls", "wall_time_ms")
    )


def cost_subtract(left: Cost, right: Cost) -> Cost:
    values = {
        field: getattr(left, field) - getattr(right, field)
        for field in ("currency_micros", "tokens", "calls", "wall_time_ms")
    }
    if min(values.values()) < 0:
        raise ValueError("cost reservation underflow")
    return Cost(**values)
