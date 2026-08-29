"""Reproducible, resource-aware baseline evaluation."""

from .analysis import Comparison, MetricDirection, MetricSpec, paired_comparison, pareto_front
from .energy import (
    CapabilityCostEnergyRecord,
    EnergyProfile,
    EnergyReading,
    EnergyUncertainty,
    LinuxRaplEnergyMeter,
    MeasurementMethod,
    ScalingProjection,
    SyntheticEnergyMeter,
    SystemBoundary,
    energy_pareto_front,
    measure_energy,
    project_power,
)
from .harness import BenchmarkHarness, BenchmarkSystem, TrialMeasurement
from .manifest import BaselineManifest, BenchmarkSpec, TaskFamily

__all__ = [
    "BaselineManifest",
    "BenchmarkHarness",
    "BenchmarkSpec",
    "BenchmarkSystem",
    "Comparison",
    "CapabilityCostEnergyRecord",
    "EnergyProfile",
    "EnergyReading",
    "EnergyUncertainty",
    "LinuxRaplEnergyMeter",
    "MeasurementMethod",
    "MetricDirection",
    "MetricSpec",
    "ScalingProjection",
    "SyntheticEnergyMeter",
    "SystemBoundary",
    "energy_pareto_front",
    "measure_energy",
    "TaskFamily",
    "TrialMeasurement",
    "paired_comparison",
    "pareto_front",
    "project_power",
]
