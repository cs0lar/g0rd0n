"""Adaptive resource topology with checkpointed, evidence-based allocation."""

from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol, Sequence

from .models import require_stable_id


@dataclass(frozen=True, slots=True)
class ResourceStrategyProfile:
    id: str
    capabilities: frozenset[str]
    expected_cost: float
    spawn_cost: float
    prior_progress: float

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.capabilities or self.expected_cost <= 0 or self.spawn_cost < 0:
            raise ValueError("resource profile requires capabilities and valid costs")
        if not 0 <= self.prior_progress <= 1:
            raise ValueError("prior progress must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class AllocationStrategy:
    id: str
    objective: str = "expected research progress / expected total resource cost"
    exploration_strength: float = 0.15
    spawn_amortization_tasks: int = 5
    retirement_min_observations: int = 3
    retirement_utility_threshold: float = 0.1

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.objective.strip() or self.exploration_strength < 0:
            raise ValueError("strategy objective and non-negative exploration are required")
        if self.spawn_amortization_tasks <= 0 or self.retirement_min_observations <= 0:
            raise ValueError("strategy horizons must be positive")
        if self.retirement_utility_threshold < 0:
            raise ValueError("retirement threshold cannot be negative")


@dataclass(frozen=True, slots=True)
class Workload:
    id: str
    family: str
    required_capability: str

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.family.strip() or not self.required_capability.strip():
            raise ValueError("workload family and capability are required")


@dataclass(frozen=True, slots=True)
class PerformanceObservation:
    resource_id: str
    workload_family: str
    progress: float
    total_cost: float
    succeeded: bool

    def __post_init__(self) -> None:
        require_stable_id(self.resource_id, "resource_id")
        if not self.workload_family.strip() or not math.isfinite(self.progress) or not 0 <= self.progress <= 1:
            raise ValueError("observation requires a family and progress in [0, 1]")
        if not math.isfinite(self.total_cost) or self.total_cost <= 0:
            raise ValueError("observed total cost must be finite and positive")

    @property
    def utility(self) -> float:
        return (self.progress if self.succeeded else 0.0) / self.total_cost


class TopologyActionKind(StrEnum):
    SPAWN = "spawn"
    REUSE = "reuse"
    RETIRE = "retire"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class TopologyAction:
    kind: TopologyActionKind
    resource_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class Allocation:
    workload_id: str
    resource_id: str
    expected_utility: float
    spawned: bool
    activation_cost: float


@dataclass(frozen=True, slots=True)
class StrategyCheckpoint:
    strategy: AllocationStrategy
    active_resource_ids: tuple[str, ...]
    observations: tuple[PerformanceObservation, ...]
    actions: tuple[TopologyAction, ...]


class AllocationPolicy(Protocol):
    def allocate(self, workload: Workload) -> Allocation: ...

    def record(self, observation: PerformanceObservation) -> None: ...


class AdaptiveResourceTopology:
    def __init__(
        self,
        profiles: Sequence[ResourceStrategyProfile],
        strategy: AllocationStrategy,
        *,
        initially_active: Sequence[str] = (),
    ) -> None:
        self.profiles = {profile.id: profile for profile in profiles}
        if not self.profiles or len(self.profiles) != len(tuple(profiles)):
            raise ValueError("resource profiles must be non-empty and unique")
        unknown = set(initially_active) - set(self.profiles)
        if unknown:
            raise ValueError(f"unknown initially active resources: {sorted(unknown)}")
        self.strategy = strategy
        self._active = set(initially_active)
        self._observations: list[PerformanceObservation] = []
        self._actions: list[TopologyAction] = []

    @property
    def active_resource_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    @property
    def observations(self) -> tuple[PerformanceObservation, ...]:
        return tuple(self._observations)

    @property
    def actions(self) -> tuple[TopologyAction, ...]:
        return tuple(self._actions)

    def allocate(self, workload: Workload) -> Allocation:
        eligible = [profile for profile in self.profiles.values() if workload.required_capability in profile.capabilities]
        if not eligible:
            raise ValueError(f"no resource provides capability {workload.required_capability}")
        ranked = sorted(
            ((self._expected_utility(profile, workload.family), profile) for profile in eligible),
            key=lambda item: (-item[0], item[1].id),
        )
        utility, selected = ranked[0]
        spawned = selected.id not in self._active
        self._active.add(selected.id)
        self._actions.append(
            TopologyAction(
                TopologyActionKind.SPAWN if spawned else TopologyActionKind.REUSE,
                selected.id,
                f"selected for {workload.family} at expected utility {utility:.6f}",
            )
        )
        return Allocation(workload.id, selected.id, utility, spawned, selected.spawn_cost if spawned else 0.0)

    def record(self, observation: PerformanceObservation) -> None:
        if observation.resource_id not in self.profiles:
            raise ValueError("cannot record performance for unknown resource")
        self._observations.append(observation)

    def retire_underperformers(self) -> tuple[str, ...]:
        retired: list[str] = []
        for resource_id in sorted(self._active):
            history = [item for item in self._observations if item.resource_id == resource_id]
            if len(history) < self.strategy.retirement_min_observations:
                continue
            if statistics.mean(item.utility for item in history) < self.strategy.retirement_utility_threshold:
                self._active.remove(resource_id)
                retired.append(resource_id)
                self._actions.append(TopologyAction(TopologyActionKind.RETIRE, resource_id, "historical utility below retirement threshold"))
        return tuple(retired)

    def checkpoint(self) -> StrategyCheckpoint:
        return StrategyCheckpoint(self.strategy, self.active_resource_ids, self.observations, self.actions)

    def rollback(self, checkpoint: StrategyCheckpoint) -> None:
        if any(resource_id not in self.profiles for resource_id in checkpoint.active_resource_ids):
            raise ValueError("checkpoint references an unknown resource")
        self.strategy = checkpoint.strategy
        self._active = set(checkpoint.active_resource_ids)
        self._observations = list(checkpoint.observations)
        self._actions = list(checkpoint.actions)
        self._actions.append(TopologyAction(TopologyActionKind.ROLLBACK, "topology", "restored declared strategy checkpoint"))

    def _expected_utility(self, profile: ResourceStrategyProfile, family: str) -> float:
        matching = [item for item in self._observations if item.resource_id == profile.id and item.workload_family == family]
        # Evidence transfers only within a declared workload family. Using a
        # specialist's success in an unrelated family is unjustified optimism.
        history = matching
        observed_progress = statistics.mean(item.progress if item.succeeded else 0.0 for item in history) if history else profile.prior_progress
        observed_cost = statistics.mean(item.total_cost for item in history) if history else profile.expected_cost
        uncertainty_bonus = self.strategy.exploration_strength / math.sqrt(len(history) + 1)
        spawn_cost = 0.0 if profile.id in self._active else profile.spawn_cost / self.strategy.spawn_amortization_tasks
        return (observed_progress + uncertainty_bonus) / (observed_cost + spawn_cost)


class FixedResourcePolicy:
    def __init__(self, profile: ResourceStrategyProfile) -> None:
        self.profile = profile

    def allocate(self, workload: Workload) -> Allocation:
        if workload.required_capability not in self.profile.capabilities:
            raise ValueError("fixed resource lacks required capability")
        return Allocation(workload.id, self.profile.id, self.profile.prior_progress / self.profile.expected_cost, False, 0.0)

    def record(self, observation: PerformanceObservation) -> None:
        pass


@dataclass(frozen=True, slots=True)
class PolicyComparison:
    paired_workloads: int
    adaptive_mean_utility: float
    fixed_mean_utility: float
    mean_improvement: float
    confidence_interval_95: tuple[float, float]
    randomization_p_value: float


def evaluate_policy(
    policy: AllocationPolicy,
    workloads: Sequence[Workload],
    outcomes: Mapping[tuple[str, str], tuple[float, float, bool]],
) -> tuple[float, ...]:
    utilities: list[float] = []
    for workload in workloads:
        allocation = policy.allocate(workload)
        try:
            progress, cost, succeeded = outcomes[(workload.id, allocation.resource_id)]
        except KeyError as error:
            raise ValueError("held-out outcome matrix is incomplete") from error
        observation = PerformanceObservation(
            allocation.resource_id,
            workload.family,
            progress,
            cost + allocation.activation_cost,
            succeeded,
        )
        policy.record(observation)
        utilities.append(observation.utility)
    return tuple(utilities)


def paired_policy_comparison(
    adaptive: Sequence[float],
    fixed: Sequence[float],
    *,
    bootstrap_samples: int = 2_000,
    seed: int = 0,
) -> PolicyComparison:
    if len(adaptive) != len(fixed) or not adaptive:
        raise ValueError("policy comparison requires equal non-empty paired samples")
    differences = [left - right for left, right in zip(adaptive, fixed)]
    observed = statistics.mean(differences)
    rng = random.Random(seed)
    bootstrap = sorted(statistics.mean(rng.choice(differences) for _ in differences) for _ in range(bootstrap_samples))
    lower = bootstrap[max(0, math.floor(0.025 * bootstrap_samples))]
    upper = bootstrap[min(bootstrap_samples - 1, math.ceil(0.975 * bootstrap_samples) - 1)]
    nonzero = [item for item in differences if item != 0]
    if len(nonzero) <= 20:
        values = [abs(statistics.mean(sign * value for sign, value in zip(signs, nonzero))) for signs in itertools.product((-1, 1), repeat=len(nonzero))]
        p_value = sum(value >= abs(observed) for value in values) / len(values) if values else 1.0
    else:
        draws = 20_000
        p_value = sum(abs(statistics.mean(value * rng.choice((-1, 1)) for value in nonzero)) >= abs(observed) for _ in range(draws)) / draws
    return PolicyComparison(len(differences), statistics.mean(adaptive), statistics.mean(fixed), observed, (lower, upper), p_value)
