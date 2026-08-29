# Adaptive Resource Topology

Phase 12 represents scheduling as data. `AllocationStrategy` declares the
progress-per-total-cost objective, exploration strength, spawn amortization,
and retirement evidence threshold. `ResourceStrategyProfile` describes
capabilities, expected invocation and spawn cost, and a conservative prior.

`AdaptiveResourceTopology` learns observed utility by workload family. It may
activate a catalogued resource, reuse an active one, or retire a consistently
poor performer. These are scheduling-state transitions only: provider creation
and termination remain adapter responsibilities and retain Phase 05 permission
and budget boundaries.

Checkpoints capture the strategy, active topology, observations, and action log.
Rollback restores that state and records the rollback. Held-out meta-evaluation
uses paired workloads, bootstrap uncertainty, and a sign-randomization test
against a fixed policy.

The synthetic suite contains stable family specialists, so adaptation should
win. It verifies that the allocator can learn and exploit structure; it does not
show that adaptive topology helps on real research workloads. If held-out real
episodes do not show credible improvement, the fixed governor should remain the
default.
