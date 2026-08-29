"""Paradigm-neutral execution and benchmark adapters."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Protocol

from g0rd0n.evaluation.harness import ResourceUsage

from .spec import ParadigmSpec


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    output: int
    usage: ResourceUsage
    trace: tuple[str, ...]


class ParadigmRunner(Protocol):
    def execute(self, spec: ParadigmSpec, inputs: tuple[int, ...], *, seed: int) -> ExecutionResult: ...


class RunnerRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ParadigmRunner]] = {}

    def register(self, name: str, factory: Callable[[], ParadigmRunner]) -> None:
        if not name.strip() or name in self._factories:
            raise ValueError("runner names must be non-empty and unique")
        self._factories[name] = factory

    def create(self, spec: ParadigmSpec) -> ParadigmRunner:
        try:
            return self._factories[spec.runner]()
        except KeyError as error:
            raise ValueError(f"no runner registered for {spec.runner}") from error


class ParadigmBenchmarkSystem:
    """Runs any registered paradigm against identical input/output cases."""

    def __init__(
        self,
        spec: ParadigmSpec,
        registry: RunnerRegistry,
        cases: tuple[tuple[tuple[int, ...], int], ...],
    ) -> None:
        if not cases:
            raise ValueError("benchmark cases cannot be empty")
        self._spec = spec
        self._registry = registry
        self._cases = cases

    def evaluate(self, *, seed: int, random_source: random.Random):
        cases = list(self._cases)
        random_source.shuffle(cases)
        correct = operations = peak_memory = 0
        latency = 0.0
        for inputs, expected in cases:
            execution = self._registry.create(self._spec).execute(self._spec, inputs, seed=seed)
            correct += execution.output == expected
            operations += execution.usage.operations
            peak_memory = max(peak_memory, execution.usage.peak_memory_bytes)
            latency += execution.usage.modelled_latency_ms
        return (
            {"accuracy": correct / len(cases)},
            ResourceUsage(operations, peak_memory, latency),
        )
