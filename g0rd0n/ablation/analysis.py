"""Paired estimates, selection-only adoption, held-out evaluation, and sensitivity."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, replace
from typing import Callable

from .models import (
    AblationSpec,
    AdoptionPlan,
    AdoptionStatus,
    DecisionThresholds,
    HarnessConfiguration,
    HarnessMechanism,
    MECHANISM_ORDER,
    MechanismDecision,
    PairedEstimate,
    RunResult,
    SensitivityResult,
    WorkloadOutcome,
    WorkloadSplit,
)
from .runner import AblationMatrix, run_configuration, run_matrix


@dataclass(frozen=True, slots=True)
class HeldOutEvaluation:
    baseline: RunResult
    adopted: RunResult
    progress_per_cost: PairedEstimate
    transfer: PairedEstimate
    component_evidence: tuple[MechanismDecision, ...]


@dataclass(frozen=True, slots=True)
class AblationStudy:
    selection: AblationMatrix
    adoption: AdoptionPlan
    held_out: HeldOutEvaluation
    sensitivity: tuple[SensitivityResult, ...]

    @property
    def passes_merge_gate(self) -> bool:
        defaults = set(self.adoption.default_configuration.mechanisms)
        held_out_supported = {
            item.mechanism for item in self.held_out.component_evidence
            if item.status is AdoptionStatus.ADOPT
        }
        return (
            defaults <= held_out_supported
            and self.held_out.progress_per_cost.confidence_interval_95[0] > 0
            and self.held_out.adopted.metrics.budget_failures == 0
        )


def paired_estimate(
    candidate: RunResult,
    reference: RunResult,
    *,
    metric: str,
    value: Callable[[WorkloadOutcome], float],
    bootstrap_samples: int,
    seed: int,
) -> PairedEstimate:
    _require_paired(candidate, reference)
    differences = [value(left) - value(right) for left, right in zip(candidate.outcomes, reference.outcomes)]
    observed = statistics.mean(differences)
    rng = random.Random(seed)
    bootstrap = sorted(
        statistics.mean(rng.choice(differences) for _ in differences)
        for _ in range(bootstrap_samples)
    )
    lower = bootstrap[max(0, int(0.025 * bootstrap_samples))]
    upper = bootstrap[min(bootstrap_samples - 1, int(0.975 * bootstrap_samples))]
    return PairedEstimate(metric, len(differences), observed, (lower, upper))


def select_adoption(
    matrix: AblationMatrix,
    spec: AblationSpec,
    *,
    thresholds=None,
    bootstrap_seed: int | None = None,
) -> AdoptionPlan:
    if matrix.split is not WorkloadSplit.SELECTION:
        raise ValueError("held-out workloads cannot be used for mechanism selection")
    active_thresholds = thresholds or spec.thresholds
    seed = spec.bootstrap_seed if bootstrap_seed is None else bootstrap_seed
    decisions = tuple(
        _mechanism_decision(matrix, spec, mechanism, active_thresholds, seed)
        for mechanism in MECHANISM_ORDER
    )
    adopted = tuple(item.mechanism for item in decisions if item.status is AdoptionStatus.ADOPT)
    return AdoptionPlan(
        decisions,
        HarnessConfiguration("supported-default", "fixed", adopted),
    )


def evaluate_held_out(plan: AdoptionPlan, spec: AblationSpec) -> HeldOutEvaluation:
    workloads = spec.for_split(WorkloadSplit.HELD_OUT)
    matrix = run_matrix(spec, workloads)
    baseline = matrix.baseline
    adopted = run_configuration(spec, workloads, plan.default_configuration)
    return HeldOutEvaluation(
        baseline,
        adopted,
        paired_estimate(
            adopted, baseline, metric="held_out_valid_progress_per_cost",
            value=lambda item: item.valid_progress_per_cost,
            bootstrap_samples=spec.bootstrap_samples, seed=spec.bootstrap_seed + 100,
        ),
        paired_estimate(
            adopted, baseline, metric="held_out_transfer",
            value=lambda item: item.transfer_score if item.discovery_valid else 0.0,
            bootstrap_samples=spec.bootstrap_samples, seed=spec.bootstrap_seed + 101,
        ),
        tuple(
            _mechanism_decision(matrix, spec, mechanism, spec.thresholds, spec.bootstrap_seed + 200)
            for mechanism in plan.default_configuration.mechanisms
        ),
    )


def sensitivity_analysis(matrix: AblationMatrix, spec: AblationSpec) -> tuple[SensitivityResult, ...]:
    counts = {item: 0 for item in MECHANISM_ORDER}
    scenarios = 0
    for ratio in (1.05, 1.10, 1.20):
        for offset in (0, 1, 2):
            thresholds = replace(spec.thresholds, maximum_cost_ratio=ratio)
            plan = select_adoption(
                matrix,
                spec,
                thresholds=thresholds,
                bootstrap_seed=spec.bootstrap_seed + offset,
            )
            selected = set(plan.default_configuration.mechanisms)
            for mechanism in selected:
                counts[mechanism] += 1
            scenarios += 1
    return tuple(SensitivityResult(item, scenarios, counts[item]) for item in MECHANISM_ORDER)


def run_study(spec: AblationSpec) -> AblationStudy:
    selection = run_matrix(spec, spec.for_split(WorkloadSplit.SELECTION))
    adoption = select_adoption(selection, spec)
    held_out = evaluate_held_out(adoption, spec)
    sensitivity = sensitivity_analysis(selection, spec)
    return AblationStudy(selection, adoption, held_out, sensitivity)


def _require_paired(candidate: RunResult, reference: RunResult) -> None:
    if candidate.split is not reference.split:
        raise ValueError("paired results must use the same split")
    if candidate.workload_ids != reference.workload_ids:
        raise ValueError("paired results must use identical ordered workloads")
    if candidate.budget_hash != reference.budget_hash:
        raise ValueError("paired results must use identical declared budgets")


def _mechanism_decision(
    matrix: AblationMatrix,
    spec: AblationSpec,
    mechanism: HarnessMechanism,
    thresholds: DecisionThresholds,
    seed: int,
) -> MechanismDecision:
    full = matrix.full
    without = matrix.without(mechanism)
    progress = paired_estimate(
        full,
        without,
        metric="valid_progress_per_cost",
        value=lambda item: item.valid_progress_per_cost,
        bootstrap_samples=spec.bootstrap_samples,
        seed=seed,
    )
    transfer = paired_estimate(
        full,
        without,
        metric="valid_transfer",
        value=lambda item: item.transfer_score if item.discovery_valid else 0.0,
        bootstrap_samples=spec.bootstrap_samples,
        seed=seed + 1,
    )
    integrity_avoided = without.metrics.integrity_violations - full.metrics.integrity_violations
    duplicates_avoided = without.metrics.duplicated_work - full.metrics.duplicated_work
    ratio = full.metrics.total_cost_units / without.metrics.total_cost_units
    progress_supported = progress.confidence_interval_95[0] > thresholds.progress_ci_lower
    integrity_supported = (
        integrity_avoided >= thresholds.minimum_integrity_violations_avoided
        and ratio <= thresholds.maximum_cost_ratio
    )
    duplicate_supported = (
        duplicates_avoided >= thresholds.minimum_duplicates_avoided
        and ratio <= thresholds.maximum_cost_ratio
    )
    if progress_supported or integrity_supported or duplicate_supported:
        status = AdoptionStatus.ADOPT
        basis = (
            "paired progress-per-cost improvement"
            if progress_supported
            else "material integrity improvement at declared cost"
            if integrity_supported
            else "material duplicate-work reduction at declared cost"
        )
    elif progress.mean_delta > 0 or integrity_avoided > 0 or duplicates_avoided > 0:
        status = AdoptionStatus.EXPERIMENTAL
        basis = "directional benefit does not meet the pre-registered threshold"
    else:
        status = AdoptionStatus.REMOVE
        basis = "no measured benefit on registered workloads"
    return MechanismDecision(
        mechanism,
        status,
        basis,
        progress,
        transfer,
        integrity_avoided,
        duplicates_avoided,
        ratio,
        spec.profile(mechanism).complexity_points,
    )
