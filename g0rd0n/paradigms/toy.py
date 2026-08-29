"""Contrasting toy paradigms used to test interface neutrality."""

from __future__ import annotations

from g0rd0n.evaluation.harness import ResourceUsage

from .runner import ExecutionResult, RunnerRegistry
from .spec import ParadigmSpec


class EventParityRunner:
    """Sparse state machine: zero events perform no state transition."""

    def execute(self, spec: ParadigmSpec, inputs: tuple[int, ...], *, seed: int) -> ExecutionResult:
        del seed
        parity = 0
        trace: list[str] = []
        operations = 0
        for value in inputs:
            if value:
                parity ^= 1
                operations += 1
                trace.append("toggle")
        return ExecutionResult(parity, ResourceUsage(operations, 1, operations * 0.1), tuple(trace))


class GraphRewriteParityRunner:
    """Symbolic reducer: delete zero nodes and cancel adjacent one nodes."""

    def execute(self, spec: ParadigmSpec, inputs: tuple[int, ...], *, seed: int) -> ExecutionResult:
        del seed
        graph = [value for value in inputs]
        trace: list[str] = []
        operations = 0
        while 0 in graph:
            graph.remove(0)
            operations += 1
            trace.append("delete(0)")
        while len(graph) >= 2:
            del graph[:2]
            operations += 1
            trace.append("cancel(1,1)")
        return ExecutionResult(len(graph), ResourceUsage(operations, len(inputs), operations * 0.2), tuple(trace))


def builtin_runner_registry() -> RunnerRegistry:
    registry = RunnerRegistry()
    registry.register("builtin:event_parity", EventParityRunner)
    registry.register("builtin:graph_rewrite_parity", GraphRewriteParityRunner)
    return registry
