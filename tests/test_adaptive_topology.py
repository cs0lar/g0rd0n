import unittest

from g0rd0n.governor import (
    AdaptiveResourceTopology,
    AllocationStrategy,
    FixedResourcePolicy,
    PerformanceObservation,
    ResourceStrategyProfile,
    TopologyActionKind,
    Workload,
    evaluate_policy,
    paired_policy_comparison,
)


GENERAL = ResourceStrategyProfile("general", frozenset({"analyze"}), 1.0, 0.0, 0.5)
MATH = ResourceStrategyProfile("math-specialist", frozenset({"analyze"}), 1.0, 0.5, 0.4)
TEXT = ResourceStrategyProfile("text-specialist", frozenset({"analyze"}), 1.0, 0.5, 0.4)
STRATEGY = AllocationStrategy(
    "utility-per-cost-v1",
    exploration_strength=0.1,
    spawn_amortization_tasks=5,
    retirement_min_observations=3,
    retirement_utility_threshold=0.2,
)


def trained_topology():
    topology = AdaptiveResourceTopology((GENERAL, MATH, TEXT), STRATEGY, initially_active=(GENERAL.id,))
    for _ in range(4):
        topology.record(PerformanceObservation(MATH.id, "math", 0.9, 1.0, True))
        topology.record(PerformanceObservation(TEXT.id, "text", 0.9, 1.0, True))
        topology.record(PerformanceObservation(GENERAL.id, "math", 0.5, 1.0, True))
        topology.record(PerformanceObservation(GENERAL.id, "text", 0.5, 1.0, True))
    return topology


class AdaptiveTopologyTests(unittest.TestCase):
    def test_allocation_spawns_then_reuses_family_specialist(self):
        topology = trained_topology()
        first = topology.allocate(Workload("held-math-0", "math", "analyze"))
        second = topology.allocate(Workload("held-math-1", "math", "analyze"))
        self.assertEqual(first.resource_id, MATH.id)
        self.assertTrue(first.spawned)
        self.assertFalse(second.spawned)
        self.assertEqual(topology.actions[-2].kind, TopologyActionKind.SPAWN)
        self.assertEqual(topology.actions[-1].kind, TopologyActionKind.REUSE)

    def test_underperformer_retires_after_declared_evidence_count(self):
        topology = AdaptiveResourceTopology((GENERAL, MATH), STRATEGY, initially_active=(GENERAL.id, MATH.id))
        for _ in range(STRATEGY.retirement_min_observations):
            topology.record(PerformanceObservation(MATH.id, "math", 0.05, 1.0, True))
        self.assertEqual(topology.retire_underperformers(), (MATH.id,))
        self.assertNotIn(MATH.id, topology.active_resource_ids)
        self.assertEqual(topology.actions[-1].kind, TopologyActionKind.RETIRE)

    def test_checkpoint_rollback_restores_strategy_topology_and_history(self):
        topology = trained_topology()
        checkpoint = topology.checkpoint()
        topology.allocate(Workload("held-text-0", "text", "analyze"))
        topology.record(PerformanceObservation(TEXT.id, "text", 0.0, 2.0, False))
        topology.strategy = AllocationStrategy("experimental-strategy")
        topology.rollback(checkpoint)
        self.assertEqual(topology.strategy, STRATEGY)
        self.assertEqual(topology.active_resource_ids, checkpoint.active_resource_ids)
        self.assertEqual(topology.observations, checkpoint.observations)
        self.assertEqual(topology.actions[-1].kind, TopologyActionKind.ROLLBACK)

    def test_held_out_adaptation_beats_fixed_policy_with_credible_paired_result(self):
        adaptive = trained_topology()
        fixed = FixedResourcePolicy(GENERAL)
        workloads = tuple(
            Workload(f"held-{index}", "math" if index % 2 == 0 else "text", "analyze")
            for index in range(16)
        )
        outcomes = {}
        for workload in workloads:
            outcomes[(workload.id, GENERAL.id)] = (0.5, 1.0, True)
            outcomes[(workload.id, MATH.id)] = (0.9 if workload.family == "math" else 0.1, 1.0, True)
            outcomes[(workload.id, TEXT.id)] = (0.9 if workload.family == "text" else 0.1, 1.0, True)
        adaptive_utility = evaluate_policy(adaptive, workloads, outcomes)
        fixed_utility = evaluate_policy(fixed, workloads, outcomes)
        comparison = paired_policy_comparison(adaptive_utility, fixed_utility)
        self.assertEqual(comparison.paired_workloads, 16)
        self.assertAlmostEqual(comparison.mean_improvement, 0.3625)
        self.assertGreater(comparison.confidence_interval_95[0], 0)
        self.assertLess(comparison.randomization_p_value, 0.01)

    def test_missing_capability_and_outcome_fail_closed(self):
        topology = trained_topology()
        with self.assertRaisesRegex(ValueError, "no resource"):
            topology.allocate(Workload("proof-0", "proof", "prove"))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            evaluate_policy(topology, (Workload("held-unknown", "math", "analyze"),), {})


if __name__ == "__main__":
    unittest.main()
