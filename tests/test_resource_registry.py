import threading
import time
import unittest

from g0rd0n.resources.adapters import (
    AdapterResult,
    CancellationToken,
    HumanResourceAdapter,
    ModelResourceAdapter,
    ProgramResourceAdapter,
)
from g0rd0n.resources.fakes import DeterministicFakeAdapter, fixed_result
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


def capability(*, permission: Permission = Permission.EXECUTE, timeout: float = 0.2) -> Capability:
    return Capability(
        id="evaluate",
        description="Evaluate a deterministic input",
        inputs=(FieldSpec("question", "string"),),
        outputs=(FieldSpec("answer", "string"),),
        required_permissions=frozenset({permission}),
        default_timeout_seconds=timeout,
    )


def resource(
    *,
    kind: ResourceKind = ResourceKind.PROGRAM,
    permission: Permission = Permission.EXECUTE,
    calls: int = 10,
    period: float = 60,
    input_bytes: int = 1_000,
    output_bytes: int = 1_000,
) -> Resource:
    return Resource(
        id=f"test-{kind.value}",
        kind=kind,
        capabilities=(capability(permission=permission),),
        cost_model=CostModel(Cost(currency_micros=25, calls=1)),
        reliability=1.0,
        rate_limit=RateLimit(calls, period),
        latency_model=LatencyModel(expected_ms=1, maximum_ms=200),
        context_limits=ContextLimits(input_bytes, output_bytes),
        permissions=frozenset({permission}),
        provenance="tests:test_resource_registry",
        context_description="one short question and answer",
        historical_performance="test fixture",
    )


def request(
    resource_id: str = "test-program",
    *,
    granted: frozenset[Permission] = frozenset({Permission.EXECUTE}),
    timeout: float | None = None,
    payload=None,
) -> InvocationRequest:
    return InvocationRequest(
        resource_id,
        "evaluate",
        payload or {"question": "What discriminates the hypotheses?"},
        granted,
        timeout,
    )


class ResourceRegistryTests(unittest.TestCase):
    def test_deterministic_fake_records_output_and_cost(self):
        registry = ResourceRegistry(id_factory=lambda: "invocation-fixed")
        adapter = DeterministicFakeAdapter({"evaluate": fixed_result({"answer": "a cheap falsifier"})})
        registry.register(resource(), adapter)

        result = registry.invoke(request())

        self.assertEqual(result.invocation_id, "invocation-fixed")
        self.assertEqual(result.status, InvocationStatus.SUCCEEDED)
        self.assertEqual(result.output, {"answer": "a cheap falsifier"})
        self.assertEqual(result.estimated_cost, Cost(currency_micros=25, calls=1))
        self.assertEqual(result.actual_cost, Cost(calls=1))
        self.assertEqual(registry.history(), (result,))
        self.assertEqual(adapter.invocations[0][0], "evaluate")

    def test_permissions_are_enforced_before_adapter_execution(self):
        registry = ResourceRegistry()
        adapter = DeterministicFakeAdapter({"evaluate": fixed_result({"answer": "must not run"})})
        registry.register(resource(permission=Permission.EXTERNAL_WRITE), adapter)
        result = registry.invoke(request(granted=frozenset()))
        self.assertEqual(result.status, InvocationStatus.DENIED)
        self.assertEqual(result.actual_cost, Cost())
        self.assertIn("external_write", result.error)
        self.assertEqual(adapter.invocations, [])

    def test_input_and_output_contracts_and_context_limits_are_enforced(self):
        registry = ResourceRegistry()
        adapter = DeterministicFakeAdapter({"evaluate": fixed_result({"unexpected": "field"})})
        registry.register(resource(input_bytes=80), adapter)
        invalid = registry.invoke(request(payload={"wrong": "shape"}))
        oversized = registry.invoke(request(payload={"question": "x" * 100}))
        bad_output = registry.invoke(request(payload={"question": "short"}))
        self.assertEqual(invalid.status, InvocationStatus.FAILED)
        self.assertEqual(oversized.status, InvocationStatus.FAILED)
        self.assertEqual(bad_output.status, InvocationStatus.FAILED)
        self.assertEqual(invalid.actual_cost, Cost())
        self.assertEqual(oversized.actual_cost, Cost())
        self.assertEqual(bad_output.actual_cost, Cost(calls=1))
        self.assertEqual(len(registry.history()), 3)

    def test_rate_limit_recovers_after_window(self):
        now = [100.0]
        registry = ResourceRegistry(clock=lambda: now[0])
        adapter = DeterministicFakeAdapter({"evaluate": fixed_result({"answer": "ok"})})
        registry.register(resource(calls=1, period=10), adapter)
        first = registry.invoke(request())
        limited = registry.invoke(request())
        now[0] = 110.0
        recovered = registry.invoke(request())
        self.assertEqual(first.status, InvocationStatus.SUCCEEDED)
        self.assertEqual(limited.status, InvocationStatus.RATE_LIMITED)
        self.assertEqual(limited.actual_cost, Cost())
        self.assertEqual(recovered.status, InvocationStatus.SUCCEEDED)

    def test_adapter_failure_is_recorded_and_next_call_recovers(self):
        class FlakyAdapter:
            calls = 0

            def invoke(self, capability, payload, cancellation):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("synthetic failure")
                return AdapterResult({"answer": "recovered"})

        registry = ResourceRegistry()
        registry.register(resource(), FlakyAdapter())
        failed = registry.invoke(request())
        recovered = registry.invoke(request())
        self.assertEqual(failed.status, InvocationStatus.FAILED)
        self.assertEqual(failed.actual_cost, Cost(currency_micros=25, calls=1))
        self.assertEqual(recovered.status, InvocationStatus.SUCCEEDED)

    def test_timeout_sets_cooperative_cancellation(self):
        stopped = threading.Event()

        class SlowAdapter:
            def invoke(self, capability, payload, cancellation):
                while not cancellation.cancelled:
                    time.sleep(0.001)
                stopped.set()
                return AdapterResult({"answer": "too late"})

        registry = ResourceRegistry()
        registry.register(resource(), SlowAdapter())
        result = registry.invoke(request(timeout=0.01))
        self.assertEqual(result.status, InvocationStatus.TIMED_OUT)
        self.assertTrue(stopped.wait(0.2))
        self.assertEqual(len(registry.history()), 1)

    def test_cancellation_during_invocation_is_recorded(self):
        started = threading.Event()

        class WaitingAdapter:
            def invoke(self, capability, payload, cancellation):
                started.set()
                while not cancellation.cancelled:
                    time.sleep(0.001)
                return AdapterResult({"answer": "cancelled work"})

        registry = ResourceRegistry()
        registry.register(resource(), WaitingAdapter())
        token = CancellationToken()
        results = []
        caller = threading.Thread(target=lambda: results.append(registry.invoke(request(), cancellation=token)))
        caller.start()
        self.assertTrue(started.wait(0.2))
        token.cancel()
        caller.join(0.2)
        self.assertFalse(caller.is_alive())
        self.assertEqual(results[0].status, InvocationStatus.CANCELLED)

    def test_model_program_and_human_wrappers_share_the_boundary(self):
        seen = []

        def backend(payload, cancellation):
            seen.append(payload["question"])
            return AdapterResult({"answer": "ok"})

        wrappers = (
            (ResourceKind.MODEL, ModelResourceAdapter(backend)),
            (ResourceKind.PROGRAM, ProgramResourceAdapter(backend)),
            (ResourceKind.HUMAN, HumanResourceAdapter(backend)),
        )
        for kind, adapter in wrappers:
            permission = Permission.HUMAN_ATTENTION if kind is ResourceKind.HUMAN else Permission.EXECUTE
            registry = ResourceRegistry()
            registered = resource(kind=kind, permission=permission)
            registry.register(registered, adapter)
            result = registry.invoke(request(registered.id, granted=frozenset({permission})))
            self.assertEqual(result.status, InvocationStatus.SUCCEEDED)
        self.assertEqual(len(seen), 3)

    def test_discovery_and_duplicate_registration(self):
        registry = ResourceRegistry()
        adapter = DeterministicFakeAdapter({"evaluate": fixed_result({"answer": "ok"})})
        registered = resource()
        registry.register(registered, adapter)
        self.assertEqual(registry.resources_for("evaluate"), (registered,))
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(registered, adapter)


if __name__ == "__main__":
    unittest.main()
