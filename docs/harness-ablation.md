# Harness ablation and adoption

Phase 20 evaluates the mechanisms imported from the automated-research harness
before making them defaults. The registered study expands 12 workload groups
into 24 selection and 24 untouched held-out episodes. Two selection groups
replay the content-addressed Phase 15 result; the others seed explicit harness
defects across heterogeneous synthetic research families.

Every run uses the fixed governor, identical ordered workload IDs, and an exact
budget hash. The matrix includes the fixed-governor baseline, five cumulative
configurations, five full-minus-one component ablations, and separately costed
human-originated ideas. Human ideas neither define truth nor influence mechanism
selection.

Adoption uses selection workloads only. A mechanism must show a positive paired
progress-per-cost interval, avoid at least three integrity violations within the
1.10 cost-ratio ceiling, or avoid at least three duplicate executions within
that ceiling. Held-out results then confirm—but never change—the selected
configuration. Bootstrap seeds and cost ceilings are varied across nine
sensitivity scenarios.

```bash
uv run python -m g0rd0n.ablation \
  benchmarks/ablation/phase-20-workloads.json \
  config/harness-defaults.json \
  --repository-root .
```

The committed result supports all five mechanisms conditionally on this seeded
suite. The default raises valid discovery rate from 0.167 to 0.500 on held-out
episodes, eliminates 12 accepted integrity violations and four duplicate runs,
and lowers total cost from 2400 to 2344 units. Its held-out paired
progress-per-cost interval is [0.000880, 0.003395]. These are harness-validation
results, not evidence of AGI capability or proof that the mechanisms improve
open-ended research. The ADR requires renewed evaluation on real campaigns.

`AdoptionPlan.rollback_configuration()` returns the empty fixed-governor
configuration. Re-running it reconstructs the baseline outcomes and metrics
exactly; no prior method, finding, or integrity record is deleted.
