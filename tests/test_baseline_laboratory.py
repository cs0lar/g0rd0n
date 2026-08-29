import json
import statistics
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from g0rd0n.evaluation.analysis import (
    MetricDirection,
    MetricSpec,
    paired_comparison,
    pareto_front,
)
from g0rd0n.evaluation.harness import BenchmarkHarness
from g0rd0n.evaluation.manifest import BaselineFamily, BaselineManifest, ReproductionSpec, TaskFamily
from g0rd0n.evaluation.report import markdown_report
from g0rd0n.evaluation.toy import AffineRuleCandidate, LookupBaseline


ROOT = Path(__file__).parents[1]
BASELINE_PATH = ROOT / "benchmarks" / "manifests" / "toy-lookup-baseline.json"
CANDIDATE_PATH = ROOT / "benchmarks" / "manifests" / "toy-affine-candidate.json"


class BaselineLaboratoryTests(unittest.TestCase):
    def setUp(self):
        self.baseline_manifest = BaselineManifest.from_json(BASELINE_PATH)
        self.candidate_manifest = BaselineManifest.from_json(CANDIDATE_PATH)

    def test_manifest_captures_required_reproducibility_fields(self):
        manifest = self.baseline_manifest
        self.assertEqual(manifest.benchmark.task_family, TaskFamily.ALGORITHMIC_GENERALIZATION)
        self.assertEqual(len(manifest.seeds), 10)
        self.assertTrue(manifest.hardware.architecture)
        self.assertTrue(manifest.environment.python_version)
        self.assertTrue(manifest.reproduction.command)
        self.assertIn("No energy claim", manifest.energy_boundary)
        with self.assertRaisesRegex(ValueError, "weights digest"):
            replace(manifest, family=BaselineFamily.TRANSFORMER, weights_digest=None)
        with self.assertRaisesRegex(ValueError, "declared together"):
            replace(
                manifest.reproduction,
                container_image="example.invalid/model:1",
                container_digest=None,
            )

    def test_seeded_harness_produces_expected_toy_rankings(self):
        harness = BenchmarkHarness()
        baseline = harness.run(self.baseline_manifest, LookupBaseline())
        candidate = harness.run(self.candidate_manifest, AffineRuleCandidate())
        self.assertEqual(baseline.metric_values("accuracy"), (0.0,) * 10)
        self.assertEqual(candidate.metric_values("accuracy"), (1.0,) * 10)
        self.assertEqual([trial.seed for trial in baseline.trials], list(range(10)))
        self.assertTrue(baseline.environment.python_version)
        self.assertTrue(baseline.environment.architecture)

    def test_paired_statistics_report_uncertainty_and_reject_mismatched_studies(self):
        harness = BenchmarkHarness()
        baseline = harness.run(self.baseline_manifest, LookupBaseline())
        candidate = harness.run(self.candidate_manifest, AffineRuleCandidate())
        comparison = paired_comparison(
            baseline,
            candidate,
            "accuracy",
            direction=MetricDirection.MAXIMIZE,
        )
        self.assertEqual(comparison.paired_samples, 10)
        self.assertEqual(comparison.mean_improvement, 1.0)
        self.assertEqual(comparison.confidence_interval_95, (1.0, 1.0))
        self.assertAlmostEqual(comparison.randomization_p_value, 2 / (2**10))
        incompatible = replace(candidate, benchmark_version="2")
        with self.assertRaisesRegex(ValueError, "same benchmark"):
            paired_comparison(
                baseline,
                incompatible,
                "accuracy",
                direction=MetricDirection.MAXIMIZE,
            )

    def test_pareto_front_uses_capability_and_resource_directions(self):
        harness = BenchmarkHarness()
        baseline = harness.run(self.baseline_manifest, LookupBaseline())
        candidate = harness.run(self.candidate_manifest, AffineRuleCandidate())

        def point(result):
            return {
                "accuracy": statistics.mean(result.metric_values("accuracy")),
                "operations": statistics.mean(trial.usage.operations for trial in result.trials),
                "memory": statistics.mean(trial.usage.peak_memory_bytes for trial in result.trials),
                "latency": statistics.mean(trial.usage.modelled_latency_ms for trial in result.trials),
            }

        metrics = (
            MetricSpec("accuracy", MetricDirection.MAXIMIZE),
            MetricSpec("operations", MetricDirection.MINIMIZE),
            MetricSpec("memory", MetricDirection.MINIMIZE),
            MetricSpec("latency", MetricDirection.MINIMIZE),
        )
        points = {
            self.baseline_manifest.id: point(baseline),
            self.candidate_manifest.id: point(candidate),
        }
        front = pareto_front(points, metrics)
        self.assertEqual(front, (self.candidate_manifest.id,))
        report = markdown_report(
            (self.baseline_manifest, self.candidate_manifest),
            (baseline, candidate),
            (
                paired_comparison(
                    baseline,
                    candidate,
                    "accuracy",
                    direction=MetricDirection.MAXIMIZE,
                ),
            ),
            front,
        )
        self.assertIn("harness_validation", report)
        self.assertIn("paired randomization", report)
        self.assertIn("toy-affine-candidate-v1", report)

    def test_manifest_command_reproduces_complete_baseline_result(self):
        completed = subprocess.run(
            self.baseline_manifest.reproduction.command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["manifest_id"], self.baseline_manifest.id)
        self.assertEqual(result["benchmark_id"], self.baseline_manifest.benchmark.id)
        self.assertEqual([trial["seed"] for trial in result["trials"]], list(range(10)))
        self.assertEqual([trial["metrics"]["accuracy"] for trial in result["trials"]], [0.0] * 10)
        self.assertTrue(result["environment"]["python_version"])


if __name__ == "__main__":
    unittest.main()
