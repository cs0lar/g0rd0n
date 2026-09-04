import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from g0rd0n.evaluation import (
    BenchmarkRole,
    EvaluationPurpose,
    EvaluationRequest,
    GateKind,
    IsolatedEvaluator,
)
from g0rd0n.methods import ExecutionReceipt, ExecutionStatus


SHORTCUT = "a" * 64
BALANCED = "b" * 64
REGRESSOR = "c" * 64


def measurement(mean: float, lower: float | None = None, upper: float | None = None):
    return {
        "mean": mean,
        "confidence_interval_95": [mean if lower is None else lower, mean if upper is None else upper],
    }


def benchmark(benchmark_id, role, shortcut, balanced, regressor=None, **gate):
    return {
        "id": benchmark_id,
        "role": role,
        "baseline": 0.0,
        "optimum": 1.0,
        "measurements": {
            SHORTCUT: shortcut,
            BALANCED: balanced,
            REGRESSOR: balanced if regressor is None else regressor,
        },
        **gate,
    }


def private_suite():
    return {
        "campaign_id": "campaign:isolation-v1",
        "aggregate_rule": "geometric_mean_positive_headroom",
        "benchmarks": [
            benchmark("optimization:a", "optimization", measurement(1.0), measurement(0.6, 0.55, 0.65), measurement(0.9, 0.85, 0.95)),
            benchmark("optimization:b", "optimization", measurement(0.0), measurement(0.5, 0.45, 0.55), measurement(0.9, 0.85, 0.95)),
            benchmark("validation:hidden", "validation", measurement(0.1), measurement(0.55, 0.5, 0.6)),
            benchmark("test:untouched", "test", measurement(0.0), measurement(0.52, 0.47, 0.57)),
            benchmark(
                "gate:capability",
                "capability_gate",
                measurement(-0.2, -0.3, -0.1),
                measurement(-0.01, -0.05, 0.03),
                measurement(-0.2, -0.3, -0.1),
                gate_kind="capability",
                minimum_headroom=0.0,
            ),
            benchmark(
                "gate:safety",
                "safety_gate",
                measurement(0.9, 0.85, 0.95),
                measurement(0.8, 0.75, 0.85),
                gate_kind="safety",
                minimum_headroom=0.7,
            ),
        ],
    }


@unittest.skipUnless(os.name == "posix", "inherited descriptor isolation requires POSIX")
class IsolatedEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.private_path = self.root / "private-suite.json"
        self.private_path.write_text(json.dumps(private_suite()), encoding="utf-8")
        self.private_fd = os.open(self.private_path, os.O_RDONLY)
        self.private_path.chmod(0)
        self.evaluator = IsolatedEvaluator(self.private_fd)

    def tearDown(self):
        os.close(self.private_fd)
        self.temporary.cleanup()

    def request(self, artifact_hash: str, purpose: EvaluationPurpose) -> EvaluationRequest:
        return EvaluationRequest("campaign:isolation-v1", artifact_hash, purpose)

    def test_worker_receives_artifact_reference_and_returns_aggregates_only(self):
        with self.assertRaises(PermissionError):
            self.private_path.read_text(encoding="utf-8")
        request = self.request(BALANCED, EvaluationPurpose.OPTIMIZE)
        self.assertEqual(set(request.to_dict()), {"campaign_id", "artifact_hash", "purpose"})
        report = self.evaluator.evaluate(request)
        serialized = json.dumps(
            {
                "scores": [score.benchmark_id for score in report.scores],
                "aggregate": report.aggregate_headroom_closed,
            }
        )
        self.assertNotIn("measurements", serialized)
        self.assertNotIn(str(self.private_path), serialized)
        self.assertEqual(
            {score.role for score in report.scores},
            {BenchmarkRole.OPTIMIZATION, BenchmarkRole.CAPABILITY_GATE, BenchmarkRole.SAFETY_GATE},
        )

    def test_request_can_bind_directly_to_successful_phase_16_receipt(self):
        receipt = ExecutionReceipt(
            "receipt:1",
            "method:1",
            "approval:1",
            "d" * 64,
            "e" * 64,
            BALANCED,
            ExecutionStatus.SUCCEEDED,
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
        request = EvaluationRequest.from_receipt(
            "campaign:isolation-v1", receipt, EvaluationPurpose.OPTIMIZE
        )
        self.assertEqual(request.artifact_hash, receipt.result_artifact_hash)
        failed = ExecutionReceipt(
            "receipt:2",
            "method:1",
            "approval:1",
            "d" * 64,
            "e" * 64,
            BALANCED,
            ExecutionStatus.FAILED,
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(ValueError, "successful approved execution"):
            EvaluationRequest.from_receipt(
                "campaign:isolation-v1", failed, EvaluationPurpose.OPTIMIZE
            )

    def test_capability_veto_overrides_high_primary_score(self):
        report = self.evaluator.evaluate(self.request(REGRESSOR, EvaluationPurpose.OPTIMIZE))
        self.assertAlmostEqual(report.aggregate_headroom_closed, 0.9)
        self.assertFalse(report.eligible)
        capability = next(item for item in report.gates if item.kind is GateKind.CAPABILITY)
        self.assertFalse(capability.passed)

    def test_multiple_optimization_benchmarks_penalize_seeded_shortcut(self):
        shortcut = self.evaluator.evaluate(self.request(SHORTCUT, EvaluationPurpose.OPTIMIZE))
        balanced = self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.OPTIMIZE))
        self.assertEqual(shortcut.aggregate_headroom_closed, 0.0)
        self.assertAlmostEqual(balanced.aggregate_headroom_closed, (0.6 * 0.5) ** 0.5)
        self.assertGreater(balanced.aggregate_headroom_closed, shortcut.aggregate_headroom_closed)

    def test_validation_selects_and_final_test_never_selects(self):
        with self.assertRaisesRegex(ValueError, "prior validation"):
            self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.CONFIRM))
        selection = self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.SELECT))
        self.assertTrue(selection.eligible)
        self.assertTrue(selection.selection.used_for_selection)
        self.assertEqual(
            {score.role for score in selection.scores},
            {BenchmarkRole.VALIDATION, BenchmarkRole.CAPABILITY_GATE, BenchmarkRole.SAFETY_GATE},
        )
        confirmation = self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.CONFIRM))
        self.assertFalse(confirmation.selection.used_for_selection)
        self.assertEqual(
            {score.role for score in confirmation.scores},
            {BenchmarkRole.TEST, BenchmarkRole.CAPABILITY_GATE, BenchmarkRole.SAFETY_GATE},
        )
        with self.assertRaisesRegex(ValueError, "already been consumed"):
            self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.CONFIRM))

    def test_component_scores_and_uncertainty_remain_visible(self):
        report = self.evaluator.evaluate(self.request(BALANCED, EvaluationPurpose.OPTIMIZE))
        by_id = {score.benchmark_id: score for score in report.scores}
        self.assertEqual(by_id["optimization:a"].confidence_interval_95, (0.55, 0.65))
        self.assertEqual(by_id["optimization:a"].headroom_interval_95, (0.55, 0.65))
        self.assertEqual(len(report.gates), 2)
        self.assertEqual(report.gates[0].minimum_headroom, 0.0)
        self.assertTrue(all(item.reason for item in report.gates))


if __name__ == "__main__":
    unittest.main()
