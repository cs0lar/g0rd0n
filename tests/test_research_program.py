import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from g0rd0n.programs import (
    ExperimentResult,
    ProgramCost,
    ProgramJournal,
    ProgramStatus,
    ResearchProgramLifecycle,
    ResearchProgramSpec,
)
from g0rd0n.research.ledger import IntegrityError


ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "programs" / "synthetic-discovery.json"


class SyntheticDiscoveryExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, task, *, attempt):
        self.calls.append((task.id, attempt))
        if task.id == "extrapolation-test" and attempt == 1:
            return ExperimentResult(
                False,
                "The first synthetic apparatus reading was invalid.",
                (),
                (),
                ("Injected transient apparatus failure.",),
                ("The mechanism remains unresolved.",),
                "Can a repeated held-out reading discriminate the mechanisms?",
                ProgramCost(1, 2, 5, 0.05, 0),
            )
        if task.id == "extrapolation-test":
            return ExperimentResult(
                True,
                "Held-out values follow the affine rule.",
                ("artifact:synthetic-held-out-sequence",),
                ("Downgrade lookup-table; retain affine-rule.",),
                (),
                ("Only a toy deterministic family has been tested.",),
                "Does the rule transfer to a different algorithmic family?",
                ProgramCost(2, 5, 20, 0.2, 0),
            )
        return ExperimentResult(
            True,
            "Human review accepts only a toy-family claim.",
            ("review:human-approval",),
            ("Label affine evidence as toy-only.",),
            (),
            ("Generality and real energy remain untested.",),
            "Which second task family most cheaply tests transfer?",
            ProgramCost(1, 2, 5, 0.05, 1),
        )


class ResearchProgramTests(unittest.TestCase):
    def test_multi_session_program_pauses_replays_reviews_and_completes(self):
        spec = ResearchProgramSpec.from_json(SPEC_PATH)
        executor = SyntheticDiscoveryExecutor()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "program.jsonl"
            first = ResearchProgramLifecycle(spec, ProgramJournal(path), executor)
            report = first.run_session(max_actions=1)
            self.assertEqual(report.status, ProgramStatus.PAUSED)
            self.assertEqual(first.state.attempt_count("extrapolation-test"), 1)

            second = ResearchProgramLifecycle(spec, ProgramJournal(path), executor)
            report = second.run_session(max_actions=1)
            self.assertEqual(report.status, ProgramStatus.PAUSED)
            self.assertEqual(second.state.completed_experiment_ids, ("extrapolation-test",))

            waiting = ResearchProgramLifecycle(spec, ProgramJournal(path), executor)
            report = waiting.run_session(max_actions=1)
            self.assertEqual(report.status, ProgramStatus.WAITING_REVIEW)
            self.assertEqual(executor.calls[-1], ("extrapolation-test", 2))

            final = ResearchProgramLifecycle(spec, ProgramJournal(path), executor)
            report = final.run_session(max_actions=1, review_decisions={"claim-review": True})
            self.assertEqual(report.status, ProgramStatus.COMPLETED)
            self.assertEqual(report.experiments_performed, ("extrapolation-test", "claim-review"))
            self.assertEqual(report.spend, ProgramCost(4, 9, 30, 0.3, 1))
            self.assertIn("toy-only", " ".join(report.claims_changed))
            self.assertIn("Energy: 0.300000 J", report.markdown())
            self.assertIn("## Best next question", report.markdown())

            replayed = ProgramJournal(path)
            self.assertEqual(replayed.state, final.state)
            self.assertGreaterEqual(len(replayed.checkpoints()), 10)
            self.assertEqual(
                [item.sequence for item in replayed.checkpoints()],
                list(range(len(replayed.checkpoints()))),
            )

    def test_budget_denial_escalates_before_execution(self):
        spec = ResearchProgramSpec.from_json(SPEC_PATH)
        spec = replace(spec, budget=ProgramCost(1, 1, 1, 0.01, 0))
        executor = SyntheticDiscoveryExecutor()
        with tempfile.TemporaryDirectory() as directory:
            lifecycle = ResearchProgramLifecycle(spec, ProgramJournal(Path(directory) / "journal.jsonl"), executor)
            report = lifecycle.run_session(max_actions=1)
            self.assertEqual(report.status, ProgramStatus.ESCALATED)
            self.assertEqual(executor.calls, [])
            self.assertIn("exceed program budget", report.reason)

    def test_actual_cost_above_declared_maximum_is_visible_and_escalates(self):
        spec = ResearchProgramSpec.from_json(SPEC_PATH)

        class ExpensiveExecutor:
            def execute(self, task, *, attempt):
                return ExperimentResult(True, "Result", (), (), (), ("Unknown",), "Next?", ProgramCost(99, 0, 0, 0, 0))

        with tempfile.TemporaryDirectory() as directory:
            lifecycle = ResearchProgramLifecycle(spec, ProgramJournal(Path(directory) / "journal.jsonl"), ExpensiveExecutor())
            report = lifecycle.run_session(max_actions=1)
            self.assertEqual(report.status, ProgramStatus.ESCALATED)
            self.assertEqual(report.spend.currency_micros, 99)
            self.assertIn("maximum cost", report.reason)

    def test_journal_tampering_prevents_resume(self):
        spec = ResearchProgramSpec.from_json(SPEC_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            ResearchProgramLifecycle(spec, ProgramJournal(path), SyntheticDiscoveryExecutor())
            content = path.read_text(encoding="utf-8")
            path.write_text(content.replace("program_initialized", "program_altered"), encoding="utf-8")
            with self.assertRaises(IntegrityError):
                ProgramJournal(path)

    def test_changed_specification_cannot_resume_existing_journal(self):
        spec = ResearchProgramSpec.from_json(SPEC_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            journal = ProgramJournal(path)
            ResearchProgramLifecycle(spec, journal, SyntheticDiscoveryExecutor())
            changed = replace(spec, question="A silently changed mission question")
            with self.assertRaisesRegex(ValueError, "specification changed"):
                ResearchProgramLifecycle(changed, ProgramJournal(path), SyntheticDiscoveryExecutor())


if __name__ == "__main__":
    unittest.main()
