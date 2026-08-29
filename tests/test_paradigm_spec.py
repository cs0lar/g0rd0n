import copy
import json
import unittest
from pathlib import Path

from g0rd0n.evaluation.harness import BenchmarkHarness
from g0rd0n.evaluation.manifest import BaselineManifest
from g0rd0n.paradigms import ParadigmBenchmarkSystem, ParadigmSpec, RunnerRegistry, builtin_runner_registry


ROOT = Path(__file__).parents[1]
EVENT_PATH = ROOT / "candidates" / "specs" / "toy-event-parity.json"
GRAPH_PATH = ROOT / "candidates" / "specs" / "toy-graph-rewrite-parity.json"
MANIFEST_PATH = ROOT / "benchmarks" / "manifests" / "toy-affine-candidate.json"
CASES = (
    ((0, 0, 0), 0),
    ((1,), 1),
    ((1, 1), 0),
    ((1, 0, 1, 0, 1), 1),
    ((1, 1, 1, 1), 0),
)


class ParadigmSpecTests(unittest.TestCase):
    def setUp(self):
        self.event = ParadigmSpec.from_json(EVENT_PATH)
        self.graph = ParadigmSpec.from_json(GRAPH_PATH)
        self.registry = builtin_runner_registry()

    def test_specs_capture_executable_claims_and_falsifiers(self):
        self.assertNotEqual(self.event.primitives, self.graph.primitives)
        self.assertEqual(self.event.runner, "builtin:event_parity")
        self.assertTrue(self.event.complexity_claims[0].assumptions)
        self.assertIn("unmeasured", self.event.energy_hypothesis)
        self.assertTrue(self.graph.falsifiers[0].consequence)

    def test_missing_scientific_obligations_are_rejected(self):
        value = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
        for field in ("complexity_claims", "falsifiers", "hardware_assumptions"):
            invalid = copy.deepcopy(value)
            invalid[field] = []
            with self.subTest(field=field), self.assertRaises(ValueError):
                ParadigmSpec.from_dict(invalid)

    def test_radically_different_paradigms_share_execution_interface(self):
        inputs = (1, 0, 1, 1)
        event_result = self.registry.create(self.event).execute(self.event, inputs, seed=7)
        graph_result = self.registry.create(self.graph).execute(self.graph, inputs, seed=7)
        self.assertEqual(event_result.output, graph_result.output)
        self.assertEqual(event_result.output, 1)
        self.assertNotEqual(event_result.trace, graph_result.trace)
        self.assertNotEqual(event_result.usage.peak_memory_bytes, graph_result.usage.peak_memory_bytes)

    def test_both_paradigms_execute_through_same_benchmark_harness(self):
        manifest = BaselineManifest.from_json(MANIFEST_PATH)
        harness = BenchmarkHarness()
        results = [
            harness.run(manifest, ParadigmBenchmarkSystem(spec, self.registry, CASES))
            for spec in (self.event, self.graph)
        ]
        for result in results:
            self.assertEqual(result.metric_values("accuracy"), (1.0,) * len(manifest.seeds))
            self.assertTrue(all(trial.usage.operations >= 0 for trial in result.trials))

    def test_runner_registry_rejects_unknown_and_duplicate_runners(self):
        with self.assertRaisesRegex(ValueError, "no runner registered"):
            RunnerRegistry().create(self.event)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.registry.register(self.event.runner, lambda: self.registry.create(self.event))


if __name__ == "__main__":
    unittest.main()
