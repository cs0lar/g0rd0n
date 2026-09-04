import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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
from g0rd0n.memory import (
    Finding,
    FindingScore,
    FindingStatus,
    LiteratureEntry,
    Proposal,
    ResearchMemoryJournal,
    ReviewerKind,
    ReviewPosition,
    ReviewRecord,
    SourceReference,
    StopAction,
)
from g0rd0n.methods import ExecutionReceipt, ExecutionStatus
from g0rd0n.programs import ProgramCost
from g0rd0n.research.ledger import IntegrityError


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def proposal(index: int, summary: str | None = None) -> Proposal:
    return Proposal(
        f"proposal:{index}", f"method:{index}", summary or f"Test sparse memory mechanism variant {index}",
        "researcher", NOW + timedelta(seconds=index),
    )


def finding(
    index: int,
    *,
    status: FindingStatus = FindingStatus.VALID,
    purpose: EvaluationPurpose = EvaluationPurpose.OPTIMIZE,
    score: float = 0.2,
) -> Finding:
    valid = status is FindingStatus.VALID
    return Finding(
        f"finding:{index}", f"proposal:{index}", f"method:{index}", DIGEST_A, DIGEST_B,
        f"receipt:{index}", DIGEST_C, ExecutionStatus.SUCCEEDED, purpose, status, valid,
        score if valid else None,
        (FindingScore("public:transfer", BenchmarkRole.OPTIMIZATION.value, score, score, (score - 0.01, score + 0.01)),),
        ProgramCost(currency_micros=index + 1, tokens=100),
        () if valid else ("capability gate failed",),
        f"Interpretation {index}", "researcher", NOW + timedelta(minutes=index),
    )


class SharedResearchMemoryTests(unittest.TestCase):
    def test_fresh_process_reconstructs_same_survey_forum_and_leaderboard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.jsonl"
            journal = ResearchMemoryJournal(path)
            journal.add_literature(
                LiteratureEntry(
                    "literature:sparse", "Sparse memory", "Candidate architectures",
                    "Gate writes using local novelty.", ("Run the published toy suite.",),
                    ("Only tested on delayed recall.",),
                    (SourceReference("Example et al. 2026", "doi:10/example"),), "librarian", NOW,
                )
            )
            journal.propose(proposal(1))
            journal.add_finding(finding(1, score=0.4))
            journal.add_review(
                ReviewRecord(
                    "review:1", "finding:1", "human:ada", ReviewerKind.HUMAN,
                    ReviewPosition.CHALLENGE, "Check transfer beyond recall.", False, NOW,
                )
            )

            replayed = ResearchMemoryJournal(path)
            self.assertEqual(replayed.events(), journal.events())
            self.assertEqual(replayed.survey(), journal.survey())
            self.assertEqual(replayed.findings(), journal.findings())
            self.assertEqual(replayed.reviews(), journal.reviews())
            self.assertEqual(replayed.forum(), journal.forum())
            self.assertEqual(replayed.leaderboard(), journal.leaderboard())
            leader = replayed.leaderboard()[0]
            self.assertEqual((leader.execution_receipt_id, leader.cost.tokens), ("receipt:1", 100))
            script = (
                "import json,sys; from pathlib import Path; "
                "from g0rd0n.memory import ResearchMemoryJournal; "
                "j=ResearchMemoryJournal(Path(sys.argv[1])); "
                "print(json.dumps([len(j.survey()),len(j.forum().findings),"
                "len(j.forum().reviews),j.leaderboard()[0].finding_id]))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script, str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(completed.stdout), [1, 1, 1, "finding:1"])

    def test_survey_deduplicates_mechanisms_before_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ResearchMemoryJournal(Path(directory) / "memory.jsonl", similarity_threshold=0.8)
            entry = LiteratureEntry(
                "literature:1", "Sparse gated memory", "Delayed recall architecture",
                "Store novel events in sparse external memory.", ("Run delayed recall suite.",),
                ("Small synthetic tasks only.",), (SourceReference("Paper", "doi:one"),),
                "librarian", NOW,
            )
            journal.add_literature(entry)
            duplicate = LiteratureEntry(
                "literature:2", "Sparse gated memories", "Delayed recall architectures",
                "Store novel event in sparse external memories.", ("Reproduce the suite.",),
                ("No hardware measurement.",), (SourceReference("Paper copy", "doi:two"),),
                "librarian", NOW,
            )
            with self.assertRaisesRegex(ValueError, "duplicate literature"):
                journal.add_literature(duplicate)
            self.assertEqual(journal.survey(), (entry,))

            decision = journal.propose(
                proposal(1, "Sparse gated memory for delayed recall stores novel events in external memory")
            )
            self.assertFalse(decision.accepted)
            self.assertEqual(decision.nearest_id, entry.id)

    def test_failed_and_invalid_findings_never_lead(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ResearchMemoryJournal(Path(directory) / "memory.jsonl")
            for index in range(1, 5):
                journal.propose(proposal(index))
            journal.add_finding(finding(1, score=0.3))
            journal.add_finding(finding(2, status=FindingStatus.FAILED, score=0.99))
            journal.add_finding(finding(3, status=FindingStatus.INVALID, score=0.99))
            journal.add_finding(finding(4, purpose=EvaluationPurpose.CONFIRM, score=0.99))

            self.assertEqual(len(journal.findings()), 4)
            self.assertEqual(
                [item.finding_id for item in journal.leaderboard()],
                ["finding:4", "finding:1"],
            )
            self.assertEqual(journal.leaderboard()[0].evaluation_purpose, EvaluationPurpose.CONFIRM)

    def test_concurrent_sessions_append_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.jsonl"

            def add(index: int) -> bool:
                session = ResearchMemoryJournal(path, similarity_threshold=1.0)
                accepted = session.propose(proposal(index)).accepted
                if accepted:
                    session.add_finding(finding(index, score=index / 100))
                return accepted

            with ThreadPoolExecutor(max_workers=8) as executor:
                accepted = list(executor.map(add, range(1, 25)))

            replayed = ResearchMemoryJournal(path)
            self.assertTrue(all(accepted))
            self.assertEqual(len(replayed.events()), 48)
            self.assertEqual(len(replayed.findings()), 24)
            self.assertEqual(
                {event.payload["id"] for event in replayed.events() if event.kind.value == "proposal_added"},
                {f"proposal:{index}" for index in range(1, 25)},
            )

    def test_duplicate_proposal_is_rejected_and_drives_stopping(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ResearchMemoryJournal(Path(directory) / "memory.jsonl", similarity_threshold=0.8)
            original = proposal(1, "Evaluate sparse event gated memory on delayed exact recall")
            self.assertTrue(journal.propose(original).accepted)
            for index in range(2, 5):
                decision = journal.propose(
                    proposal(index, "Evaluate sparse event gated memory on delayed exact recalls")
                )
                self.assertFalse(decision.accepted)
                self.assertEqual(decision.nearest_id, original.id)
            self.assertEqual(journal.stopping_decision(duplicate_limit=3).action, StopAction.STOP)
            self.assertFalse(any(item.id == "proposal:2" for item in journal.proposals()))

    def test_plateau_stops_after_declared_window(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ResearchMemoryJournal(Path(directory) / "memory.jsonl")
            for index, score in enumerate((0.50, 0.49, 0.50, 0.505), 1):
                journal.propose(proposal(index))
                journal.add_finding(finding(index, score=score))
            decision = journal.stopping_decision(plateau_window=3, minimum_improvement=0.01)
            self.assertEqual(decision.action, StopAction.STOP)
            self.assertIn("no material improvement", decision.reason)

    def test_briefing_is_deterministic_and_excludes_restricted_and_test_information(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.jsonl"
            journal = ResearchMemoryJournal(path)
            journal.add_literature(
                LiteratureEntry(
                    "literature:private", "HIDDEN TEST ANSWERS", "private evaluation", "SECRET-PAYLOAD",
                    ("Do not disclose.",), ("Private fixture.",),
                    (SourceReference("Internal fixture", "restricted:fixture"),), "evaluator", NOW, False,
                )
            )
            journal.propose(proposal(1))
            journal.add_finding(finding(1, purpose=EvaluationPurpose.CONFIRM, score=0.9))
            journal.propose(proposal(2))
            journal.add_finding(finding(2, score=0.4))
            journal.add_review(
                ReviewRecord(
                    "review:human", "finding:2", "human:grace", ReviewerKind.HUMAN,
                    ReviewPosition.CHALLENGE, "Replication is still missing.", False, NOW,
                )
            )
            budget = ProgramCost(currency_micros=500, tokens=2_000, human_minutes=15)

            first = journal.briefing(mission="Find valid separations.", remaining_budget=budget)
            second = ResearchMemoryJournal(path).briefing(mission="Find valid separations.", remaining_budget=budget)
            self.assertEqual(first, second)
            self.assertIn("finding:2", first)
            self.assertIn("human:grace", first)
            self.assertNotIn("HIDDEN TEST ANSWERS", first)
            self.assertNotIn("SECRET-PAYLOAD", first)
            self.assertNotIn("finding:1", first)

    def test_finding_factory_binds_receipt_and_aggregate_report(self):
        receipt = ExecutionReceipt(
            "receipt:1", "method:1", "approval:1", DIGEST_A, DIGEST_B, DIGEST_C,
            ExecutionStatus.SUCCEEDED, NOW,
        )
        request = EvaluationRequest("campaign:1", DIGEST_C, EvaluationPurpose.SELECT)
        report = EvaluationReport(
            request,
            (BenchmarkScore("validation:transfer", BenchmarkRole.VALIDATION, 0.7, (0.6, 0.8), 0.5, (0.4, 0.6)),),
            (), AggregateRule.GEOMETRIC_MEAN_POSITIVE_HEADROOM, 0.5, True,
            SelectionRecord("campaign:1", DIGEST_C, EvaluationPurpose.SELECT, True, BenchmarkRole.VALIDATION),
        )
        bound = Finding.from_evaluation(
            finding_id="finding:1", proposal_id="proposal:1", receipt=receipt, report=report,
            status=FindingStatus.VALID, cost=ProgramCost(tokens=10), failures=(),
            interpretation="Transfer improved.", recorded_by="researcher", recorded_at=NOW,
        )
        self.assertEqual((bound.protocol_hash, bound.code_hash, bound.aggregate_score), (DIGEST_A, DIGEST_B, 0.5))

        mismatched = EvaluationRequest("campaign:1", "d" * 64, EvaluationPurpose.SELECT)
        with self.assertRaisesRegex(ValueError, "does not match"):
            Finding.from_evaluation(
                finding_id="finding:2", proposal_id="proposal:1", receipt=receipt,
                report=EvaluationReport(
                    mismatched, report.scores, report.gates, report.aggregate_rule,
                    report.aggregate_headroom_closed, report.eligible, report.selection,
                ),
                status=FindingStatus.VALID, cost=ProgramCost(), failures=(),
                interpretation="Bad binding.", recorded_by="researcher", recorded_at=NOW,
            )

    def test_edited_finding_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.jsonl"
            journal = ResearchMemoryJournal(path)
            journal.propose(proposal(1))
            journal.add_finding(finding(1))
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = json.loads(lines[1])
            changed["payload"]["interpretation"] = "Hindsight rewrite"
            lines[1] = json.dumps(changed)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "hash chain"):
                ResearchMemoryJournal(path)


if __name__ == "__main__":
    unittest.main()
