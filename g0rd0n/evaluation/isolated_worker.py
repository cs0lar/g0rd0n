"""Private-suite worker for :mod:`g0rd0n.evaluation.isolation`."""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Mapping

from g0rd0n.research.ledger import canonical_json

from .isolation import AggregateRule, BenchmarkRole, EvaluationPurpose, GateKind, _GATE_ROLES, _PURPOSE_ROLE


def _headroom(score: float, baseline: float, optimum: float) -> float:
    if optimum == baseline:
        raise ValueError("benchmark optimum must differ from baseline")
    return (score - baseline) / (optimum - baseline)


def _score(benchmark: Mapping[str, Any], artifact_hash: str) -> dict[str, Any]:
    measurement = benchmark["measurements"][artifact_hash]
    mean = float(measurement["mean"])
    interval = tuple(float(value) for value in measurement["confidence_interval_95"])
    if len(interval) != 2 or interval[0] > mean or mean > interval[1] or any(not math.isfinite(value) for value in (mean, *interval)):
        raise ValueError("invalid score estimate")
    baseline = float(benchmark["baseline"])
    optimum = float(benchmark["optimum"])
    if not math.isfinite(baseline) or not math.isfinite(optimum) or baseline == optimum:
        raise ValueError("benchmark baseline and distinct optimum must be finite")
    headroom_interval = sorted((_headroom(interval[0], baseline, optimum), _headroom(interval[1], baseline, optimum)))
    return {
        "benchmark_id": str(benchmark["id"]),
        "role": str(benchmark["role"]),
        "mean": mean,
        "confidence_interval_95": interval,
        "headroom_closed": _headroom(mean, baseline, optimum),
        "headroom_interval_95": headroom_interval,
    }


def evaluate(private: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if request.get("campaign_id") != private.get("campaign_id"):
        raise ValueError("campaign does not match private evaluation suite")
    artifact_hash = str(request["artifact_hash"])
    purpose = EvaluationPurpose(request["purpose"])
    aggregate_rule = AggregateRule(private["aggregate_rule"])
    target_role = _PURPOSE_ROLE[purpose]
    benchmark_ids = [str(item["id"]) for item in private["benchmarks"]]
    if len(benchmark_ids) != len(set(benchmark_ids)):
        raise ValueError("private suite benchmark ids must be unique")
    selected = [
        benchmark
        for benchmark in private["benchmarks"]
        if BenchmarkRole(benchmark["role"]) in {target_role, *_GATE_ROLES}
    ]
    if not any(BenchmarkRole(item["role"]) is target_role for item in selected):
        raise ValueError("private suite has no benchmark for requested purpose")
    scores = [_score(item, artifact_hash) for item in selected]
    by_id = {item["benchmark_id"]: item for item in scores}
    gates: list[dict[str, Any]] = []
    for benchmark in selected:
        if BenchmarkRole(benchmark["role"]) not in _GATE_ROLES:
            continue
        score = by_id[str(benchmark["id"])]
        threshold = float(benchmark["minimum_headroom"])
        kind = GateKind(benchmark["gate_kind"])
        role = BenchmarkRole(benchmark["role"])
        expected_role = BenchmarkRole.CAPABILITY_GATE if kind is GateKind.CAPABILITY else BenchmarkRole.SAFETY_GATE
        if role is not expected_role:
            raise ValueError("gate kind does not match benchmark role")
        if kind is GateKind.CAPABILITY:
            passed = score["headroom_interval_95"][1] >= threshold
            reason = "no statistically confirmed regression" if passed else "confidence interval is entirely below capability floor"
        else:
            passed = score["headroom_interval_95"][0] >= threshold
            reason = "safety floor met with declared uncertainty" if passed else "safety floor is not established"
        gates.append(
            {
                "benchmark_id": score["benchmark_id"],
                "kind": kind.value,
                "minimum_headroom": threshold,
                "passed": passed,
                "reason": reason,
            }
        )
    if {item["kind"] for item in gates} != {GateKind.CAPABILITY.value, GateKind.SAFETY.value}:
        raise ValueError("private suite requires capability and safety gates")
    primary = [item["headroom_closed"] for item in scores if item["role"] == target_role.value]
    if aggregate_rule is not AggregateRule.GEOMETRIC_MEAN_POSITIVE_HEADROOM:
        raise ValueError("unsupported aggregate rule")
    aggregate = 0.0 if any(value <= 0 for value in primary) else math.prod(primary) ** (1 / len(primary))
    return {
        "request": dict(request),
        "scores": scores,
        "gates": gates,
        "aggregate_rule": aggregate_rule.value,
        "aggregate_headroom_closed": aggregate,
        "eligible": all(item["passed"] for item in gates),
    }


def main() -> int:
    descriptor_text = os.environ.pop("G0RD0N_PRIVATE_EVALUATION_FD", None)
    if descriptor_text is None:
        print("private evaluation descriptor is required", file=sys.stderr)
        return 2
    try:
        with os.fdopen(int(descriptor_text), "r", encoding="utf-8", closefd=False) as stream:
            private = json.load(stream)
        request = json.load(sys.stdin.buffer)
        if not isinstance(private, Mapping) or not isinstance(request, Mapping):
            raise ValueError("evaluation inputs must be objects")
        report = evaluate(private, request)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
