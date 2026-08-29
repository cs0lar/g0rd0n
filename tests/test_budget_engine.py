import json
import tempfile
import threading
import unittest
from pathlib import Path

from g0rd0n.budget.engine import BudgetEngine
from g0rd0n.budget.ledger import CostLedger
from g0rd0n.budget.models import (
    Budget,
    BudgetClass,
    BudgetMetric,
    BudgetScopeKind,
    CostCeiling,
    StopCondition,
)
from g0rd0n.research.ledger import IntegrityError
from g0rd0n.resources.adapters import AdapterResult
from g0rd0n.resources.fakes import DeterministicFakeAdapter
from g0rd0n.resources.models import (
    Capability,
    ContextLimits,
    Cost,
    CostModel,
    FieldSpec,
    InvocationRequest,
    InvocationStatus,
    LatencyModel,
    Permission,
    RateLimit,
    Resource,
    ResourceKind,
)
from g0rd0n.resources.registry import ResourceRegistry


def make_resource() -> Resource:
    return Resource(
        id="program:test",
        kind=ResourceKind.PROGRAM,
        capabilities=(
            Capability(
                "run",
                "Run a bounded experiment",
                (FieldSpec("input", "string"),),
                (FieldSpec("output", "string"),),
                frozenset({Permission.EXECUTE}),
                1.0,
            ),
        ),
        cost_model=CostModel(Cost(currency_micros=10, tokens=5, calls=1)),
        reliability=1.0,
        rate_limit=RateLimit(100, 60),
        latency_model=LatencyModel(1, 1_000),
        context_limits=ContextLimits(1_000, 1_000),
        permissions=frozenset({Permission.EXECUTE}),
        provenance="budget-test",
    )


def request() -> InvocationRequest:
    return InvocationRequest(
        "program:test",
        "run",
        {"input": "toy experiment"},
        frozenset({Permission.EXECUTE}),
    )


def register_budgets(
    engine: BudgetEngine,
    *,
    program_hard: CostCeiling = CostCeiling(currency_micros=100),
    session_hard: CostCeiling = CostCeiling(currency_micros=50),
    session_soft: CostCeiling = CostCeiling(currency_micros=40),
    stop_conditions=(),
) -> None:
    engine.register(
        Budget(
            "program:P-1",
            BudgetScopeKind.PROGRAM,
            BudgetClass.SMALL,
            program_hard,
            CostCeiling(currency_micros=80),
        )
    )
    engine.register(
        Budget(
            "session:S-1",
            BudgetScopeKind.SESSION,
            BudgetClass.TINY,
            session_hard,
            session_soft,
            tuple(stop_conditions),
            "program:P-1",
        )
    )


class BudgetEngineTests(unittest.TestCase):
    def make_engine(self, root: Path, **budget_options) -> BudgetEngine:
        engine = BudgetEngine(CostLedger(root / "costs.jsonl"))
        register_budgets(engine, **budget_options)
        return engine

    def make_registry(self, adapter) -> ResourceRegistry:
        registry = ResourceRegistry()
        registry.register(make_resource(), adapter)
        return registry

    def test_success_is_attributed_to_session_and_program(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(Path(temporary_directory))
            registry = self.make_registry(
                DeterministicFakeAdapter(
                    {"run": AdapterResult({"output": "result"}, Cost(currency_micros=8, tokens=4, calls=1))}
                )
            )
            result = engine.invoke(
                registry,
                request(),
                scope_id="session:S-1",
                maximum_cost=Cost(currency_micros=15, tokens=10, calls=1, wall_time_ms=1_000),
            )
            self.assertTrue(result.decision.allowed)
            self.assertEqual(result.event.status, InvocationStatus.SUCCEEDED)
            self.assertEqual(result.event.estimated_cost.currency_micros, 10)
            self.assertEqual(result.event.actual_cost.currency_micros, 8)
            self.assertEqual(engine.usage("session:S-1").cost, result.event.actual_cost)
            self.assertEqual(engine.usage("program:P-1").cost, result.event.actual_cost)

    def test_hard_budget_prevents_execution(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(
                Path(temporary_directory),
                session_hard=CostCeiling(currency_micros=20),
                session_soft=CostCeiling(currency_micros=15),
            )
            adapter = DeterministicFakeAdapter(
                {"run": AdapterResult({"output": "result"}, Cost(currency_micros=10, calls=1))}
            )
            registry = self.make_registry(adapter)
            maximum = Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000)
            first = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            denied = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            self.assertEqual(first.event.status, InvocationStatus.SUCCEEDED)
            self.assertEqual(denied.event.status, InvocationStatus.DENIED)
            self.assertIn("hard budget exceeded", denied.decision.reason)
            self.assertEqual(len(adapter.invocations), 1)
            self.assertEqual(engine.usage("session:S-1").cost.currency_micros, 10)

    def test_concurrent_reservations_cannot_overcommit_hard_limit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(
                Path(temporary_directory),
                session_hard=CostCeiling(currency_micros=20),
                session_soft=CostCeiling(currency_micros=15),
            )
            started = threading.Event()
            release = threading.Event()

            class BlockingAdapter:
                def invoke(self, capability, payload, cancellation):
                    started.set()
                    release.wait(1)
                    return AdapterResult({"output": "done"}, Cost(currency_micros=10, calls=1))

            registry = self.make_registry(BlockingAdapter())
            maximum = Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000)
            results = []
            worker = threading.Thread(
                target=lambda: results.append(
                    engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
                )
            )
            worker.start()
            self.assertTrue(started.wait(0.2))
            denied = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            release.set()
            worker.join(0.5)
            self.assertEqual(denied.event.status, InvocationStatus.DENIED)
            self.assertEqual(results[0].event.status, InvocationStatus.SUCCEEDED)

    def test_failed_invocation_is_charged_and_stop_condition_blocks_next(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(
                Path(temporary_directory),
                stop_conditions=(StopCondition(BudgetMetric.FAILURES, 1, "stop after one failure"),),
            )

            class FailingAdapter:
                def invoke(self, capability, payload, cancellation):
                    raise RuntimeError("experiment crashed")

            registry = self.make_registry(FailingAdapter())
            maximum = Cost(currency_micros=15, tokens=10, calls=1, wall_time_ms=1_000)
            failed = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            stopped = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            self.assertEqual(failed.event.status, InvocationStatus.FAILED)
            self.assertEqual(failed.event.actual_cost.currency_micros, 10)
            self.assertEqual(engine.usage("session:S-1").failures, 1)
            self.assertEqual(stopped.event.status, InvocationStatus.DENIED)
            self.assertIn("stop condition", stopped.decision.reason)

    def test_soft_limit_warns_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(
                Path(temporary_directory), session_soft=CostCeiling(currency_micros=5)
            )
            registry = self.make_registry(
                DeterministicFakeAdapter({"run": AdapterResult({"output": "ok"}, Cost(currency_micros=8, calls=1))})
            )
            result = engine.invoke(
                registry,
                request(),
                scope_id="session:S-1",
                maximum_cost=Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000),
            )
            self.assertTrue(result.decision.allowed)
            self.assertIn("soft budget exceeded for session:S-1: currency_micros", result.decision.soft_warnings)

    def test_maximum_must_cover_estimate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(Path(temporary_directory))
            registry = self.make_registry(
                DeterministicFakeAdapter({"run": AdapterResult({"output": "must not run"})})
            )
            result = engine.invoke(
                registry,
                request(),
                scope_id="session:S-1",
                maximum_cost=Cost(currency_micros=9, tokens=5, calls=1),
            )
            self.assertEqual(result.event.status, InvocationStatus.DENIED)
            self.assertIn("maximum_cost", result.decision.reason)

    def test_replay_restores_usage_and_action_sequence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            engine = self.make_engine(root)
            registry = self.make_registry(
                DeterministicFakeAdapter({"run": AdapterResult({"output": "ok"}, Cost(currency_micros=7, calls=1))})
            )
            maximum = Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000)
            first = engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            replayed = self.make_engine(root)
            second = replayed.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            self.assertEqual(replayed.usage("session:S-1").cost.currency_micros, 14)
            self.assertNotEqual(first.event.action_id, second.event.action_id)

    def test_report_compares_estimated_and_actual_cost(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(Path(temporary_directory))
            registry = self.make_registry(
                DeterministicFakeAdapter(
                    {"run": AdapterResult({"output": "ok"}, Cost(currency_micros=7, tokens=3, calls=1))}
                )
            )
            engine.invoke(
                registry,
                request(),
                scope_id="session:S-1",
                maximum_cost=Cost(currency_micros=15, tokens=10, calls=1, wall_time_ms=1_000),
            )
            report = engine.report()
            self.assertIn("# Budget report", report)
            self.assertIn("### session:S-1", report)
            self.assertIn("Estimated: currency=10µ, tokens=5", report)
            self.assertIn("Actual: currency=7µ, tokens=3", report)
            self.assertIn("Currency variance (micros): -3", report)

    def test_cost_ledger_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            engine = self.make_engine(root)
            registry = self.make_registry(
                DeterministicFakeAdapter({"run": AdapterResult({"output": "ok"}, Cost(currency_micros=7, calls=1))})
            )
            engine.invoke(
                registry,
                request(),
                scope_id="session:S-1",
                maximum_cost=Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000),
            )
            path = root / "costs.jsonl"
            event = json.loads(path.read_text(encoding="utf-8"))
            event["actual_cost"]["currency_micros"] = 0
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "content hash"):
                CostLedger(path)

    def test_ledger_write_failure_keeps_reservation_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            engine = self.make_engine(
                Path(temporary_directory),
                session_hard=CostCeiling(currency_micros=20),
                session_soft=CostCeiling(currency_micros=15),
            )
            registry = self.make_registry(
                DeterministicFakeAdapter({"run": AdapterResult({"output": "spent"}, Cost(currency_micros=10, calls=1))})
            )
            original_append = engine.ledger.append
            engine.ledger.append = lambda **values: (_ for _ in ()).throw(OSError("disk unavailable"))
            maximum = Cost(currency_micros=15, tokens=5, calls=1, wall_time_ms=1_000)
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                engine.invoke(registry, request(), scope_id="session:S-1", maximum_cost=maximum)
            engine.ledger.append = original_append
            decision = engine.preflight("session:S-1", Cost(currency_micros=10), maximum)
            self.assertFalse(decision.allowed)
            self.assertIn("hard budget exceeded", decision.reason)


if __name__ == "__main__":
    unittest.main()
