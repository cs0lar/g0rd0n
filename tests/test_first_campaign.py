import json
import subprocess
import unittest
from pathlib import Path

from g0rd0n.campaigns import run_campaign


ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "campaigns" / "first-discovery" / "preregistration.json"
RESULT_PATH = ROOT / "campaigns" / "first-discovery" / "result.json"


class FirstDiscoveryCampaignTests(unittest.TestCase):
    def test_preregistration_fixes_question_baselines_bounds_and_falsifiers(self):
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.assertTrue(spec["registered_before_results"])
        self.assertIn("not externally timestamped", spec["registration_scope"])
        self.assertEqual(len(spec["task_families"]), 2)
        self.assertEqual(spec["resource_constraints"]["maximum_paid_api_calls"], 0)
        self.assertEqual(spec["resource_constraints"]["maximum_gpu_seconds"], 0)
        self.assertTrue(spec["falsifiers"])
        for baseline in spec["baselines"]:
            self.assertTrue(baseline["known_shortcuts"])
            self.assertTrue(baseline["contamination_risk"])

    def test_exhaustive_campaign_reproduces_committed_negative_result(self):
        campaign = run_campaign(SPEC_PATH)
        committed = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(campaign.status, committed["status"])
        self.assertEqual(campaign.first_falsifying_length, committed["first_falsifying_length"])
        self.assertEqual(campaign.replication_hash, committed["replication_hash"])
        self.assertTrue(campaign.replicated)
        self.assertEqual(
            [item.candidate_accuracy for item in campaign.recall_curve],
            committed["recall_candidate_accuracy"],
        )

    def test_candidate_advantage_is_narrow_and_transfer_falsifier_is_decisive(self):
        campaign = run_campaign(SPEC_PATH)
        for point in campaign.parity_curve:
            self.assertEqual(point.candidate_accuracy, 1.0)
            self.assertLessEqual(point.candidate_state_bits, point.history_baseline_state_bits)
            self.assertLessEqual(point.candidate_mean_updates, point.history_baseline_mean_reads)
        state_bits = 2
        for point in campaign.recall_curve:
            expected = 1.0 if point.sequence_length <= state_bits else 2 ** (state_bits - point.sequence_length)
            self.assertEqual(point.candidate_accuracy, expected)
            self.assertEqual(point.history_baseline_accuracy, 1.0)
        self.assertTrue(all(campaign.theorem_obligations.values()))
        self.assertFalse(campaign.transformer_benchmark_executed)
        self.assertIn("No joule", campaign.energy_claim)

    def test_one_command_campaign_output_is_machine_readable(self):
        completed = subprocess.run(
            ("python", "-m", "g0rd0n.campaigns", "run", str(SPEC_PATH)),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "falsified_candidate_class")
        self.assertTrue(output["replicated"])


if __name__ == "__main__":
    unittest.main()
