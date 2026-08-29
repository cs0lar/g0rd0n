"""Seeded benchmark execution with environment and resource capture."""

from __future__ import annotations

import os
import math
import platform
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .manifest import BaselineManifest


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    operations: int
    peak_memory_bytes: int
    modelled_latency_ms: float

    def __post_init__(self) -> None:
        if self.operations < 0 or self.peak_memory_bytes < 0 or self.modelled_latency_ms < 0:
            raise ValueError("resource usage cannot be negative")


@dataclass(frozen=True, slots=True)
class TrialMeasurement:
    seed: int
    metrics: Mapping[str, float]
    usage: ResourceUsage
    wall_time_ns: int


@dataclass(frozen=True, slots=True)
class EnvironmentCapture:
    python_version: str
    implementation: str
    operating_system: str
    architecture: str
    processor: str
    logical_cpu_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    manifest_id: str
    benchmark_id: str
    benchmark_version: str
    trials: tuple[TrialMeasurement, ...]
    environment: EnvironmentCapture

    def metric_values(self, metric: str) -> tuple[float, ...]:
        return tuple(trial.metrics[metric] for trial in self.trials)


class BenchmarkSystem(Protocol):
    def evaluate(self, *, seed: int, random_source: random.Random) -> tuple[Mapping[str, float], ResourceUsage]: ...


class BenchmarkHarness:
    def run(self, manifest: BaselineManifest, system: BenchmarkSystem) -> BenchmarkResult:
        trials: list[TrialMeasurement] = []
        for seed in manifest.seeds:
            random_source = random.Random(seed)
            started = time.perf_counter_ns()
            metrics, usage = system.evaluate(seed=seed, random_source=random_source)
            elapsed = time.perf_counter_ns() - started
            if manifest.benchmark.primary_metric not in metrics:
                raise ValueError("system omitted the benchmark primary metric")
            if any(
                not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in metrics.values()
            ):
                raise ValueError("benchmark metrics must be finite numbers")
            trials.append(
                TrialMeasurement(seed, dict(sorted(metrics.items())), usage, elapsed)
            )
        return BenchmarkResult(
            manifest.id,
            manifest.benchmark.id,
            manifest.benchmark.version,
            tuple(trials),
            EnvironmentCapture(
                platform.python_version(),
                sys.implementation.name,
                platform.platform(),
                platform.machine() or "unknown",
                platform.processor() or "unknown",
                os.cpu_count() or 1,
            ),
        )
