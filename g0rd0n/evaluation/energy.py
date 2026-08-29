"""Boundary-aware energy measurement and scaling projections."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from .analysis import MetricDirection, MetricSpec, pareto_front


class MeasurementMethod(StrEnum):
    MEASURED = "measured"
    MODELLED = "modelled"


@dataclass(frozen=True, slots=True)
class SystemBoundary:
    id: str
    included_components: tuple[str, ...]
    excluded_components: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.included_components:
            raise ValueError("energy boundary requires an id and included components")
        if set(self.included_components) & set(self.excluded_components):
            raise ValueError("energy boundary cannot include and exclude the same component")


@dataclass(frozen=True, slots=True)
class EnergyUncertainty:
    relative_fraction: float
    basis: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.relative_fraction) or self.relative_fraction < 0:
            raise ValueError("relative uncertainty must be finite and non-negative")
        if not self.basis.strip():
            raise ValueError("uncertainty basis is required")


@dataclass(frozen=True, slots=True)
class EnergyReading:
    joules: float
    timestamp_ns: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.joules) or self.joules < 0 or self.timestamp_ns < 0:
            raise ValueError("energy readings must be finite, non-negative values")


class EnergyMeter(Protocol):
    boundary: SystemBoundary
    method: MeasurementMethod
    uncertainty: EnergyUncertainty
    maximum_joules: float | None

    def read(self) -> EnergyReading: ...


@dataclass(frozen=True, slots=True)
class EnergyProfile:
    boundary: SystemBoundary
    method: MeasurementMethod
    uncertainty: EnergyUncertainty
    idle_power_watts: float
    active_power_watts: float
    average_power_watts: float
    active_energy_joules: float
    active_duration_seconds: float
    joules_per_task: float
    joules_per_learned_update: float | None
    energy_delay_product_joule_seconds: float

    def __post_init__(self) -> None:
        values = (
            self.idle_power_watts,
            self.active_power_watts,
            self.average_power_watts,
            self.active_energy_joules,
            self.joules_per_task,
            self.energy_delay_product_joule_seconds,
        )
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("energy profile values must be finite and non-negative")
        if self.active_duration_seconds <= 0 or not math.isfinite(self.active_duration_seconds):
            raise ValueError("active duration must be finite and positive")
        if self.joules_per_learned_update is not None and (
            not math.isfinite(self.joules_per_learned_update) or self.joules_per_learned_update < 0
        ):
            raise ValueError("per-update energy must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ScalingProjection:
    tasks_per_second: float
    utilization: float
    projected_power_watts: float
    uncertainty_watts: float


@dataclass(frozen=True, slots=True)
class CapabilityCostEnergyRecord:
    id: str
    capability: float
    monetary_cost: float
    energy: EnergyProfile


T = TypeVar("T")


def _delta(start: EnergyReading, end: EnergyReading, maximum_joules: float | None) -> tuple[float, float]:
    elapsed = (end.timestamp_ns - start.timestamp_ns) / 1_000_000_000
    if elapsed <= 0:
        raise ValueError("energy readings require increasing timestamps")
    energy = end.joules - start.joules
    if energy < 0 and maximum_joules is not None:
        energy += maximum_joules
    if energy < 0:
        raise ValueError("energy counter decreased without a declared wrap limit")
    return energy, elapsed


def measure_energy(
    meter: EnergyMeter,
    workload: Callable[[], T],
    *,
    task_count: int,
    learned_updates: int = 0,
) -> tuple[T, EnergyProfile]:
    if task_count <= 0 or learned_updates < 0:
        raise ValueError("task_count must be positive and learned_updates non-negative")
    idle_start = meter.read()
    idle_end = meter.read()
    idle_energy, idle_duration = _delta(idle_start, idle_end, meter.maximum_joules)
    active_start = meter.read()
    result = workload()
    active_end = meter.read()
    active_energy, active_duration = _delta(active_start, active_end, meter.maximum_joules)
    idle_power = idle_energy / idle_duration
    active_power = active_energy / active_duration
    total_energy = idle_energy + active_energy
    total_duration = idle_duration + active_duration
    return result, EnergyProfile(
        meter.boundary,
        meter.method,
        meter.uncertainty,
        idle_power,
        active_power,
        total_energy / total_duration,
        active_energy,
        active_duration,
        active_energy / task_count,
        None if learned_updates == 0 else active_energy / learned_updates,
        active_energy * active_duration,
    )


def project_power(profile: EnergyProfile, *, tasks_per_second: float, utilization: float) -> ScalingProjection:
    if not math.isfinite(tasks_per_second) or tasks_per_second < 0 or not math.isfinite(utilization) or not 0 <= utilization <= 1:
        raise ValueError("projection rate must be non-negative and utilization within [0, 1]")
    dynamic_power = max(0.0, profile.active_power_watts - profile.idle_power_watts)
    projected = profile.idle_power_watts + dynamic_power * utilization
    throughput_power = profile.idle_power_watts + profile.joules_per_task * tasks_per_second
    projected = max(projected, throughput_power)
    return ScalingProjection(
        tasks_per_second,
        utilization,
        projected,
        projected * profile.uncertainty.relative_fraction,
    )


def energy_pareto_front(records: tuple[CapabilityCostEnergyRecord, ...]) -> tuple[str, ...]:
    if not records:
        raise ValueError("energy Pareto analysis requires records")
    boundaries = {record.energy.boundary for record in records}
    if len(boundaries) != 1:
        raise ValueError("energy comparisons require identical system boundaries")
    points = {
        record.id: {
            "capability": record.capability,
            "cost": record.monetary_cost,
            "joules_per_task": record.energy.joules_per_task,
        }
        for record in records
    }
    return pareto_front(
        points,
        (
            MetricSpec("capability", MetricDirection.MAXIMIZE),
            MetricSpec("cost", MetricDirection.MINIMIZE),
            MetricSpec("joules_per_task", MetricDirection.MINIMIZE),
        ),
    )


class SyntheticEnergyMeter:
    """Deterministic meter for tests and modelled-energy fallbacks."""

    def __init__(
        self,
        readings: tuple[EnergyReading, ...],
        *,
        boundary: SystemBoundary,
        uncertainty: EnergyUncertainty,
        method: MeasurementMethod = MeasurementMethod.MODELLED,
        maximum_joules: float | None = None,
    ) -> None:
        self._readings = iter(readings)
        self.boundary = boundary
        self.uncertainty = uncertainty
        self.method = method
        self.maximum_joules = maximum_joules

    def read(self) -> EnergyReading:
        try:
            return next(self._readings)
        except StopIteration as error:
            raise RuntimeError("synthetic meter exhausted") from error


class LinuxRaplEnergyMeter:
    """Reads Linux powercap package counters when Intel/AMD RAPL is exposed."""

    def __init__(self, energy_paths: tuple[Path, ...]) -> None:
        if not energy_paths:
            raise ValueError("at least one RAPL energy counter is required")
        self._paths = energy_paths
        self.boundary = SystemBoundary(
            "rapl-package-total",
            tuple(f"cpu_package:{path.parent.name}" for path in energy_paths),
            ("dram unless included by package counter", "accelerators", "storage", "display"),
        )
        self.method = MeasurementMethod.MEASURED
        self.uncertainty = EnergyUncertainty(0.05, "conservative default for host RAPL counters")
        maxima = [float((path.parent / "max_energy_range_uj").read_text().strip()) / 1_000_000 for path in energy_paths]
        self.maximum_joules = sum(maxima)

    @classmethod
    def discover(cls, root: Path = Path("/sys/class/powercap")) -> "LinuxRaplEnergyMeter | None":
        # Select package roots only; summing nested zones would double-count energy.
        paths = tuple(sorted(path for path in root.glob("intel-rapl:*/energy_uj") if path.parent.name.count(":") == 1))
        if not paths:
            return None
        try:
            for path in paths:
                float(path.read_text().strip())
                float((path.parent / "max_energy_range_uj").read_text().strip())
            return cls(paths)
        except (OSError, ValueError):
            return None

    def read(self) -> EnergyReading:
        return EnergyReading(
            sum(float(path.read_text().strip()) / 1_000_000 for path in self._paths),
            time.monotonic_ns(),
        )
