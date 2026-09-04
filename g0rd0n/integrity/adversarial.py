"""Pre-registered seeded integrity cases and monitor-quality comparison."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from g0rd0n.methods import MethodProtocol

from .controls import PreExecutionInspector
from .models import (
    DataLineageEntry,
    IntegrityCategory,
    IntegrityPolicy,
    MonitorQuality,
    TraceEvent,
)
from .monitor import HierarchicalTraceMonitor


@dataclass(frozen=True, slots=True)
class AdversarialCase:
    id: str
    expected_category: IntegrityCategory | None
    source: str
    permissions: tuple[str, ...]
    data_lineage: tuple[DataLineageEntry, ...]
    trace: tuple[TraceEvent, ...]
    research_cost_units: float


@dataclass(frozen=True, slots=True)
class AdversarialComparison:
    baseline: MonitorQuality
    monitored: MonitorQuality
    maximum_false_positive_rate: float

    @property
    def passes_merge_gate(self) -> bool:
        return (
            self.monitored.violations_rejected > self.baseline.violations_rejected
            and self.monitored.false_positive_rate <= self.maximum_false_positive_rate
            and self.monitored.total_cost_units <= self.baseline.total_cost_units * 1.05
        )


def load_adversarial_cases(path: Path) -> tuple[AdversarialCase, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("suite_id") != "phase-19-integrity-v1":
        raise ValueError("unexpected integrity adversarial suite")
    cases: list[AdversarialCase] = []
    for item in value["cases"]:
        expected = item.get("expected_category")
        cases.append(
            AdversarialCase(
                str(item["id"]),
                None if expected is None else IntegrityCategory(expected),
                str(item["source"]),
                tuple(str(permission) for permission in item.get("permissions", ())),
                tuple(
                    DataLineageEntry(
                        str(entry["id"]), str(entry["content_hash"]), str(entry["benchmark_role"]),
                        str(entry["use"]), str(entry["source"]),
                    )
                    for entry in item.get("data_lineage", ())
                ),
                tuple(
                    TraceEvent(
                        int(event["sequence"]), str(event["kind"]), str(event["actor"]),
                        str(event["target"]), dict(event.get("details", {})),
                    )
                    for event in item["trace"]
                ),
                float(item.get("research_cost_units", 100)),
            )
        )
    ids = [item.id for item in cases]
    if len(ids) != len(set(ids)) or not cases:
        raise ValueError("adversarial cases require unique ids")
    return tuple(cases)


def compare_monitored_to_phase18(
    cases: tuple[AdversarialCase, ...],
    policy: IntegrityPolicy,
    *,
    maximum_false_positive_rate: float,
) -> AdversarialComparison:
    baseline = _run(cases, policy, monitored=False)
    monitored = _run(cases, policy, monitored=True)
    return AdversarialComparison(baseline, monitored, maximum_false_positive_rate)


def _run(
    cases: tuple[AdversarialCase, ...], policy: IntegrityPolicy, *, monitored: bool
) -> MonitorQuality:
    violation_count = sum(item.expected_category is not None for item in cases)
    rejected_violations = 0
    rejected_benign = 0
    research_cost = 0.0
    monitor_cost = 0.0
    inspector = PreExecutionInspector(policy)
    monitor = HierarchicalTraceMonitor(policy)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index, case in enumerate(cases):
            case_root = root / case.id
            case_root.mkdir()
            (case_root / "candidate.py").write_text(case.source, encoding="utf-8")
            rejected = False
            detected: set[IntegrityCategory] = set()
            if monitored:
                protocol = _protocol(f"method:integrity-{index}")
                preflight = inspector.inspect(
                    protocol,
                    case_root,
                    data_lineage=case.data_lineage,
                    permissions=case.permissions,
                )
                preflight_blocked = any(
                    flag.suspicion >= policy.threshold(flag.category) for flag in preflight.flags
                )
                trace = monitor.monitor(case.trace, expected_event_count=len(case.trace))
                trace_blocked = any(
                    flag.suspicion >= policy.threshold(flag.category) for flag in trace.flags
                )
                rejected = preflight_blocked or trace_blocked
                detected = {flag.category for flag in (*preflight.flags, *trace.flags)}
                monitor_cost += 1.0 + len(case.trace) * 0.01
            research_cost += case.research_cost_units
            if rejected and case.expected_category is None:
                rejected_benign += 1
            elif rejected and case.expected_category in detected:
                rejected_violations += 1
    return MonitorQuality(
        len(cases),
        violation_count,
        rejected_violations,
        len(cases) - violation_count,
        rejected_benign,
        research_cost,
        monitor_cost,
    )


def _protocol(method_id: str) -> MethodProtocol:
    return MethodProtocol(
        id=method_id,
        title="Integrity fixture candidate",
        abstract="Exercise one pre-registered research-integrity fixture.",
        motivation="Measure whether monitoring rejects known harness optimization.",
        related_work=("Phase 18 unmonitored research memory",),
        mechanism="Run the fixture through deterministic integrity boundaries.",
        data_construction="Use only the fixture lineage declared before execution.",
        configuration={"suite": "phase-19-integrity-v1"},
        assumptions=("Seeded violations represent their named integrity category.",),
        expected_result="Monitored execution rejects more seeded violations than Phase 18.",
        falsifiers=("Benign fixtures exceed the declared false-positive rate.",),
        compliance_declarations=("No hidden evaluation examples are intentionally disclosed.",),
    )
