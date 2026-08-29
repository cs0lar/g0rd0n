import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from g0rd0n.budget.engine import BudgetEngine
from g0rd0n.budget.ledger import CostLedger
from g0rd0n.budget.models import Budget, BudgetClass, BudgetScopeKind, CostCeiling
from g0rd0n.core.mission import MissionSpec
from g0rd0n.core.research import ResearchObjectKind
from g0rd0n.governor.governor import GovernorConfig, MinimalResearchGovernor
from g0rd0n.governor.models import CycleDecision
from g0rd0n.governor.selection import InformationGainSelector, RandomSelector
from g0rd0n.research.ledger import FileResearchLedger, ObjectStatus
from g0rd0n.resources.adapters import AdapterResult
from g0rd0n.resources.models import (
    Capability,
    ContextLimits,
    Cost,
    CostModel,
    FieldSpec,
    LatencyModel,
    Permission,
    RateLimit,
    Resource,
    ResourceKind,
)
from g0rd0n.resources.registry import ResourceRegistry


MISSION_PATH = Path(__file__).parents[1] / "config" / "mission.json"
FIXED_TIME = datetime(2026, 8, 29, 14, 0, tzinfo=UTC)


EXPERIMENTS = [
    {
        "id": "E-best",
        "description": "One cheap experiment with a unique outcome per hypothesis",
        "predictions": {"H-A": "a", "H-B": "b", "H-C": "c", "H-D": "d"},
        "cost_units": 1,
        "maximum_cost": {"currency_micros": 2, "calls": 1, "wall_time_ms": 1000},
    },
    {
        "id": "E-partition-1",
        "description": "A weaker binary partition",
        "predictions": {"H-A": "zero", "H-B": "zero", "H-C": "one", "H-D": "one"},
        "cost_units": 2,
        "maximum_cost": {"currency_micros": 2, "calls": 1, "wall_time_ms": 1000},
    },
    {
        "id": "E-partition-2",
        "description": "A second weaker binary partition",
        "predictions": {"H-A": "zero", "H-B": "one", "H-C": "zero", "H-D": "one"},
        "cost_units": 2,
        "maximum_cost": {"currency_micros": 2, "calls": 1, "wall_time_ms": 1000},
    },
    {
        "id": "E-partition-3",
        "description": "A third weaker binary partition",
        "predictions": {"H-A": "zero", "H-B": "one", "H-C": "one", "H-D": "zero"},
        "cost_units": 2,
        "maximum_cost": {"currency_micros": 2, "calls": 1, "wall_time_ms": 1000},
    },
]


class SyntheticWorldAdapter:
    def __init__(self, true_hypothesis: str = "H-C", experiments=None) -> None:
        self.true_hypothesis = true_hypothesis
        self.experiments = list(experiments or EXPERIMENTS)
        self.calls = []

    def invoke(self, capability, payload, cancellation):
        self.calls.append(capability.id)
        if capability.id == "improve_question":
            output = {
                "questions": [
                    {
                        "id": "Q-vague",
                        "text": "Which system is best?",
                        "mission_relevance": 0.6,
                        "clarity": 0.2,
                        "falsifiability": 0.1,
                    },
                    {
                        "id": "Q-bounded",
                        "text": "Which hypothesis predicts the held-out deterministic outcome under four calls?",
                        "mission_relevance": 0.9,
                        "clarity": 1.0,
                        "falsifiability": 1.0,
                    },
                ]
            }
        elif capability.id == "generate_hypotheses":
            output = {
                "hypotheses": [
                    {"id": item, "statement": f"World mechanism is {item}"}
                    for item in ("H-A", "H-B", "H-C", "H-D")
                ]
            }
        elif capability.id == "propose_experiments":
            output = {"experiments": self.experiments}
        elif capability.id == "run_experiment":
            experiment_id = payload["experiment_id"]
            experiment = next(item for item in self.experiments if item["id"] == experiment_id)
            output = {
                "outcome": experiment["predictions"][self.true_hypothesis],
                "evidence": {
                    "world": "deterministic",
                    "experiment_id": experiment_id,
                    "observed": experiment["predictions"][self.true_hypothesis],
                },
            }
        else:
            raise RuntimeError(f"unknown capability: {capability.id}")
        return AdapterResult(output, Cost(currency_micros=1, calls=1))


def governor_resource() -> Resource:
    permissions = frozenset({Permission.EXECUTE})
    capabilities = (
        Capability(
            "improve_question",
            "Propose clearer falsifiable questions",
            (FieldSpec("mission", "string"), FieldSpec("current_question", "string")),
            (FieldSpec("questions", "array"),),
            permissions,
            1,
        ),
        Capability(
            "generate_hypotheses",
            "Generate competing hypotheses",
            (FieldSpec("question", "string"),),
            (FieldSpec("hypotheses", "array"),),
            permissions,
            1,
        ),
        Capability(
            "propose_experiments",
            "Propose discriminating experiments",
            (FieldSpec("question", "string"), FieldSpec("hypotheses", "array")),
            (FieldSpec("experiments", "array"),),
            permissions,
            1,
        ),
        Capability(
            "run_experiment",
            "Execute a synthetic experiment",
            (FieldSpec("experiment_id", "string"),),
            (FieldSpec("outcome", "string"), FieldSpec("evidence", "object")),
            permissions,
            1,
        ),
    )
    return Resource(
        "synthetic-world",
        ResourceKind.SIMULATOR,
        capabilities,
        CostModel(Cost(currency_micros=1, calls=1)),
        1.0,
        RateLimit(100, 60),
        LatencyModel(1, 1000),
        ContextLimits(100_000, 100_000),
        permissions,
        "tests:test_governor",
    )


def make_governor(root: Path, adapter, selector, *, max_experiments=1, hard_calls=10):
    registry = ResourceRegistry()
    registry.register(governor_resource(), adapter)
    budget = BudgetEngine(CostLedger(root / "costs.jsonl"))
    budget.register(
        Budget(
            "program:synthetic",
            BudgetScopeKind.PROGRAM,
            BudgetClass.TINY,
            CostCeiling(currency_micros=100, calls=hard_calls, wall_time_ms=100_000),
            CostCeiling(currency_micros=80, calls=max(0, hard_calls - 1), wall_time_ms=80_000),
        )
    )
    budget.register(
        Budget(
            "session:synthetic",
            BudgetScopeKind.SESSION,
            BudgetClass.TINY,
            CostCeiling(currency_micros=100, calls=hard_calls, wall_time_ms=100_000),
            CostCeiling(currency_micros=80, calls=max(0, hard_calls - 1), wall_time_ms=80_000),
            parent_id="program:synthetic",
        )
    )
    ledger = FileResearchLedger(root / "research")
    governor = MinimalResearchGovernor(
        mission=MissionSpec.from_json(MISSION_PATH),
        registry=registry,
        budget=budget,
        ledger=ledger,
        config=GovernorConfig(
            "synthetic-world",
            "session:synthetic",
            frozenset({Permission.EXECUTE}),
            Cost(currency_micros=2, calls=1, wall_time_ms=1000),
            max_experiments,
        ),
        selector=selector,
        now=lambda: FIXED_TIME,
    )
    return governor, ledger, budget


class GovernorTests(unittest.TestCase):
    def test_information_gain_cycle_converges_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = SyntheticWorldAdapter()
            governor, ledger, budget = make_governor(root, adapter, InformationGainSelector())
            outcome = governor.run("Which mechanism is true?")

            self.assertEqual(outcome.decision, CycleDecision.STOP)
            self.assertEqual(outcome.selected_question_id, "Q-bounded")
            self.assertEqual(outcome.surviving_hypothesis_ids, ("H-C",))
            self.assertEqual(outcome.experiments_run, ("E-best",))
            self.assertEqual(ledger.state.statuses["H-C"], ObjectStatus.COMPLETED)
            self.assertEqual(ledger.state.statuses["H-A"], ObjectStatus.REJECTED)
            observations = [item for item in ledger.state.objects.values() if item.kind is ResearchObjectKind.OBSERVATION]
            results = [item for item in ledger.state.objects.values() if item.kind is ResearchObjectKind.RESULT]
            predictions = [item for item in ledger.state.objects.values() if item.kind is ResearchObjectKind.PREDICTION]
            self.assertEqual(len(observations), 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(len(predictions), 4)
            self.assertEqual(len(ledger.state.artifacts[observations[0].id]), 1)
            source_ids = [item.id for item in ledger.state.trace_sources(results[0].id)]
            self.assertIn(observations[0].id, source_ids)
            self.assertEqual(budget.usage("session:synthetic").cost.calls, 4)

    def test_discrimination_policy_beats_random_under_same_one_experiment_budget(self):
        information_successes = 0
        random_successes = 0
        trials = 40
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for seed in range(trials):
                info_governor, _, _ = make_governor(
                    root / f"info-{seed}", SyntheticWorldAdapter(), InformationGainSelector()
                )
                random_governor, _, _ = make_governor(
                    root / f"random-{seed}", SyntheticWorldAdapter(), RandomSelector(seed)
                )
                information_successes += info_governor.run("Which mechanism is true?").decision is CycleDecision.STOP
                random_successes += random_governor.run("Which mechanism is true?").decision is CycleDecision.STOP
        self.assertEqual(information_successes, trials)
        self.assertGreater(information_successes, random_successes)
        self.assertLess(random_successes, trials // 2)

    def test_unresolved_but_discriminable_cycle_requests_continuation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            weak_experiments = EXPERIMENTS[1:]
            governor, _, _ = make_governor(
                Path(temporary_directory),
                SyntheticWorldAdapter(experiments=weak_experiments),
                InformationGainSelector(),
            )
            outcome = governor.run("Which mechanism is true?")
            self.assertEqual(outcome.decision, CycleDecision.CONTINUE)
            self.assertEqual(len(outcome.surviving_hypothesis_ids), 2)

    def test_budget_denial_escalates_without_silent_experiment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            adapter = SyntheticWorldAdapter()
            governor, ledger, budget = make_governor(
                Path(temporary_directory), adapter, InformationGainSelector(), hard_calls=3
            )
            outcome = governor.run("Which mechanism is true?")
            self.assertEqual(outcome.decision, CycleDecision.ESCALATE)
            self.assertEqual(adapter.calls, ["improve_question", "generate_hypotheses", "propose_experiments"])
            self.assertEqual(ledger.state.statuses["E-best"], ObjectStatus.REJECTED)
            self.assertEqual(budget.usage("session:synthetic").cost.calls, 3)


if __name__ == "__main__":
    unittest.main()
