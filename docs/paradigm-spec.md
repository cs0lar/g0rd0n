# Candidate Paradigm Specifications

`ParadigmSpec` turns an architectural hypothesis into a versioned, executable
research object. A spec declares primitives, state, memory, learning and
inference rules, communication, adaptation, hardware assumptions, bounded
complexity claims, an energy hypothesis, and explicit falsifiers. The `runner`
field selects execution code without embedding provider or benchmark logic in
the spec.

`ParadigmRunner.execute()` accepts the same inputs for every paradigm and
returns output, resource use, and an auditable trace. `ParadigmBenchmarkSystem`
adapts that contract to the seeded Phase 08 harness, keeping metrics and cases
outside candidate implementations.

The example specs are intentionally unlike one another: one toggles a single
bit on sparse events, while the other materializes a graph and reduces it with
symbolic rewrite rules. Both solve toy parity through the same interface. This
demonstrates interface neutrality only; it is not evidence for generality,
energy efficiency, or advantage over neural baselines.
