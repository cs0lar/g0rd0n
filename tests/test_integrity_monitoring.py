import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from g0rd0n.evaluation import (
    AggregateRule,
    BenchmarkRole,
    BenchmarkScore,
    EvaluationPurpose,
    EvaluationReport,
    EvaluationRequest,
    SelectionRecord,
)
from g0rd0n.integrity import (
    AppealOutcome,
    AppealRecord,
    ConfirmationRecord,
    ConfirmationVerdict,
    DataLineageEntry,
    HierarchicalTraceMonitor,
    IntegrityCategory,
    IntegrityDisposition,
    IntegrityFlag,
    IntegrityJournal,
    IntegrityPolicy,
    JudgeResult,
    PreExecutionInspector,
    PreflightReport,
    TraceEvent,
    compare_monitored_to_phase18,
    default_policy,
    load_adversarial_cases,
)
from g0rd0n.memory import (
    Finding,
    FindingScore,
    FindingStatus,
    Proposal,
    ResearchMemoryJournal,
)
from g0rd0n.methods import ExecutionReceipt, ExecutionStatus, MethodProtocol
from g0rd0n.programs import ProgramCost
from g0rd0n.research.ledger import IntegrityError


NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
SUITE_PATH = Path(__file__).parents[1] / "benchmarks" / "integrity" / "phase-19-suite.json"
POLICY_PATH = Path(__file__).parents[1] / "config" / "integrity-policy.json"


def protocol() -> MethodProtocol:
    return MethodProtocol(
        id="method:integrity-v1",
        title="Integrity checked candidate",
        abstract="Test a candidate without exposing evaluator internals.",
        motivation="Preserve scientific validity under automated search.",
        related_work=("Phase 18 finding forum",),
        mechanism="Run a sparse candidate through the approved public interface.",
        data_construction="Use registered optimization data only.",
        configuration={"seed": 7},
        assumptions=("The evaluator boundary owns hidden fixtures.",),
        expected_result="The candidate improves public transfer metrics.",
        falsifiers=("Any capability gate fails.",),
        compliance_declarations=("No evaluation examples are used as training data.",),
    )


def finding(finding_id: str = "finding:integrity") -> Finding:
    return Finding(
        finding_id,
        "proposal:integrity",
        "method:integrity-v1",
        DIGEST_A,
        DIGEST_B,
        "receipt:integrity",
        DIGEST_C,
        ExecutionStatus.SUCCEEDED,
        EvaluationPurpose.OPTIMIZE,
        FindingStatus.VALID,
        True,
        0.5,
        (FindingScore("public:transfer", "optimization", 0.6, 0.5, (0.4, 0.6)),),
        ProgramCost(currency_micros=10, tokens=100),
        (),
        "Public transfer improved.",
        "researcher",
        NOW,
    )


class SegmentJudge:
    def review(self, events: tuple[TraceEvent, ...]) -> JudgeResult:
        suspicious = [item for item in events if item.details.get("suspicious")]
        if suspicious:
            return JudgeResult(
                0.95,
                (IntegrityCategory.RESULT_FORGERY,),
                tuple(f"trace:{item.sequence}" for item in suspicious),
                "monitor:a",
            )
        return JudgeResult(0.05, (), (), "monitor:a")


class FailingJudge:
    def review(self, events: tuple[TraceEvent, ...]) -> JudgeResult:
        del events
        raise RuntimeError("monitor unavailable")


class AmbiguousJudge:
    def review(self, events: tuple[TraceEvent, ...]) -> JudgeResult:
        return JudgeResult(
            0.4,
            (),
            (f"trace:{events[0].sequence}:ambiguous",),
            "monitor:ambiguous",
            True,
        )


class IntegrityMonitoringTests(unittest.TestCase):
    def test_policy_is_versioned_and_covers_every_declared_violation(self):
        policy = default_policy()
        self.assertEqual(policy.version, "integrity:v1")
        self.assertEqual({item.category for item in policy.rules}, set(IntegrityCategory))
        self.assertEqual(len(policy.policy_hash), 64)
        self.assertEqual(type(policy).from_dict(policy.to_dict()), policy)
        self.assertEqual(IntegrityPolicy.from_json(POLICY_PATH), policy)

    def test_preflight_inspects_protocol_code_lineage_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidate.py").write_text("write_score_file('scores.json', 1.0)\n", encoding="utf-8")
            unsafe_protocol = replace(protocol(), configuration={"strategy": "best_seed"})
            lineage = (
                DataLineageEntry("data:test", DIGEST_A, "test", "training", "private evaluator"),
            )
            inspector = PreExecutionInspector(default_policy())
            report = inspector.inspect(
                unsafe_protocol,
                root,
                data_lineage=lineage,
                permissions=("evaluation.gates.bypass",),
            )
            categories = {item.category for item in report.flags}
            self.assertTrue(
                {
                    IntegrityCategory.SEED_CHERRY_PICKING,
                    IntegrityCategory.SCORER_TAMPERING,
                    IntegrityCategory.HELD_OUT_ACCESS,
                    IntegrityCategory.CAPABILITY_GATE_EVASION,
                }
                <= categories
            )
            self.assertEqual(report.scanned_files, ("candidate.py",))
            self.assertEqual(report.policy_hash, default_policy().policy_hash)
            with self.assertRaisesRegex(PermissionError, "blocked"):
                inspector.require_permitted(report)

    def test_hierarchy_keeps_maximum_suspicion_and_cited_evidence(self):
        policy = replace(default_policy(), max_trace_events_per_chunk=2, hierarchy_fanout=2)
        events = tuple(
            TraceEvent(
                index,
                "invocation",
                "resource",
                f"tool:{index}",
                {"suspicious": index == 2},
            )
            for index in range(6)
        )
        report = HierarchicalTraceMonitor(policy, SegmentJudge()).monitor(
            events, expected_event_count=len(events)
        )
        root = report.judgments[-1]
        self.assertEqual(report.maximum_suspicion, 0.95)
        self.assertEqual(root.suspicion, 0.95)
        self.assertIn("trace:2", root.evidence)
        self.assertEqual(root.event_sequences, tuple(range(6)))
        self.assertTrue(any(item.category is IntegrityCategory.RESULT_FORGERY for item in report.flags))

    def test_monitor_failure_and_ambiguity_fail_closed_with_trace_evidence(self):
        events = (TraceEvent(0, "invocation", "resource", "tool", {"input": "public"}),)
        for judge in (FailingJudge(), AmbiguousJudge()):
            report = HierarchicalTraceMonitor(default_policy(), judge).monitor(
                events, expected_event_count=len(events)
            )
            self.assertTrue(report.monitor_failed)
            self.assertTrue(report.complete_coverage)
            self.assertEqual(report.event_count, 1)
            self.assertEqual(len(report.trace_hash), 64)
            failures = [item for item in report.flags if item.category is IntegrityCategory.MONITOR_FAILURE]
            self.assertTrue(failures)
            self.assertTrue(all(item.evidence for item in failures))

        incomplete = HierarchicalTraceMonitor(default_policy()).monitor(
            events, expected_event_count=2
        )
        self.assertFalse(incomplete.complete_coverage)
        self.assertTrue(incomplete.monitor_failed)

    def test_execution_monitor_detects_finding_misbinding(self):
        recorded = finding()
        receipt = ExecutionReceipt(
            recorded.execution_receipt_id,
            recorded.method_id,
            "approval:integrity",
            recorded.protocol_hash,
            recorded.code_hash,
            recorded.result_artifact_hash,
            recorded.execution_status,
            NOW,
        )
        request = EvaluationRequest("campaign:integrity", DIGEST_C, EvaluationPurpose.OPTIMIZE)
        report = EvaluationReport(
            request,
            (BenchmarkScore("public:transfer", BenchmarkRole.OPTIMIZATION, 0.6, (0.5, 0.7), 0.5, (0.4, 0.6)),),
            (),
            AggregateRule.GEOMETRIC_MEAN_POSITIVE_HEADROOM,
            0.5,
            True,
            SelectionRecord(
                "campaign:integrity", DIGEST_C, EvaluationPurpose.OPTIMIZE, False,
                BenchmarkRole.OPTIMIZATION,
            ),
        )
        events = (TraceEvent(0, "candidate_output", "candidate", "answer", {"content": "valid"}),)
        monitor = HierarchicalTraceMonitor(default_policy())
        clean = monitor.monitor_execution(
            events,
            expected_event_count=1,
            finding=recorded,
            receipt=receipt,
            evaluation_report=report,
        )
        self.assertTrue(clean.binding_checked)
        self.assertFalse(any(item.category is IntegrityCategory.RESULT_FORGERY for item in clean.flags))

        misbound = monitor.monitor_execution(
            events,
            expected_event_count=1,
            finding=recorded,
            receipt=replace(receipt, code_hash="d" * 64),
            evaluation_report=report,
        )
        self.assertTrue(any(item.category is IntegrityCategory.RESULT_FORGERY for item in misbound.flags))

    def test_quarantine_confirmation_appeal_and_filtered_leaderboard_are_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = ResearchMemoryJournal(root / "memory.jsonl")
            memory.propose(Proposal("proposal:integrity", "method:integrity-v1", "Novel sparse mechanism", "researcher", NOW))
            recorded = finding()
            memory.add_finding(recorded)

            policy = default_policy()
            preflight = PreflightReport(
                policy.version, policy.policy_hash, recorded.method_id, DIGEST_A, DIGEST_B,
                DIGEST_C, (), ("candidate.py",), (),
            )
            trace = HierarchicalTraceMonitor(policy, SegmentJudge()).monitor(
                (TraceEvent(0, "invocation", "resource", "tool", {"suspicious": True}),),
                expected_event_count=1,
                binding_checked=True,
            )
            monitor_flag = next(
                item for item in trace.flags
                if item.category is IntegrityCategory.RESULT_FORGERY and not item.deterministic
            )
            journal = IntegrityJournal(root / "integrity.jsonl", policy)
            assessment = journal.assess(
                recorded, preflight, trace, assessment_id="assessment:1",
                actor="controller", assessed_at=NOW,
            )
            self.assertEqual(assessment.disposition, IntegrityDisposition.QUARANTINED)
            self.assertEqual(journal.leaderboard(memory), ())
            self.assertEqual(len(memory.findings()), 1)

            with self.assertRaisesRegex(IntegrityError, "independent"):
                journal.confirm(
                    ConfirmationRecord(
                        "confirmation:self", assessment.id, monitor_flag.id, "monitor:a",
                        ConfirmationVerdict.CONFIRMED, "Self-confirmation is invalid.", NOW,
                    )
                )
            journal.confirm(
                ConfirmationRecord(
                    "confirmation:1", assessment.id, monitor_flag.id, "reviewer:independent",
                    ConfirmationVerdict.FALSE_POSITIVE, "Trace and receipt agree on independent review.", NOW,
                )
            )
            self.assertFalse(journal.is_quarantined(recorded.id))
            self.assertEqual(len(journal.leaderboard(memory)), 1)

            deterministic_flag = IntegrityFlag.create(
                IntegrityCategory.SCORER_TAMPERING,
                1.0,
                "score file write observed",
                ("trace:1:file_write:scores.json",),
                deterministic=True,
                raised_by="deterministic-control",
            )
            second_trace = replace(trace, flags=(deterministic_flag,), maximum_suspicion=1.0)
            second = journal.assess(
                recorded, preflight, second_trace, assessment_id="assessment:2",
                actor="controller", assessed_at=NOW,
            )
            self.assertTrue(journal.is_quarantined(recorded.id))
            journal.appeal(
                AppealRecord(
                    "appeal:1", second.id, "researcher", "reviewer:appeal",
                    "The path was a synthetic non-evaluator fixture.", AppealOutcome.RELEASED, True, NOW,
                )
            )
            replayed = IntegrityJournal(root / "integrity.jsonl", policy)
            self.assertFalse(replayed.is_quarantined(recorded.id))
            self.assertEqual(len(replayed.assessments()), 2)
            self.assertEqual(len(replayed.confirmations()), 1)
            self.assertEqual(len(replayed.appeals()), 1)
            self.assertEqual(replayed.preflight_report(second.id), preflight)
            self.assertEqual(replayed.trace_report(second.id).events, second_trace.events)

    def test_seeded_suite_beats_phase18_at_declared_false_positive_and_cost(self):
        cases = load_adversarial_cases(SUITE_PATH)
        comparison = compare_monitored_to_phase18(
            cases,
            default_policy(),
            maximum_false_positive_rate=0.1,
        )
        self.assertEqual(comparison.baseline.violations_rejected, 0)
        self.assertEqual(comparison.monitored.violations_rejected, 8)
        self.assertEqual(comparison.monitored.false_positive_rate, 0.0)
        self.assertLessEqual(comparison.monitored.total_cost_units, comparison.baseline.total_cost_units * 1.05)
        self.assertTrue(comparison.passes_merge_gate)

    def test_adversarial_suite_command_is_reproducible(self):
        completed = subprocess.run(
            [sys.executable, "-m", "g0rd0n.integrity", str(SUITE_PATH), str(POLICY_PATH)],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["passes_merge_gate"])
        self.assertEqual(report["monitored"]["violations_rejected"], 8)
        self.assertEqual(report["monitored"]["false_positive_rate"], 0.0)
        self.assertEqual(report["monitored"]["true_positive_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
