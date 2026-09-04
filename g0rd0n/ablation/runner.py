"""Deterministic fixed-governor execution for harness ablations."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Sequence

from g0rd0n.research.ledger import content_hash

from .models import (
    AblationSpec,
    AblationWorkload,
    HarnessConfiguration,
    HarnessMechanism,
    IdeaOrigin,
    MECHANISM_ORDER,
    RunMetrics,
    RunResult,
    SeededDefect,
    WorkloadOutcome,
    WorkloadSplit,
)


@dataclass(frozen=True, slots=True)
class AblationMatrix:
    split: WorkloadSplit
    baseline: RunResult
    cumulative: tuple[RunResult, ...]
    components: tuple[RunResult, ...]
    human_baseline: RunResult

    @property
    def full(self) -> RunResult:
        return self.cumulative[-1]

    def without(self, mechanism: HarnessMechanism) -> RunResult:
        target = f"without:{mechanism.value}"
        return next(item for item in self.components if item.configuration.id == target)


def configurations() -> tuple[HarnessConfiguration, tuple[HarnessConfiguration, ...], tuple[HarnessConfiguration, ...], HarnessConfiguration]:
    baseline = HarnessConfiguration.fixed_baseline()
    cumulative = tuple(
        HarnessConfiguration(f"cumulative:{index + 1}", "fixed", MECHANISM_ORDER[: index + 1])
        for index in range(len(MECHANISM_ORDER))
    )
    components = tuple(
        HarnessConfiguration(
            f"without:{omitted.value}",
            "fixed",
            tuple(item for item in MECHANISM_ORDER if item is not omitted),
        )
        for omitted in MECHANISM_ORDER
    )
    human = HarnessConfiguration("human-ideas-baseline", "fixed", (), IdeaOrigin.HUMAN)
    return baseline, cumulative, components, human


def run_matrix(
    spec: AblationSpec,
    workloads: Sequence[AblationWorkload],
) -> AblationMatrix:
    baseline, cumulative, components, human = configurations()
    results = tuple(run_configuration(spec, workloads, item) for item in cumulative)
    component_results = tuple(run_configuration(spec, workloads, item) for item in components)
    baseline_result = run_configuration(spec, workloads, baseline)
    human_result = run_configuration(spec, workloads, human)
    return AblationMatrix(baseline_result.split, baseline_result, results, component_results, human_result)


def run_configuration(
    spec: AblationSpec,
    workloads: Sequence[AblationWorkload],
    configuration: HarnessConfiguration,
) -> RunResult:
    workload_tuple = tuple(workloads)
    if not workload_tuple:
        raise ValueError("ablation run requires workloads")
    splits = {item.split for item in workload_tuple}
    if len(splits) != 1:
        raise ValueError("one run cannot mix selection and held-out workloads")
    outcomes = tuple(_run_one(spec, item, configuration) for item in workload_tuple)
    valid = [item for item in outcomes if item.discovery_valid]
    metrics = RunMetrics(
        len(outcomes),
        len(valid) / len(outcomes),
        statistics.mean(item.transfer_score for item in valid) if valid else 0.0,
        sum(item.integrity_violations for item in outcomes),
        sum(item.duplicated_work for item in outcomes),
        sum(item.human_review_minutes for item in outcomes),
        sum(item.wall_time_ms for item in outcomes),
        sum(item.total_cost_units for item in outcomes),
        sum(spec.profile(item).complexity_points for item in configuration.mechanisms),
        sum(item.budget_exceeded for item in outcomes),
    )
    budget_hash = content_hash(
        [
            {
                "id": item.id,
                "cost_units": item.budget.cost_units,
                "wall_time_ms": item.budget.wall_time_ms,
                "human_minutes": item.budget.human_minutes,
            }
            for item in workload_tuple
        ]
    )
    return RunResult(
        configuration,
        next(iter(splits)),
        tuple(item.id for item in workload_tuple),
        budget_hash,
        outcomes,
        metrics,
    )

def _run_one(
    spec: AblationSpec,
    workload: AblationWorkload,
    configuration: HarnessConfiguration,
) -> WorkloadOutcome:
    if configuration.idea_origin is IdeaOrigin.HUMAN:
        idea = workload.human_idea
        valid = bool(idea and idea.valid)
        transfer = idea.transfer_score if valid and idea else 0.0
        cost = workload.base_cost_units + (idea.cost_units if idea else 0.0)
        wall = workload.base_wall_time_ms + (idea.wall_time_ms if idea else 0)
        human = workload.base_human_minutes + (idea.human_minutes if idea else 0.0)
        return _bounded_outcome(workload, valid, transfer, 0, 0, human, wall, cost)

    enabled = set(configuration.mechanisms)
    valid = workload.has_valid_candidate
    violations = 0
    duplicated = 0
    defects = workload.defects

    if SeededDefect.PROTOCOL_DRIFT in defects and HarnessMechanism.FROZEN_PROTOCOLS not in enabled:
        valid = False
        violations += 1
    if (
        SeededDefect.EVALUATION_LEAKAGE in defects
        or SeededDefect.CAPABILITY_REGRESSION in defects
    ):
        valid = False
        if HarnessMechanism.EVALUATION_ISOLATION not in enabled:
            violations += 1
    if SeededDefect.CONTEXT_CONTAMINATION in defects and HarnessMechanism.FRESH_SESSIONS not in enabled:
        valid = False
    if SeededDefect.INTEGRITY_VIOLATION in defects:
        valid = False
        if HarnessMechanism.INTEGRITY_MONITORING not in enabled:
            violations += 1
    if SeededDefect.DUPLICATED_WORK in defects:
        duplicated = int(HarnessMechanism.SHARED_SURVEY_FORUM not in enabled)

    base_cost = workload.base_cost_units
    if SeededDefect.DUPLICATED_WORK in defects and HarnessMechanism.SHARED_SURVEY_FORUM in enabled:
        base_cost *= 0.2
    cost = base_cost + sum(spec.profile(item).cost_units for item in enabled)
    wall = workload.base_wall_time_ms + sum(spec.profile(item).wall_time_ms for item in enabled)
    human = workload.base_human_minutes + sum(spec.profile(item).human_minutes for item in enabled)
    return _bounded_outcome(
        workload,
        valid,
        workload.transfer_score if valid else 0.0,
        violations,
        duplicated,
        human,
        wall,
        cost,
    )


def _bounded_outcome(
    workload: AblationWorkload,
    valid: bool,
    transfer: float,
    violations: int,
    duplicated: int,
    human: float,
    wall: int,
    cost: float,
) -> WorkloadOutcome:
    exceeded = (
        cost > workload.budget.cost_units
        or wall > workload.budget.wall_time_ms
        or human > workload.budget.human_minutes
    )
    return WorkloadOutcome(
        workload.id,
        valid and not exceeded,
        transfer if not exceeded else 0.0,
        violations,
        duplicated,
        human,
        wall,
        cost,
        exceeded,
    )
