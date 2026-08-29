# Baseline Laboratory

Phase 08 provides reproducible, resource-aware comparison infrastructure. A
`BaselineManifest` pins the system role and family, implementation/version/model
revision, weights digest where applicable, benchmark version, seeds, declared
hardware and software environment, reproduction command, training data, and
energy boundary.

The benchmark vocabulary spans algorithmic generalization, compositional
transfer, continual learning, online adaptation, causal/system identification,
memory, planning, and program induction. Every benchmark records why it matters,
known shortcuts, contamination risk, primary metric direction, and whether it is
exploratory, confirmatory, or only harness validation.

## Reproduction

The bundled lookup baseline is reproduced with:

```bash
python -m g0rd0n.evaluation run benchmarks/manifests/toy-lookup-baseline.json
```

It emits one JSON result containing all pinned seeds, metrics, modeled operations,
memory and latency, measured wall time, and the actual host environment. The toy
affine candidate intentionally dominates the lookup baseline on this trivial
out-of-domain affine task; this validates known rankings in the harness and is
not evidence about DNNs, Transformers, general intelligence, or physical energy.

## Analysis discipline

Paired comparisons require identical benchmark IDs, versions, and seed sets.
They report mean improvement, a deterministic paired bootstrap interval, and an
exact sign-randomization p-value for up to 20 nonzero pairs. Pareto analysis
requires explicit maximize/minimize directions for every metric. Reports retain
the study stage and energy boundary so harness checks cannot be mistaken for
scientific superiority claims.
