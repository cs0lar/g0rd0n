"""Aggregate-only evaluation through a separate worker and inherited private data."""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from g0rd0n.methods import ExecutionReceipt, ExecutionStatus
from g0rd0n.research.ledger import canonical_json


class BenchmarkRole(StrEnum):
    OPTIMIZATION = "optimization"
    VALIDATION = "validation"
    TEST = "test"
    CAPABILITY_GATE = "capability_gate"
    SAFETY_GATE = "safety_gate"


class GateKind(StrEnum):
    CAPABILITY = "capability"
    SAFETY = "safety"


class EvaluationPurpose(StrEnum):
    OPTIMIZE = "optimize"
    SELECT = "select"
    CONFIRM = "confirm"


class AggregateRule(StrEnum):
    GEOMETRIC_MEAN_POSITIVE_HEADROOM = "geometric_mean_positive_headroom"


_PURPOSE_ROLE = {
    EvaluationPurpose.OPTIMIZE: BenchmarkRole.OPTIMIZATION,
    EvaluationPurpose.SELECT: BenchmarkRole.VALIDATION,
    EvaluationPurpose.CONFIRM: BenchmarkRole.TEST,
}
_GATE_ROLES = frozenset({BenchmarkRole.CAPABILITY_GATE, BenchmarkRole.SAFETY_GATE})


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _finite(value: Any, field: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    campaign_id: str
    artifact_hash: str
    purpose: EvaluationPurpose

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id is required")
        if len(self.artifact_hash) != 64 or any(character not in "0123456789abcdef" for character in self.artifact_hash):
            raise ValueError("artifact_hash must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {"campaign_id": self.campaign_id, "artifact_hash": self.artifact_hash, "purpose": self.purpose.value}

    @classmethod
    def from_receipt(
        cls,
        campaign_id: str,
        receipt: ExecutionReceipt,
        purpose: EvaluationPurpose,
    ) -> "EvaluationRequest":
        if receipt.status is not ExecutionStatus.SUCCEEDED:
            raise ValueError("only a successful approved execution can be evaluated")
        return cls(campaign_id, receipt.result_artifact_hash, purpose)


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    benchmark_id: str
    role: BenchmarkRole
    mean: float
    confidence_interval_95: tuple[float, float]
    headroom_closed: float
    headroom_interval_95: tuple[float, float]


@dataclass(frozen=True, slots=True)
class GateVerdict:
    benchmark_id: str
    kind: GateKind
    minimum_headroom: float
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SelectionRecord:
    campaign_id: str
    artifact_hash: str
    purpose: EvaluationPurpose
    used_for_selection: bool
    benchmark_role: BenchmarkRole


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    request: EvaluationRequest
    scores: tuple[BenchmarkScore, ...]
    gates: tuple[GateVerdict, ...]
    aggregate_rule: AggregateRule
    aggregate_headroom_closed: float | None
    eligible: bool
    selection: SelectionRecord

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvaluationReport":
        request_value = value["request"]
        request = EvaluationRequest(
            _text(request_value.get("campaign_id"), "campaign_id"),
            _text(request_value.get("artifact_hash"), "artifact_hash"),
            EvaluationPurpose(request_value["purpose"]),
        )
        scores = tuple(
            BenchmarkScore(
                _text(item.get("benchmark_id"), "benchmark_id"),
                BenchmarkRole(item["role"]),
                _finite(item["mean"], "mean"),
                tuple(_finite(point, "confidence_interval_95") for point in item["confidence_interval_95"]),
                _finite(item["headroom_closed"], "headroom_closed"),
                tuple(_finite(point, "headroom_interval_95") for point in item["headroom_interval_95"]),
            )
            for item in value["scores"]
        )
        gates = tuple(
            GateVerdict(
                _text(item.get("benchmark_id"), "gate.benchmark_id"),
                GateKind(item["kind"]),
                _finite(item["minimum_headroom"], "gate.minimum_headroom"),
                bool(item["passed"]),
                _text(item.get("reason"), "gate.reason"),
            )
            for item in value["gates"]
        )
        aggregate = value.get("aggregate_headroom_closed")
        role = _PURPOSE_ROLE[request.purpose]
        eligible = bool(value["eligible"])
        selection = SelectionRecord(
            request.campaign_id,
            request.artifact_hash,
            request.purpose,
            request.purpose is EvaluationPurpose.SELECT and eligible,
            role,
        )
        return cls(
            request,
            scores,
            gates,
            AggregateRule(value["aggregate_rule"]),
            None if aggregate is None else _finite(aggregate, "aggregate"),
            eligible,
            selection,
        )


class IsolatedEvaluator:
    """Trusted broker; private_fd must not be made available to research code."""

    def __init__(self, private_fd: int, *, worker_command: tuple[str, ...] | None = None) -> None:
        try:
            descriptor = os.fstat(private_fd)
        except OSError as error:
            raise ValueError("private_fd must be an open descriptor") from error
        if not stat.S_ISREG(descriptor.st_mode):
            raise ValueError("private_fd must refer to a regular file")
        self._private_fd = private_fd
        self._worker_command = worker_command or (sys.executable, "-m", "g0rd0n.evaluation.isolated_worker")
        self._history: list[SelectionRecord] = []

    def history(self) -> tuple[SelectionRecord, ...]:
        return tuple(self._history)

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        if request.purpose is EvaluationPurpose.CONFIRM:
            selected = any(
                item.campaign_id == request.campaign_id
                and item.artifact_hash == request.artifact_hash
                and item.purpose is EvaluationPurpose.SELECT
                and item.used_for_selection
                for item in self._history
            )
            if not selected:
                raise ValueError("final test requires a prior validation selection record")
            if any(item.campaign_id == request.campaign_id and item.purpose is EvaluationPurpose.CONFIRM for item in self._history):
                raise ValueError("final test has already been consumed for this campaign")
        os.lseek(self._private_fd, 0, os.SEEK_SET)
        worker_environment = {
            key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH"}
        }
        worker_environment["G0RD0N_PRIVATE_EVALUATION_FD"] = str(self._private_fd)
        completed = subprocess.run(
            self._worker_command,
            input=canonical_json(request.to_dict()),
            capture_output=True,
            pass_fds=(self._private_fd,),
            env=worker_environment,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"isolated evaluator failed: {error}")
        try:
            value = json.loads(completed.stdout)
            if not isinstance(value, Mapping):
                raise TypeError("report is not an object")
            report = EvaluationReport.from_dict(value)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("isolated evaluator returned an invalid aggregate report") from error
        if report.request != request:
            raise RuntimeError("isolated evaluator response does not match request")
        expected_roles = {_PURPOSE_ROLE[request.purpose], *_GATE_ROLES}
        if not report.scores or any(score.role not in expected_roles for score in report.scores):
            raise RuntimeError("isolated evaluator disclosed an unexpected benchmark role")
        self._history.append(report.selection)
        return report
