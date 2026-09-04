import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from g0rd0n.ablation import (
    AblationSpec,
    AdoptionStatus,
    HarnessConfiguration,
    HarnessMechanism,
    IdeaOrigin,
    WorkloadSource,
    WorkloadSplit,
    paired_estimate,
    run_configuration,
    run_matrix,
    run_study,
    select_adoption,
)


ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "benchmarks" / "ablation" / "phase-20-workloads.json"
DEFAULTS_PATH = ROOT / "config" / "harness-defaults.json"


class HarnessAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = AblationSpec.from_json(SPEC_PATH, repository_root=ROOT)
        cls.study = run_study(cls.spec)

    def test_spec_preregisters_synthetic_historical_splits_and_budgets(self):
        self.assertEqual(len(self.spec.workloads), 48)
        self.assertEqual(len(self.spec.for_split(WorkloadSplit.SELECTION)), 24)
        self.assertEqual(len(self.spec.for_split(WorkloadSplit.HELD_OUT)), 24)
        self.assertEqual({item.source for item in self.spec.workloads}, set(WorkloadSource))
        historical = [item for item in self.spec.workloads if item.source is WorkloadSource.HISTORICAL_REPLAY]
        self.assertTrue(historical)
        self.assertTrue(all(item.historical_sha256 for item in historical))

        with tempfile.TemporaryDirectory() as directory:
            changed = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
            changed["workload_groups"][0]["historical_sha256"] = "0" * 64
            path = Path(directory) / "changed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "historical artifact mismatch"):
                AblationSpec.from_json(path, repository_root=ROOT)

    def test_cumulative_ablation_moves_each_seeded_defect_metric(self):
        matrix = self.study.selection
        baseline, frozen, isolated, shared, fresh, monitored = matrix.baseline, *matrix.cumulative
        self.assertEqual(baseline.metrics.valid_discovery_rate, 1 / 6)
        self.assertEqual((baseline.metrics.integrity_violations, baseline.metrics.duplicated_work), (12, 4))
        self.assertEqual(frozen.metrics.valid_discovery_rate, 1 / 3)
        self.assertEqual(frozen.metrics.integrity_violations, 8)
        self.assertEqual(isolated.metrics.integrity_violations, 4)
        self.assertEqual(shared.metrics.duplicated_work, 0)
        self.assertLess(shared.metrics.total_cost_units, isolated.metrics.total_cost_units)
        self.assertEqual(fresh.metrics.valid_discovery_rate, 0.5)
        self.assertEqual(monitored.metrics.integrity_violations, 0)
        self.assertEqual(monitored.metrics.budget_failures, 0)
        for result in (*matrix.cumulative, *matrix.components, matrix.human_baseline):
            self.assertEqual(result.workload_ids, baseline.workload_ids)
            self.assertEqual(result.budget_hash, baseline.budget_hash)

    def test_selection_adopts_only_supported_mechanisms_and_matches_defaults(self):
        study = self.study
        self.assertEqual(
            {item.status for item in study.adoption.decisions},
            {AdoptionStatus.ADOPT},
        )
        configured = HarnessConfiguration.from_json(DEFAULTS_PATH)
        self.assertEqual(configured, study.adoption.default_configuration)
        self.assertEqual(
            set(configured.mechanisms),
            {item.mechanism for item in study.adoption.decisions if item.status is AdoptionStatus.ADOPT},
        )
        held_matrix = run_matrix(self.spec, self.spec.for_split(WorkloadSplit.HELD_OUT))
        with self.assertRaisesRegex(ValueError, "held-out workloads cannot be used"):
            select_adoption(held_matrix, self.spec)
        changed_held_out = replace(
            self.spec,
            workloads=tuple(
                replace(item, transfer_score=0.0)
                if item.split is WorkloadSplit.HELD_OUT
                else item
                for item in self.spec.workloads
            ),
        )
        self.assertEqual(select_adoption(study.selection, changed_held_out), study.adoption)

    def test_component_estimates_are_paired_and_reject_budget_or_workload_changes(self):
        matrix = self.study.selection
        full = matrix.full
        without = matrix.without(HarnessMechanism.FROZEN_PROTOCOLS)
        estimate = paired_estimate(
            full,
            without,
            metric="valid_progress_per_cost",
            value=lambda item: item.valid_progress_per_cost,
            bootstrap_samples=self.spec.bootstrap_samples,
            seed=self.spec.bootstrap_seed,
        )
        self.assertEqual(estimate.paired_workloads, 24)
        self.assertGreater(estimate.confidence_interval_95[0], 0)
        with self.assertRaisesRegex(ValueError, "identical declared budgets"):
            paired_estimate(
                full,
                replace(without, budget_hash="0" * 64),
                metric="invalid",
                value=lambda item: item.valid_progress_per_cost,
                bootstrap_samples=100,
                seed=0,
            )
        with self.assertRaisesRegex(ValueError, "identical ordered workloads"):
            paired_estimate(
                full,
                replace(without, workload_ids=tuple(reversed(without.workload_ids))),
                metric="invalid",
                value=lambda item: item.valid_progress_per_cost,
                bootstrap_samples=100,
                seed=0,
            )

    def test_held_out_confirmation_sensitivity_and_human_cost_are_explicit(self):
        study = self.study
        self.assertTrue(study.passes_merge_gate)
        self.assertGreater(study.held_out.progress_per_cost.confidence_interval_95[0], 0)
        self.assertGreater(study.held_out.transfer.confidence_interval_95[0], 0)
        self.assertEqual(study.held_out.adopted.metrics.integrity_violations, 0)
        self.assertEqual({item.status for item in study.held_out.component_evidence}, {AdoptionStatus.ADOPT})
        self.assertTrue(all(item.adoption_fraction == 1 for item in study.sensitivity))
        human = study.selection.human_baseline
        self.assertEqual(human.configuration.idea_origin, IdeaOrigin.HUMAN)
        self.assertEqual(human.configuration.mechanisms, ())
        self.assertGreater(human.metrics.human_review_minutes, study.selection.full.metrics.human_review_minutes)
        self.assertGreater(human.metrics.total_cost_units, study.selection.full.metrics.total_cost_units)

    def test_rollback_restores_exact_fixed_governor_baseline(self):
        study = self.study
        workloads = self.spec.for_split(WorkloadSplit.SELECTION)
        rolled_back = run_configuration(self.spec, workloads, study.adoption.rollback_configuration())
        baseline = run_configuration(self.spec, workloads, HarnessConfiguration.fixed_baseline())
        self.assertEqual(rolled_back.outcomes, baseline.outcomes)
        self.assertEqual(rolled_back.metrics, baseline.metrics)
        self.assertEqual(rolled_back.configuration.governor_policy, "fixed")

    def test_command_reproduces_decision_and_held_out_report(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "g0rd0n.ablation",
                str(SPEC_PATH),
                str(DEFAULTS_PATH),
                "--repository-root",
                str(ROOT),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["passes_merge_gate"])
        self.assertTrue(report["configuration_matches"])
        self.assertEqual(report["held_out"]["adopted"]["integrity_violations"], 0)
        self.assertEqual(report["rollback"]["mechanisms"], [])


if __name__ == "__main__":
    unittest.main()
