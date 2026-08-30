import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from g0rd0n.proofs import (
    BoundKind,
    BoundTemplate,
    ComplexityBound,
    ProofArtifactStore,
    ProofBundle,
    builtin_verifier_registry,
    search_bound_counterexample,
)


ROOT = Path(__file__).parents[1]
PROOF_PATH = ROOT / "proofs" / "toy-direct-address-membership.json"


class ProofWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.bundle = ProofBundle.from_json(PROOF_PATH)

    def test_toy_separation_discharges_every_obligation(self):
        result = builtin_verifier_registry().verify(self.bundle)
        self.assertTrue(result.verified)
        self.assertEqual(
            set(result.discharged_obligations),
            {"x-correct", "x-upper", "y-lower", "strict-separation"},
        )
        self.assertEqual(result.errors, ())
        self.assertIsNone(search_bound_counterexample(self.bundle.claim, maximum_n=10_000))

    def test_independent_verification_command(self):
        completed = subprocess.run(
            ("python", "-m", "g0rd0n.proofs", "verify", str(PROOF_PATH)),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["verified"])
        self.assertEqual(result["verifier"], "builtin:toy-membership-separation-v1")

    def test_altered_assumption_and_certificate_are_rejected(self):
        weakened = replace(self.bundle.claim, assumptions=("All models are equivalent.",))
        result = builtin_verifier_registry().verify(ProofBundle(weakened, self.bundle.certificate))
        self.assertFalse(result.verified)
        altered = dict(self.bundle.certificate)
        altered["capacity_recurrence"] = "C(h)=C(h-1)"
        result = builtin_verifier_registry().verify(ProofBundle(self.bundle.claim, altered))
        self.assertFalse(result.verified)
        self.assertIn("comparison-tree capacity induction failed", result.errors)

    def test_counterexample_search_finds_non_strict_bound(self):
        false_claim = replace(
            self.bundle.claim,
            x_bound=ComplexityBound(
                BoundKind.UPPER,
                self.bundle.claim.x_bound.resource,
                BoundTemplate.CONSTANT,
                2,
            ),
            domain_min_n=2,
        )
        counterexample = search_bound_counterexample(false_claim, maximum_n=16)
        self.assertIsNotNone(counterexample)
        assert counterexample is not None
        self.assertEqual((counterexample.n, counterexample.x_cost, counterexample.y_cost), (2, 2, 2))

    def test_proof_artifacts_are_content_addressed_and_tamper_evident(self):
        artifact = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            store = ProofArtifactStore(Path(directory))
            digest = store.put(artifact)
            self.assertEqual(store.put(artifact), digest)
            self.assertEqual(store.get(digest), artifact)
            path = Path(directory) / f"{digest}.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                store.get(digest)


if __name__ == "__main__":
    unittest.main()
