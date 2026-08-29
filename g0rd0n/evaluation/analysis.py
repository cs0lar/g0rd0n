"""Paired statistical comparisons and multi-metric Pareto fronts."""

from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from .harness import BenchmarkResult


class MetricDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    direction: MetricDirection


@dataclass(frozen=True, slots=True)
class Comparison:
    metric: str
    paired_samples: int
    baseline_mean: float
    candidate_mean: float
    mean_improvement: float
    confidence_interval_95: tuple[float, float]
    randomization_p_value: float


def paired_comparison(
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
    metric: str,
    *,
    direction: MetricDirection,
    bootstrap_samples: int = 2_000,
    seed: int = 0,
) -> Comparison:
    if (baseline.benchmark_id, baseline.benchmark_version) != (
        candidate.benchmark_id,
        candidate.benchmark_version,
    ):
        raise ValueError("paired comparisons require the same benchmark id and version")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    baseline_by_seed = {trial.seed: trial.metrics[metric] for trial in baseline.trials}
    candidate_by_seed = {trial.seed: trial.metrics[metric] for trial in candidate.trials}
    if set(baseline_by_seed) != set(candidate_by_seed) or not baseline_by_seed:
        raise ValueError("paired comparisons require identical non-empty seed sets")
    seeds = sorted(baseline_by_seed)
    sign = 1 if direction is MetricDirection.MAXIMIZE else -1
    differences = [sign * (candidate_by_seed[item] - baseline_by_seed[item]) for item in seeds]
    observed = statistics.mean(differences)
    rng = random.Random(seed)
    bootstrap = sorted(
        statistics.mean(rng.choice(differences) for _ in differences)
        for _ in range(bootstrap_samples)
    )
    lower_index = max(0, math.floor(0.025 * bootstrap_samples))
    upper_index = min(bootstrap_samples - 1, math.ceil(0.975 * bootstrap_samples) - 1)
    nonzero = [value for value in differences if value != 0]
    if len(nonzero) <= 20:
        permutations = itertools.product((-1, 1), repeat=len(nonzero))
        permuted = [abs(statistics.mean(sign_value * value for sign_value, value in zip(signs, nonzero))) for signs in permutations]
        p_value = sum(value >= abs(observed) for value in permuted) / len(permuted) if permuted else 1.0
    else:
        draws = 20_000
        p_value = sum(
            abs(statistics.mean(value * rng.choice((-1, 1)) for value in nonzero)) >= abs(observed)
            for _ in range(draws)
        ) / draws
    return Comparison(
        metric,
        len(seeds),
        statistics.mean(baseline_by_seed.values()),
        statistics.mean(candidate_by_seed.values()),
        observed,
        (bootstrap[lower_index], bootstrap[upper_index]),
        p_value,
    )


def dominates(
    left: Mapping[str, float], right: Mapping[str, float], metrics: Sequence[MetricSpec]
) -> bool:
    no_worse = True
    strictly_better = False
    for metric in metrics:
        left_value = left[metric.name]
        right_value = right[metric.name]
        if metric.direction is MetricDirection.MAXIMIZE:
            no_worse &= left_value >= right_value
            strictly_better |= left_value > right_value
        else:
            no_worse &= left_value <= right_value
            strictly_better |= left_value < right_value
    return no_worse and strictly_better


def pareto_front(
    points: Mapping[str, Mapping[str, float]], metrics: Sequence[MetricSpec]
) -> tuple[str, ...]:
    if not metrics:
        raise ValueError("Pareto analysis requires at least one metric")
    for values in points.values():
        if any(metric.name not in values for metric in metrics):
            raise ValueError("Pareto point omitted a metric")
    front = [
        name
        for name, values in points.items()
        if not any(
            other_name != name and dominates(other_values, values, metrics)
            for other_name, other_values in points.items()
        )
    ]
    return tuple(sorted(front))
