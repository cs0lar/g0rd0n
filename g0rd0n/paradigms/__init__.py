"""Executable specifications for candidate cognitive paradigms."""

from .runner import ExecutionResult, ParadigmBenchmarkSystem, ParadigmRunner, RunnerRegistry
from .spec import ComplexityClaim, Falsifier, ParadigmSpec
from .toy import EventParityRunner, GraphRewriteParityRunner, builtin_runner_registry

__all__ = [
    "ComplexityClaim",
    "EventParityRunner",
    "ExecutionResult",
    "Falsifier",
    "GraphRewriteParityRunner",
    "ParadigmBenchmarkSystem",
    "ParadigmRunner",
    "ParadigmSpec",
    "RunnerRegistry",
    "builtin_runner_registry",
]
