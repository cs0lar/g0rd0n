"""Hierarchical trajectory monitoring that preserves maximum suspicion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from g0rd0n.research.ledger import content_hash

from g0rd0n.evaluation import EvaluationReport
from g0rd0n.memory import Finding
from g0rd0n.methods import ExecutionReceipt

from .controls import BindingInspector, inspect_trace_events
from .models import (
    ChunkJudgment,
    IntegrityCategory,
    IntegrityFlag,
    IntegrityPolicy,
    TraceEvent,
    TraceReport,
)


@dataclass(frozen=True, slots=True)
class JudgeResult:
    suspicion: float
    categories: tuple[IntegrityCategory, ...]
    evidence: tuple[str, ...]
    reviewer: str
    ambiguous: bool = False


class TraceJudge(Protocol):
    def review(self, events: tuple[TraceEvent, ...]) -> JudgeResult: ...


class NoopTraceJudge:
    """Explicit zero-suspicion judge for deterministic-only deployments."""

    def review(self, events: tuple[TraceEvent, ...]) -> JudgeResult:
        del events
        return JudgeResult(0.0, (), (), "noop-monitor")


class HierarchicalTraceMonitor:
    def __init__(self, policy: IntegrityPolicy, judge: TraceJudge | None = None) -> None:
        self.policy = policy
        self.judge = judge or NoopTraceJudge()

    def monitor(
        self,
        events: tuple[TraceEvent, ...],
        *,
        expected_event_count: int,
        binding_flags: tuple[IntegrityFlag, ...] = (),
        binding_checked: bool = False,
    ) -> TraceReport:
        if expected_event_count < 0:
            raise ValueError("expected_event_count must be non-negative")
        ordered = tuple(sorted(events, key=lambda item: item.sequence))
        trace_hash = content_hash([asdict(item) for item in ordered])
        expected = tuple(range(expected_event_count))
        actual = tuple(item.sequence for item in ordered)
        complete = bool(ordered) and actual == expected
        flags = [*inspect_trace_events(ordered), *binding_flags]
        monitor_failed = not complete
        judgments: list[ChunkJudgment] = []

        leaves: list[ChunkJudgment] = []
        chunk_size = self.policy.max_trace_events_per_chunk
        for offset in range(0, len(ordered), chunk_size):
            chunk = ordered[offset : offset + chunk_size]
            chunk_id = f"leaf:{offset // chunk_size}"
            try:
                result = self.judge.review(chunk)
                judgment = ChunkJudgment(
                    chunk_id,
                    tuple(item.sequence for item in chunk),
                    result.suspicion,
                    tuple(sorted(set(result.categories), key=lambda item: item.value)),
                    tuple(dict.fromkeys(result.evidence)),
                    result.reviewer,
                    result.ambiguous,
                )
            except Exception as error:
                judgment = ChunkJudgment(
                    chunk_id,
                    tuple(item.sequence for item in chunk),
                    1.0,
                    (IntegrityCategory.MONITOR_FAILURE,),
                    (f"monitor-error:{type(error).__name__}",),
                    "monitor-runtime",
                    True,
                )
            leaves.append(judgment)
            judgments.append(judgment)
            if judgment.ambiguous:
                monitor_failed = True
            for category in judgment.categories:
                if judgment.suspicion >= self.policy.threshold(category):
                    flags.append(
                        IntegrityFlag.create(
                            category,
                            judgment.suspicion,
                            "trajectory monitor raised suspicion",
                            judgment.evidence or (f"chunk:{chunk_id}",),
                            deterministic=False,
                            raised_by=judgment.reviewer,
                        )
                    )

        level = leaves
        depth = 0
        while len(level) > 1:
            combined: list[ChunkJudgment] = []
            for offset in range(0, len(level), self.policy.hierarchy_fanout):
                children = level[offset : offset + self.policy.hierarchy_fanout]
                maximum = max(item.suspicion for item in children)
                parent = ChunkJudgment(
                    f"level:{depth}:{offset // self.policy.hierarchy_fanout}",
                    tuple(sequence for item in children for sequence in item.event_sequences),
                    maximum,
                    tuple(sorted({category for item in children for category in item.categories}, key=lambda item: item.value)),
                    tuple(dict.fromkeys(evidence for item in children for evidence in item.evidence)),
                    "hierarchical-maximum",
                    any(item.ambiguous for item in children),
                    tuple(item.chunk_id for item in children),
                )
                combined.append(parent)
                judgments.append(parent)
            level = combined
            depth += 1

        if monitor_failed:
            flags.append(
                IntegrityFlag.create(
                    IntegrityCategory.MONITOR_FAILURE,
                    1.0,
                    "trajectory monitor failed, was ambiguous, or did not cover a contiguous complete trace",
                    (f"trace:{trace_hash}",),
                    deterministic=False,
                    raised_by="monitor-controller",
                )
            )
        maximum = max(
            (item.suspicion for item in (*leaves, *flags)),
            default=1.0,
        )
        return TraceReport(
            self.policy.version,
            self.policy.policy_hash,
            trace_hash,
            len(ordered),
            ordered,
            tuple(judgments),
            tuple(_deduplicate_flags(flags)),
            maximum,
            complete,
            binding_checked,
            monitor_failed,
        )

    def monitor_execution(
        self,
        events: tuple[TraceEvent, ...],
        *,
        expected_event_count: int,
        finding: Finding,
        receipt: ExecutionReceipt,
        evaluation_report: EvaluationReport | None,
    ) -> TraceReport:
        return self.monitor(
            events,
            expected_event_count=expected_event_count,
            binding_flags=BindingInspector.inspect(finding, receipt, evaluation_report),
            binding_checked=True,
        )


def _deduplicate_flags(flags: list[IntegrityFlag]) -> tuple[IntegrityFlag, ...]:
    unique: dict[str, IntegrityFlag] = {}
    for flag in flags:
        unique.setdefault(flag.id, flag)
    return tuple(unique[key] for key in sorted(unique))
