"""Reproducible, resource-aware baseline evaluation."""

from .analysis import Comparison, MetricDirection, MetricSpec, paired_comparison, pareto_front
from .harness import BenchmarkHarness, BenchmarkSystem, TrialMeasurement
from .manifest import BaselineManifest, BenchmarkSpec, TaskFamily

__all__ = [
    "BaselineManifest",
    "BenchmarkHarness",
    "BenchmarkSpec",
    "BenchmarkSystem",
    "Comparison",
    "MetricDirection",
    "MetricSpec",
    "TaskFamily",
    "TrialMeasurement",
    "paired_comparison",
    "pareto_front",
]
