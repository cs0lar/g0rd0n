"""Typed contracts for pre-registered harness-ablation studies."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


def _text(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


class WorkloadSplit(StrEnum):
    SELECTION = "selection"
    HELD_OUT = "held_out"


class WorkloadSource(StrEnum):
    SYNTHETIC = "synthetic"
    HISTORICAL_REPLAY = "historical_replay"


class HarnessMechanism(StrEnum):
    FROZEN_PROTOCOLS = "frozen_protocols"
    EVALUATION_ISOLATION = "evaluation_isolation"
    SHARED_SURVEY_FORUM = "shared_survey_forum"
    FRESH_SESSIONS = "fresh_sessions"
    INTEGRITY_MONITORING = "integrity_monitoring"


MECHANISM_ORDER = tuple(HarnessMechanism)


class SeededDefect(StrEnum):
    PROTOCOL_DRIFT = "protocol_drift"
    EVALUATION_LEAKAGE = "evaluation_leakage"
    CAPABILITY_REGRESSION = "capability_regression"
    DUPLICATED_WORK = "duplicated_work"
    CONTEXT_CONTAMINATION = "context_contamination"
    INTEGRITY_VIOLATION = "integrity_violation"


class IdeaOrigin(StrEnum):
    AUTOMATED = "automated"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class WorkloadBudget:
    cost_units: float
    wall_time_ms: int
    human_minutes: float

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(float(value)) or value < 0
            for value in (self.cost_units, self.wall_time_ms, self.human_minutes)
        ):
            raise ValueError("workload budget values must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class HumanIdea:
    valid: bool
    transfer_score: float
    cost_units: float
    wall_time_ms: int
    human_minutes: float

    def __post_init__(self) -> None:
        if not 0 <= self.transfer_score <= 1:
            raise ValueError("human idea transfer_score must be in [0, 1]")
        if any(
            not math.isfinite(float(value)) or value < 0
            for value in (self.cost_units, self.wall_time_ms, self.human_minutes)
        ):
            raise ValueError("human idea costs must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class AblationWorkload:
    id: str
    family: str
    split: WorkloadSplit
    source: WorkloadSource
    defects: frozenset[SeededDefect]
    has_valid_candidate: bool
    transfer_score: float
    base_cost_units: float
    base_wall_time_ms: int
    base_human_minutes: float
    budget: WorkloadBudget
    historical_artifact: str | None = None
    historical_sha256: str | None = None
    human_idea: HumanIdea | None = None

    def __post_init__(self) -> None:
        _text(self.id, "workload id")
        _text(self.family, "workload family")
        if not 0 <= self.transfer_score <= 1:
            raise ValueError("transfer_score must be in [0, 1]")
        actual = WorkloadBudget(self.base_cost_units, self.base_wall_time_ms, self.base_human_minutes)
        if (
            actual.cost_units > self.budget.cost_units
            or actual.wall_time_ms > self.budget.wall_time_ms
            or actual.human_minutes > self.budget.human_minutes
        ):
            raise ValueError("base workload cost exceeds its declared budget")
        if self.source is WorkloadSource.HISTORICAL_REPLAY:
            if not self.historical_artifact or not self.historical_sha256:
                raise ValueError("historical workloads require artifact provenance")
            if len(self.historical_sha256) != 64 or any(character not in "0123456789abcdef" for character in self.historical_sha256):
                raise ValueError("historical_sha256 must be lowercase SHA-256")
        elif self.historical_artifact is not None or self.historical_sha256 is not None:
            raise ValueError("synthetic workloads cannot claim historical artifacts")


@dataclass(frozen=True, slots=True)
class MechanismProfile:
    mechanism: HarnessMechanism
    cost_units: float
    wall_time_ms: int
    human_minutes: float
    complexity_points: int

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(float(value)) or value < 0
            for value in (self.cost_units, self.wall_time_ms, self.human_minutes, self.complexity_points)
        ):
            raise ValueError("mechanism costs and complexity must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class DecisionThresholds:
    progress_ci_lower: float
    minimum_integrity_violations_avoided: int
    minimum_duplicates_avoided: int
    maximum_cost_ratio: float

    def __post_init__(self) -> None:
        if self.progress_ci_lower < 0 or self.minimum_integrity_violations_avoided <= 0:
            raise ValueError("decision thresholds must be positive")
        if self.minimum_duplicates_avoided <= 0 or self.maximum_cost_ratio < 1:
            raise ValueError("decision thresholds must permit a non-decreasing cost ratio")


@dataclass(frozen=True, slots=True)
class HarnessConfiguration:
    id: str
    governor_policy: str
    mechanisms: tuple[HarnessMechanism, ...]
    idea_origin: IdeaOrigin = IdeaOrigin.AUTOMATED

    def __post_init__(self) -> None:
        _text(self.id, "configuration id")
        if self.governor_policy != "fixed":
            raise ValueError("Phase 20 comparisons require the fixed governor")
        if len(self.mechanisms) != len(set(self.mechanisms)):
            raise ValueError("configuration mechanisms must be unique")
        order = {mechanism: index for index, mechanism in enumerate(MECHANISM_ORDER)}
        if tuple(sorted(self.mechanisms, key=order.__getitem__)) != self.mechanisms:
            raise ValueError("configuration mechanisms must use canonical order")
        if self.idea_origin is IdeaOrigin.HUMAN and self.mechanisms:
            raise ValueError("human-originated ideas are a separately costed baseline")

    @classmethod
    def fixed_baseline(cls) -> "HarnessConfiguration":
        return cls("fixed-governor-baseline", "fixed", ())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HarnessConfiguration":
        return cls(
            str(value["id"]),
            str(value["governor_policy"]),
            tuple(HarnessMechanism(item) for item in value["mechanisms"]),
            IdeaOrigin(value.get("idea_origin", "automated")),
        )

    @classmethod
    def from_json(cls, path: Path) -> "HarnessConfiguration":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("harness configuration root must be an object")
        return cls.from_dict(value)


@dataclass(frozen=True, slots=True)
class WorkloadOutcome:
    workload_id: str
    discovery_valid: bool
    transfer_score: float
    integrity_violations: int
    duplicated_work: int
    human_review_minutes: float
    wall_time_ms: int
    total_cost_units: float
    budget_exceeded: bool

    @property
    def valid_progress_per_cost(self) -> float:
        if not self.discovery_valid or self.total_cost_units == 0:
            return 0.0
        return self.transfer_score / self.total_cost_units


@dataclass(frozen=True, slots=True)
class RunMetrics:
    workload_count: int
    valid_discovery_rate: float
    mean_transfer: float
    integrity_violations: int
    duplicated_work: int
    human_review_minutes: float
    wall_time_ms: int
    total_cost_units: float
    complexity_points: int
    budget_failures: int

    @property
    def valid_progress_per_cost(self) -> float:
        if self.total_cost_units == 0:
            return 0.0
        return (
            self.valid_discovery_rate
            * self.mean_transfer
            * self.workload_count
            / self.total_cost_units
        )


@dataclass(frozen=True, slots=True)
class RunResult:
    configuration: HarnessConfiguration
    split: WorkloadSplit
    workload_ids: tuple[str, ...]
    budget_hash: str
    outcomes: tuple[WorkloadOutcome, ...]
    metrics: RunMetrics


@dataclass(frozen=True, slots=True)
class PairedEstimate:
    metric: str
    paired_workloads: int
    mean_delta: float
    confidence_interval_95: tuple[float, float]


class AdoptionStatus(StrEnum):
    ADOPT = "adopt"
    EXPERIMENTAL = "experimental"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class MechanismDecision:
    mechanism: HarnessMechanism
    status: AdoptionStatus
    reason: str
    progress_per_cost: PairedEstimate
    transfer: PairedEstimate
    integrity_violations_avoided: int
    duplicates_avoided: int
    total_cost_ratio: float
    complexity_points: int


@dataclass(frozen=True, slots=True)
class AdoptionPlan:
    decisions: tuple[MechanismDecision, ...]
    default_configuration: HarnessConfiguration

    def rollback_configuration(self) -> HarnessConfiguration:
        return HarnessConfiguration.fixed_baseline()


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    mechanism: HarnessMechanism
    scenarios: int
    adopted_scenarios: int

    @property
    def adoption_fraction(self) -> float:
        return self.adopted_scenarios / self.scenarios


@dataclass(frozen=True, slots=True)
class AblationSpec:
    id: str
    workloads: tuple[AblationWorkload, ...]
    mechanism_profiles: tuple[MechanismProfile, ...]
    thresholds: DecisionThresholds
    bootstrap_samples: int
    bootstrap_seed: int

    def __post_init__(self) -> None:
        _text(self.id, "ablation id")
        ids = [item.id for item in self.workloads]
        if not self.workloads or len(ids) != len(set(ids)):
            raise ValueError("ablation workloads must be non-empty and unique")
        if {item.split for item in self.workloads} != set(WorkloadSplit):
            raise ValueError("ablation requires selection and held-out workloads")
        profiles = [item.mechanism for item in self.mechanism_profiles]
        if tuple(profiles) != MECHANISM_ORDER:
            raise ValueError("ablation must profile every mechanism in canonical order")
        if self.bootstrap_samples < 100 or self.bootstrap_seed < 0:
            raise ValueError("bootstrap configuration is invalid")

    def profile(self, mechanism: HarnessMechanism) -> MechanismProfile:
        return next(item for item in self.mechanism_profiles if item.mechanism is mechanism)

    def for_split(self, split: WorkloadSplit) -> tuple[AblationWorkload, ...]:
        return tuple(item for item in self.workloads if item.split is split)

    @classmethod
    def from_json(cls, path: Path, *, repository_root: Path) -> "AblationSpec":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("ablation specification root must be an object")
        budget_value = value["per_workload_budget"]
        budget = WorkloadBudget(
            float(budget_value["cost_units"]),
            int(budget_value["wall_time_ms"]),
            float(budget_value["human_minutes"]),
        )
        workloads: list[AblationWorkload] = []
        for group in value["workload_groups"]:
            source = WorkloadSource(group["source"])
            artifact = group.get("historical_artifact")
            digest = group.get("historical_sha256")
            if source is WorkloadSource.HISTORICAL_REPLAY:
                root = repository_root.resolve()
                artifact_path = (root / str(artifact)).resolve()
                if not artifact_path.is_relative_to(root):
                    raise ValueError(f"historical artifact escapes repository for group {group['id']}")
                if not artifact_path.is_file() or hashlib.sha256(artifact_path.read_bytes()).hexdigest() != digest:
                    raise ValueError(f"historical artifact mismatch for group {group['id']}")
            idea_value = group.get("human_idea")
            idea = None if idea_value is None else HumanIdea(
                bool(idea_value["valid"]), float(idea_value["transfer_score"]),
                float(idea_value["cost_units"]), int(idea_value["wall_time_ms"]),
                float(idea_value["human_minutes"]),
            )
            for index in range(int(group["count"])):
                workloads.append(
                    AblationWorkload(
                        f"{group['id']}:{index}", str(group["family"]), WorkloadSplit(group["split"]),
                        source, frozenset(SeededDefect(item) for item in group.get("defects", ())),
                        bool(group["has_valid_candidate"]), float(group["transfer_score"]),
                        float(group["base_cost_units"]), int(group["base_wall_time_ms"]),
                        float(group["base_human_minutes"]), budget,
                        None if artifact is None else str(artifact), None if digest is None else str(digest), idea,
                    )
                )
        profiles = tuple(
            MechanismProfile(
                HarnessMechanism(item["mechanism"]), float(item["cost_units"]),
                int(item["wall_time_ms"]), float(item["human_minutes"]),
                int(item["complexity_points"]),
            )
            for item in value["mechanism_profiles"]
        )
        thresholds = value["decision_thresholds"]
        return cls(
            str(value["id"]), tuple(workloads), profiles,
            DecisionThresholds(
                float(thresholds["progress_ci_lower"]),
                int(thresholds["minimum_integrity_violations_avoided"]),
                int(thresholds["minimum_duplicates_avoided"]),
                float(thresholds["maximum_cost_ratio"]),
            ),
            int(value["bootstrap_samples"]), int(value["bootstrap_seed"]),
        )
