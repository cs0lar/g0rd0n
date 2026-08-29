import random
import unittest

from g0rd0n.governor import (
    AdversarialScienceLoop,
    CandidateStatus,
    NoveltyIndex,
    ScientificRole,
)


class SyntheticAdversarialBackend:
    def __init__(self, *, seed=0, include_valid=True, include_duplicate=True):
        self.random = random.Random(seed)
        self.include_valid = include_valid
        self.include_duplicate = include_duplicate

    def invoke(self, assignment, payload):
        if assignment.role is ScientificRole.CANDIDATE_GENERATOR:
            candidates = [
                {"id": "H-confounded", "statement": "Feature X directly causes outcome Y", "prior_weight": 0.5}
            ]
            if self.include_duplicate:
                candidates.append(
                    {"id": "H-confounded-copy", "statement": "Feature X directly causes outcome Y", "prior_weight": 0.5}
                )
            if self.include_valid:
                candidates.append(
                    {"id": "H-robust", "statement": "Mechanism M predicts outcome Y under intervention", "prior_weight": 0.5}
                )
            return {"candidates": candidates}
        candidate_id = payload["candidate"]["id"]
        if assignment.role is ScientificRole.CRITIC:
            return {
                "strongest_alternative": "A latent variable causes both the feature and outcome.",
                "hidden_assumptions": ["No unmeasured confounder exists."],
                "known_failure_modes": ["Observational correlation survives the standard test."],
                "objections": ["The proposal lacks an intervention."],
            }
        if assignment.role is ScientificRole.FALSIFIER:
            if "experiment_id" not in payload:
                return {
                    "experiments": [
                        {"id": f"E-expensive-{candidate_id}", "description": "Large observational replication", "cost_units": 10, "falsifying_outcome": "confounder_found"},
                        {"id": f"E-cheap-{candidate_id}", "description": "Cheap confounder intervention", "cost_units": 1, "falsifying_outcome": "confounder_found"},
                    ]
                }
            flawed_is_exposed = self.random.random() < 0.75
            if candidate_id == "H-confounded":
                outcome = "confounder_found" if flawed_is_exposed else "no_confounder_found"
                likelihoods = (0.05, 0.95) if flawed_is_exposed else (0.7, 0.3)
            else:
                outcome = "intervention_succeeds"
                likelihoods = (0.9, 0.1)
            return {"outcome": outcome, "likelihood_if_candidate": likelihoods[0], "likelihood_if_alternative": likelihoods[1]}
        if assignment.role is ScientificRole.REPLICATOR:
            original = payload["original_observation"]
            return {
                "outcome": original,
                "likelihood_if_candidate": 0.9 if candidate_id == "H-robust" else 0.7,
                "likelihood_if_alternative": 0.1 if candidate_id == "H-robust" else 0.3,
            }
        raise AssertionError(assignment.role)


class AdversarialScienceTests(unittest.TestCase):
    def test_promoted_hypothesis_has_required_adversarial_record(self):
        outcome = AdversarialScienceLoop(SyntheticAdversarialBackend(seed=1)).run("What causes Y?")
        by_id = {item.candidate.id: item for item in outcome.assessments}
        flawed = by_id["H-confounded"]
        duplicate = by_id["H-confounded-copy"]
        robust = by_id["H-robust"]
        self.assertEqual(flawed.status, CandidateStatus.REJECTED)
        self.assertEqual(duplicate.status, CandidateStatus.DUPLICATE)
        self.assertEqual(robust.status, CandidateStatus.PROMOTED)
        self.assertIn("latent variable", robust.review.strongest_alternative)
        self.assertEqual(robust.selected_falsifier.cost_units, 1)
        self.assertTrue(robust.evidence_updates[-1].replicated)
        self.assertGreaterEqual(robust.evidence_updates[-1].posterior_weight, 0.8)
        self.assertNotIn(ScientificRole.REPLICATOR, outcome.role_calls[:3])
        self.assertEqual(outcome.total_experiment_cost_units, 2)

    def test_dead_candidate_stops_before_replication(self):
        outcome = AdversarialScienceLoop(
            SyntheticAdversarialBackend(seed=1, include_valid=False, include_duplicate=False)
        ).run("What causes Y?")
        self.assertEqual(outcome.assessments[0].status, CandidateStatus.REJECTED)
        self.assertNotIn(ScientificRole.REPLICATOR, outcome.role_calls)
        self.assertEqual(outcome.total_experiment_cost_units, 1)

    def test_novelty_index_detects_near_duplicates(self):
        index = NoveltyIndex(similarity_threshold=0.75)
        self.assertTrue(index.admit("Sparse events update a persistent state"))
        self.assertFalse(index.admit("Persistent state updates from sparse events"))
        self.assertTrue(index.admit("Graphs rewrite adjacent symbols"))

    def test_seeded_flaws_are_rejected_more_than_confirmation_only_at_equal_cost(self):
        adversarial_rejections = confirmation_rejections = 0
        trials = 100
        for seed in range(trials):
            outcome = AdversarialScienceLoop(
                SyntheticAdversarialBackend(seed=seed, include_valid=False, include_duplicate=False)
            ).run("Does X cause Y?")
            adversarial_rejections += outcome.assessments[0].status is CandidateStatus.REJECTED
            self.assertEqual(outcome.total_experiment_cost_units, 1)
            # A PR-07-style non-adversarial positive test checks correlation only;
            # the seeded confounder is exposed in just 20% of equal-cost trials.
            confirmation_rejections += random.Random(seed).random() < 0.20
        self.assertGreater(adversarial_rejections, confirmation_rejections)
        self.assertGreaterEqual(adversarial_rejections, 65)

    def test_malformed_red_team_review_is_rejected(self):
        backend = SyntheticAdversarialBackend()
        original = backend.invoke

        def malformed(assignment, payload):
            if assignment.role is ScientificRole.CRITIC:
                return {"strongest_alternative": "Alternative", "hidden_assumptions": [], "known_failure_modes": [], "objections": []}
            return original(assignment, payload)

        backend.invoke = malformed
        with self.assertRaises(ValueError):
            AdversarialScienceLoop(backend).run("What causes Y?")


if __name__ == "__main__":
    unittest.main()
