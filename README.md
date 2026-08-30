# g0rd0n

`g0rd0n` is a scientific research system for finding and testing computable
cognitive architectures under explicit capability, learning, resource, and
energy bounds. The project treats resource-bounded separation—not unrestricted
computability—as its default interpretation of “more powerful.”

## Phase 01

This phase defines the falsifiable contract on which later orchestration will
depend:

- `config/mission.json` is the canonical, machine-readable mission.
- `g0rd0n/core/` contains dependency-free typed models and validation.
- `schemas/` documents the stable JSON shapes for research objects.
- `docs/` records vocabulary, baseline families, and decision rationale.

Validate the current phase with:

```bash
python -m unittest discover -s tests -v
python -m g0rd0n validate config/mission.json
```

Phase 02 adds a dependency-free, hash-chained research ledger in
`g0rd0n/research/`. It rebuilds state from immutable JSONL events and keeps raw
evidence in a content-addressed artifact directory; see
`docs/research-ledger.md` for its invariants and usage model.

Phase 03 adds the replaceable `KnowledgeStore` boundary under
`g0rd0n/knowledge/`, with contract-equivalent in-memory and `knk` MCP adapters.
See `docs/knowledge-store.md` for the supported temporal assertion model.

Phase 04 adds a deterministic Obsidian projection in `g0rd0n/projection/`.
Generated notes preserve explicit human-owned regions, use stable wikilinks, and
copy hash-verified evidence into the vault; see `docs/obsidian-projection.md`.

Phase 05 adds the uniform resource registry and invocation boundary under
`g0rd0n/resources/`, including permissions, rate limits, timeout/cancellation,
context validation, deterministic fakes, and attributable per-invocation costs.

Phase 06 adds durable budget governance under `g0rd0n/budget/`: program and
session limits, concurrency-safe maximum-cost reservations, stop conditions,
hash-chained cost events, and estimated-versus-actual Markdown reports.

Phase 07 adds the minimal closed research loop under `g0rd0n/governor/`. It
improves questions, tests competing hypotheses with cheap discriminating
experiments, preserves evidence, updates statuses, and makes explicit
stop/continue/escalate decisions through budgeted resources.

Phase 08 adds the baseline laboratory under `g0rd0n/evaluation/`: pinned
manifests, seeded benchmark execution, environment/resource capture, paired
statistics, Pareto reporting, and a one-command toy reproduction example.

Phase 09 adds boundary-aware energy accounting under `g0rd0n/evaluation/`:
idle/active power, per-task and per-update energy, energy-delay product,
uncertainty-bearing projections, synthetic meters, and optional Linux RAPL
package measurement. Energy Pareto comparisons reject mismatched boundaries.

Phase 10 adds executable candidate descriptions under `g0rd0n/paradigms/`.
Typed `ParadigmSpec` documents architecture, assumptions, claims, energy
hypotheses, and falsifiers while a common runner and benchmark adapter keep the
evaluation harness paradigm-neutral.

Phase 11 adds an adversarial science loop under `g0rd0n/governor/`. Roles remain
data over a shared backend while candidate deduplication, competing explanations,
cheap falsifiers, evidence-weight updates, replication, and stopping rules make
hypothesis promotion explicitly resistant to confirmation bias.

Phase 12 adds checkpointed adaptive resource topology under `g0rd0n/governor/`.
It learns progress per total cost by workload family, activates or reuses useful
resources, retires consistently poor ones, and compares itself with fixed
scheduling on held-out paired workloads.

Phase 13 adds formal claims and verifier adapters under `g0rd0n/proofs/`, plus
content-addressed proof artifacts, counterexample search, reusable complexity
bounds, and an independently checkable toy membership-query separation theorem.

The contract intentionally makes failure possible. A candidate is not promoted
unless it is executable, evaluated across heterogeneous task families, strictly
better than named baselines under a declared resource bound, energy-accounted,
and paired with observations that would falsify it.
