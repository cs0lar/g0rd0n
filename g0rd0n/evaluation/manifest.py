"""Pinned baseline and benchmark manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class TaskFamily(StrEnum):
    ALGORITHMIC_GENERALIZATION = "algorithmic_generalization"
    COMPOSITIONAL_TRANSFER = "compositional_transfer"
    CONTINUAL_LEARNING = "continual_learning"
    ONLINE_ADAPTATION = "online_adaptation"
    CAUSAL_SYSTEM_IDENTIFICATION = "causal_system_identification"
    MEMORY = "memory"
    PLANNING = "planning"
    PROGRAM_INDUCTION = "program_induction"


class BaselineFamily(StrEnum):
    TRANSFORMER = "transformer"
    DNN = "dnn"
    STATE_SPACE_MODEL = "state_space_model"
    TOY_LOOKUP = "toy_lookup"
    TOY_SYMBOLIC = "toy_symbolic"


class StudyStage(StrEnum):
    EXPLORATORY = "exploratory"
    CONFIRMATORY = "confirmatory"
    HARNESS_VALIDATION = "harness_validation"


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class HardwareSpec:
    architecture: str
    processor: str
    logical_cpu_count: int
    accelerator: str | None
    memory_bytes: int | None

    def __post_init__(self) -> None:
        if not self.architecture.strip() or not self.processor.strip() or self.logical_cpu_count <= 0:
            raise ValueError("hardware architecture, processor, and CPU count are required")
        if self.memory_bytes is not None and self.memory_bytes <= 0:
            raise ValueError("hardware memory_bytes must be positive")


@dataclass(frozen=True, slots=True)
class EnvironmentSpec:
    operating_system: str
    python_version: str
    dependencies: tuple[str, ...]
    environment_variables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operating_system.strip() or not self.python_version.strip():
            raise ValueError("operating system and Python version are required")


@dataclass(frozen=True, slots=True)
class ReproductionSpec:
    command: tuple[str, ...]
    source_revision: str
    container_image: str | None = None
    container_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.command or any(not item.strip() for item in self.command):
            raise ValueError("reproduction command is required")
        if not self.source_revision.strip():
            raise ValueError("source revision is required")
        if (self.container_image is None) != (self.container_digest is None):
            raise ValueError("container image and digest must be declared together")
        if self.container_digest is not None and not self.container_digest.startswith("sha256:"):
            raise ValueError("container digest must use sha256")


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    id: str
    version: str
    task_family: TaskFamily
    generality_rationale: str
    known_shortcuts: tuple[str, ...]
    contamination_risk: str
    primary_metric: str
    higher_is_better: bool
    stage: StudyStage

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "benchmark.id"),
            (self.version, "benchmark.version"),
            (self.generality_rationale, "benchmark.generality_rationale"),
            (self.contamination_risk, "benchmark.contamination_risk"),
            (self.primary_metric, "benchmark.primary_metric"),
        ):
            _text(value, field)
        if not self.known_shortcuts:
            raise ValueError("benchmark known_shortcuts cannot be empty")


@dataclass(frozen=True, slots=True)
class BaselineManifest:
    id: str
    family: BaselineFamily
    role: str
    implementation: str
    implementation_version: str
    model_revision: str
    weights_digest: str | None
    runner: str
    seeds: tuple[int, ...]
    benchmark: BenchmarkSpec
    hardware: HardwareSpec
    environment: EnvironmentSpec
    reproduction: ReproductionSpec
    training_data: str
    energy_boundary: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "id"),
            (self.role, "role"),
            (self.implementation, "implementation"),
            (self.implementation_version, "implementation_version"),
            (self.model_revision, "model_revision"),
            (self.runner, "runner"),
            (self.training_data, "training_data"),
            (self.energy_boundary, "energy_boundary"),
        ):
            _text(value, field)
        if self.role not in {"baseline", "candidate"}:
            raise ValueError("manifest role must be baseline or candidate")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or any(seed < 0 for seed in self.seeds):
            raise ValueError("seeds must be non-empty, unique, and non-negative")
        if self.family in {BaselineFamily.TRANSFORMER, BaselineFamily.DNN} and not self.weights_digest:
            raise ValueError("DNN and Transformer manifests require a weights digest")

    @classmethod
    def from_json(cls, path: Path) -> "BaselineManifest":
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, Mapping):
            raise ValueError("baseline manifest root must be an object")
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BaselineManifest":
        benchmark = value["benchmark"]
        hardware = value["hardware"]
        environment = value["environment"]
        reproduction = value["reproduction"]
        return cls(
            id=_text(value.get("id"), "id"),
            family=BaselineFamily(value["family"]),
            role=_text(value.get("role"), "role"),
            implementation=_text(value.get("implementation"), "implementation"),
            implementation_version=_text(value.get("implementation_version"), "implementation_version"),
            model_revision=_text(value.get("model_revision"), "model_revision"),
            weights_digest=None if value.get("weights_digest") is None else _text(value["weights_digest"], "weights_digest"),
            runner=_text(value.get("runner"), "runner"),
            seeds=tuple(int(seed) for seed in value["seeds"]),
            benchmark=BenchmarkSpec(
                id=_text(benchmark.get("id"), "benchmark.id"),
                version=_text(benchmark.get("version"), "benchmark.version"),
                task_family=TaskFamily(benchmark["task_family"]),
                generality_rationale=_text(benchmark.get("generality_rationale"), "benchmark.generality_rationale"),
                known_shortcuts=tuple(str(item) for item in benchmark["known_shortcuts"]),
                contamination_risk=_text(benchmark.get("contamination_risk"), "benchmark.contamination_risk"),
                primary_metric=_text(benchmark.get("primary_metric"), "benchmark.primary_metric"),
                higher_is_better=bool(benchmark["higher_is_better"]),
                stage=StudyStage(benchmark["stage"]),
            ),
            hardware=HardwareSpec(
                _text(hardware.get("architecture"), "hardware.architecture"),
                _text(hardware.get("processor"), "hardware.processor"),
                int(hardware["logical_cpu_count"]),
                None if hardware.get("accelerator") is None else str(hardware["accelerator"]),
                None if hardware.get("memory_bytes") is None else int(hardware["memory_bytes"]),
            ),
            environment=EnvironmentSpec(
                _text(environment.get("operating_system"), "environment.operating_system"),
                _text(environment.get("python_version"), "environment.python_version"),
                tuple(str(item) for item in environment["dependencies"]),
                tuple(str(item) for item in environment.get("environment_variables", ())),
            ),
            reproduction=ReproductionSpec(
                tuple(str(item) for item in reproduction["command"]),
                _text(reproduction.get("source_revision"), "reproduction.source_revision"),
                None if reproduction.get("container_image") is None else str(reproduction["container_image"]),
                None if reproduction.get("container_digest") is None else str(reproduction["container_digest"]),
            ),
            training_data=_text(value.get("training_data"), "training_data"),
            energy_boundary=_text(value.get("energy_boundary"), "energy_boundary"),
        )
