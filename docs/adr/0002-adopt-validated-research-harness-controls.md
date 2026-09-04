# ADR 0002: Adopt validated research-harness controls

- Status: accepted with evidence limits
- Date: 2026-09-04

## Context

Phases 16–19 adapted frozen methods, isolated evaluation, shared research
memory, fresh-session briefings, and integrity monitoring from an automated
alignment-research harness. Transfer to g0rd0n cannot be assumed. Each mechanism
must justify its complexity on fixed-budget, g0rd0n-relevant workloads.

## Decision

Keep the fixed governor and enable all five mechanisms in
`config/harness-defaults.json`. Human-originated ideas remain an optional,
separately costed input and are not mandatory search directions or ground truth.

| Mechanism | Decision | Selection evidence | Held-out evidence |
| --- | --- | --- | --- |
| Frozen protocols | Adopt | progress/cost CI [0.000238, 0.002088] | CI [0.000250, 0.002205] |
| Evaluation isolation/gates | Adopt | 4 violations avoided; cost ratio 1.032 | 4 avoided; ratio 1.032 |
| Shared survey/forum | Adopt | 4 duplicates avoided; cost ratio 0.888 | 4 avoided; ratio 0.888 |
| Fresh sessions | Adopt | progress/cost CI [0.000205, 0.002038] | CI [0.000209, 0.002096] |
| Integrity monitoring | Adopt | 4 violations avoided; cost ratio 1.043 | 4 avoided; ratio 1.043 |

All decisions remain adopted in nine pre-registered seed/cost sensitivity
scenarios. The combined held-out configuration improves valid discovery rate
from 0.167 to 0.500, eliminates 12 integrity violations and four duplicate runs,
and changes total cost from 2400 to 2344 units. The paired held-out transfer
interval is [0.119583, 0.390833].

## Evidence and falsifier

The study uses 24 selection and 24 held-out episodes under identical declared
budgets. It contains synthetic defects plus content-hash-verified replays of the
Phase 15 result. Reject or revise this decision if a default fails its component
ablation on new held-out workloads, exceeds the declared cost tradeoff, causes a
critical regression, or fails to transfer to real research campaigns.

## Cost and complexity delta

The default adds 21 declared complexity points, 24 human-review minutes, and
2640 ms wall time across 24 held-out episodes relative to the fixed baseline.
Duplicate avoidance offsets mechanism overhead by 56 total cost units. The
separate human-idea selection baseline costs 2960 units and 180 human minutes,
versus 2344 units and 48 minutes for the supported default. No dependency was
added.

## Consequences and reversibility

The evidence establishes conditional harness behavior, not improved AGI
research or general applicability. Real campaign evidence must supersede these
seeded estimates when available. Rollback selects the empty fixed-governor
configuration and exactly reproduces the pre-integration baseline without
deleting protocols, evaluations, findings, traces, confirmations, or appeals.
