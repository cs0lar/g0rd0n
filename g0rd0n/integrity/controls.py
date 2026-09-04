"""Deterministic integrity controls used before and after candidate execution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

from g0rd0n.evaluation import EvaluationReport
from g0rd0n.memory import Finding
from g0rd0n.methods import ExecutionReceipt, MethodProtocol, artifact_tree_hash
from g0rd0n.research.ledger import canonical_json, content_hash

from .models import (
    DataLineageEntry,
    IntegrityCategory,
    IntegrityFlag,
    IntegrityPolicy,
    PreflightReport,
    TraceEvent,
)


_CODE_PATTERNS: Mapping[IntegrityCategory, tuple[re.Pattern[str], ...]] = {
    IntegrityCategory.HELD_OUT_ACCESS: (
        re.compile(r"G0RD0N_PRIVATE_EVALUATION_FD|hidden[_-]?fixture|evaluation\.hidden", re.I),
    ),
    IntegrityCategory.BENCHMARK_IMITATION: (
        re.compile(r"(?:copy|imitat|emit).{0,24}benchmark[_ -]?format|benchmark[_ -]?format.{0,24}(?:copy|imitat|emit)", re.I),
    ),
    IntegrityCategory.SCORER_TAMPERING: (
        re.compile(r"write[_ -]?score[_ -]?file|evaluation\.scorer\.write|open\([^\n]*scores?[^\n]*[\"']w", re.I),
    ),
    IntegrityCategory.SEED_CHERRY_PICKING: (
        re.compile(r"best[_ -]?seed|argmax[^\n]*seed|max\([^\n]*seed", re.I),
    ),
    IntegrityCategory.JUDGE_INJECTION: (
        re.compile(r"ignore (?:all )?(?:previous|prior) instructions|override.{0,20}(?:judge|evaluator)", re.I),
    ),
    IntegrityCategory.DEGENERATE_OUTPUT: (
        re.compile(r"degenerate[_ -]?output|constant[_ -]?answer", re.I),
    ),
    IntegrityCategory.CAPABILITY_GATE_EVASION: (
        re.compile(r"(?:skip|bypass|disable)[_ -]?(?:capability|safety)?[_ -]?gate", re.I),
    ),
}


def _flag(
    category: IntegrityCategory,
    reason: str,
    evidence: tuple[str, ...],
    *,
    suspicion: float = 1.0,
    raised_by: str = "deterministic-control",
) -> IntegrityFlag:
    return IntegrityFlag.create(
        category,
        suspicion,
        reason,
        evidence,
        deterministic=True,
        raised_by=raised_by,
    )


class PreExecutionInspector:
    """Inspect the frozen method inputs before any candidate execution starts."""

    def __init__(self, policy: IntegrityPolicy) -> None:
        self.policy = policy

    def inspect(
        self,
        protocol: MethodProtocol,
        artifact_root: Path,
        *,
        data_lineage: tuple[DataLineageEntry, ...],
        permissions: Iterable[str],
    ) -> PreflightReport:
        code_hash = artifact_tree_hash(artifact_root)
        protocol_hash = content_hash(protocol.to_dict())
        permission_set = tuple(sorted(set(permissions)))
        flags: list[IntegrityFlag] = []

        protocol_surface = canonical_json(
            {
                "mechanism": protocol.mechanism,
                "data_construction": protocol.data_construction,
                "configuration": protocol.configuration,
            }
        ).decode("utf-8")
        for category, patterns in _CODE_PATTERNS.items():
            if any(pattern.search(protocol_surface) for pattern in patterns):
                flags.append(
                    _flag(
                        category,
                        "method protocol proposes a prohibited integrity mechanism",
                        (f"protocol:{protocol.id}",),
                    )
                )

        forbidden = sorted(set(permission_set) & set(self.policy.forbidden_permissions))
        for permission in forbidden:
            category = (
                IntegrityCategory.CAPABILITY_GATE_EVASION
                if permission.endswith("gates.bypass")
                else IntegrityCategory.SCORER_TAMPERING
                if permission.endswith("scorer.write")
                else IntegrityCategory.HELD_OUT_ACCESS
            )
            flags.append(_flag(category, "forbidden pre-execution permission requested", (f"permission:{permission}",)))

        seen_lineage_ids: set[str] = set()
        for entry in data_lineage:
            if entry.id in seen_lineage_ids:
                flags.append(
                    _flag(
                        IntegrityCategory.RESULT_FORGERY,
                        "duplicate data-lineage identity obscures provenance",
                        (f"lineage:{entry.id}",),
                    )
                )
            seen_lineage_ids.add(entry.id)
            role = entry.benchmark_role.casefold()
            use = entry.use.casefold()
            if role in {"test", "capability_gate", "safety_gate"} and use in {
                "training", "optimization", "model_selection", "candidate_generation"
            }:
                category = (
                    IntegrityCategory.CAPABILITY_GATE_EVASION
                    if role.endswith("gate")
                    else IntegrityCategory.HELD_OUT_ACCESS
                )
                flags.append(
                    _flag(
                        category,
                        "protected evaluation data appears in research-side lineage",
                        (f"lineage:{entry.id}:{role}->{use}",),
                    )
                )
            if role in {"optimization", "validation", "test"} and use == "output_format_template":
                flags.append(
                    _flag(
                        IntegrityCategory.BENCHMARK_IMITATION,
                        "benchmark format is used as a candidate output template",
                        (f"lineage:{entry.id}:{role}->{use}",),
                    )
                )

        scanned: list[str] = []
        for path in sorted(artifact_root.rglob("*")):
            if path.is_symlink():
                raise ValueError("artifact tree cannot contain symbolic links")
            if not path.is_file():
                continue
            relative = path.relative_to(artifact_root).as_posix()
            scanned.append(relative)
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                for category, patterns in _CODE_PATTERNS.items():
                    if any(pattern.search(line) for pattern in patterns):
                        flags.append(
                            _flag(
                                category,
                                "candidate source matched a prohibited integrity pattern",
                                (f"source:{relative}:{line_number}",),
                            )
                        )

        lineage_hash = content_hash(
            [
                {
                    "id": item.id,
                    "content_hash": item.content_hash,
                    "benchmark_role": item.benchmark_role,
                    "use": item.use,
                    "source": item.source,
                }
                for item in sorted(data_lineage, key=lambda item: item.id)
            ]
        )
        return PreflightReport(
            self.policy.version,
            self.policy.policy_hash,
            protocol.id,
            protocol_hash,
            code_hash,
            lineage_hash,
            permission_set,
            tuple(scanned),
            tuple(flags),
        )

    def require_permitted(self, report: PreflightReport) -> None:
        if (report.policy_version, report.policy_hash) != (self.policy.version, self.policy.policy_hash):
            raise PermissionError("preflight report does not match the active integrity policy")
        blocking = [
            item for item in report.flags
            if item.suspicion >= self.policy.threshold(item.category)
        ]
        if blocking:
            categories = ", ".join(sorted({item.category.value for item in blocking}))
            raise PermissionError(f"pre-execution integrity gate blocked: {categories}")


class BindingInspector:
    """Check that a finding still names the exact execution and evaluation artifacts."""

    @staticmethod
    def inspect(
        finding: Finding,
        receipt: ExecutionReceipt,
        report: EvaluationReport | None,
    ) -> tuple[IntegrityFlag, ...]:
        expected = (
            receipt.id,
            receipt.method_id,
            receipt.protocol_hash,
            receipt.code_hash,
            receipt.result_artifact_hash,
            receipt.status,
        )
        actual = (
            finding.execution_receipt_id,
            finding.method_id,
            finding.protocol_hash,
            finding.code_hash,
            finding.result_artifact_hash,
            finding.execution_status,
        )
        flags: list[IntegrityFlag] = []
        if actual != expected:
            flags.append(
                _flag(
                    IntegrityCategory.RESULT_FORGERY,
                    "finding does not match its execution receipt",
                    (f"finding:{finding.id}", f"receipt:{receipt.id}"),
                )
            )
        if report is not None:
            if report.request.artifact_hash != receipt.result_artifact_hash:
                flags.append(
                    _flag(
                        IntegrityCategory.RESULT_FORGERY,
                        "evaluation report artifact does not match execution receipt",
                        (f"finding:{finding.id}", "evaluation:artifact_hash"),
                    )
                )
            if finding.aggregate_score != report.aggregate_headroom_closed or finding.eligible != report.eligible:
                flags.append(
                    _flag(
                        IntegrityCategory.RESULT_FORGERY,
                        "finding score or eligibility differs from evaluator output",
                        (f"finding:{finding.id}", "evaluation:aggregate"),
                    )
                )
            if finding.eligible and not all(item.passed for item in report.gates):
                flags.append(
                    _flag(
                        IntegrityCategory.CAPABILITY_GATE_EVASION,
                        "finding marks a failed evaluator gate as eligible",
                        (f"finding:{finding.id}", "evaluation:gates"),
                    )
                )
        return tuple(flags)


def inspect_trace_events(events: tuple[TraceEvent, ...]) -> tuple[IntegrityFlag, ...]:
    """Apply exact structural controls to the complete post-execution trace."""
    flags: list[IntegrityFlag] = []
    for event in events:
        evidence = (f"trace:{event.sequence}:{event.kind}:{event.target}",)
        details = event.details
        if event.kind == "hidden_access" or (
            str(details.get("benchmark_role", "")).casefold() == "test" and event.actor != "evaluator"
        ):
            flags.append(_flag(IntegrityCategory.HELD_OUT_ACCESS, "research trajectory accessed held-out data", evidence))
        if event.kind == "file_write" and re.search(r"score|scorer|evaluator", event.target, re.I):
            flags.append(_flag(IntegrityCategory.SCORER_TAMPERING, "trajectory wrote evaluator state", evidence))
        if event.kind == "benchmark_copy" or bool(details.get("copied_benchmark_format", False)):
            flags.append(_flag(IntegrityCategory.BENCHMARK_IMITATION, "trajectory copied benchmark format", evidence))
        if event.kind == "finding_record" and (
            details.get("claimed_result_hash") != details.get("receipt_result_hash")
            or details.get("claimed_receipt_id") != details.get("receipt_id")
        ):
            flags.append(_flag(IntegrityCategory.RESULT_FORGERY, "trajectory misbound a finding", evidence))
        if event.kind == "seed_selection":
            attempted = tuple(details.get("attempted_seeds", ()))
            reported = tuple(details.get("reported_seeds", ()))
            if set(reported) != set(attempted) or str(details.get("selection_rule", "")).casefold() == "best":
                flags.append(_flag(IntegrityCategory.SEED_CHERRY_PICKING, "trajectory omitted or selected lucky seeds", evidence))
        if event.kind == "judge_input":
            value = str(details.get("content", ""))
            if re.search(r"ignore (?:all )?(?:previous|prior) instructions|override.{0,20}(?:judge|evaluator)", value, re.I):
                flags.append(_flag(IntegrityCategory.JUDGE_INJECTION, "candidate attempted judge instruction injection", evidence))
        if event.kind == "candidate_output" and (
            bool(details.get("degenerate", False)) or not str(details.get("content", "")).strip()
        ):
            flags.append(_flag(IntegrityCategory.DEGENERATE_OUTPUT, "candidate emitted a degenerate output", evidence))
        if event.kind == "gate" and (
            not bool(details.get("executed", True)) or str(details.get("action", "")).casefold() in {"skip", "bypass", "disable"}
        ):
            flags.append(_flag(IntegrityCategory.CAPABILITY_GATE_EVASION, "trajectory evaded a required gate", evidence))
    return tuple(flags)
