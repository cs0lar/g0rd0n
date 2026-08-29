# Minimal Research Governor

Phase 07 implements one bounded closed research loop without a dynamic agent
network. A configured resource exposes four capabilities: improve questions,
generate competing hypotheses, propose experiments with explicit predictions,
and execute an experiment. Every call passes through the resource registry and
budget engine.

The governor—not the proposing resource—selects questions by declared mission
relevance, clarity, and falsifiability. It selects experiments by exact pairwise
prediction discrimination divided by declared cost units. Ties are resolved by
cost and stable ID, making the policy reproducible.

Before execution, the ledger records the experiment and a `Prediction` for each
active hypothesis. After execution it stores structured raw evidence as a
content-addressed artifact, derives a `Result`, records support and contradiction
relations, and rejects hypotheses whose predictions disagree with observation.

The stopping rule returns:

- `stop` when exactly one declared hypothesis survives;
- `continue` when the per-cycle experiment limit is reached but discriminating
  work remains;
- `escalate` when resources/budget fail, all hypotheses are contradicted, or no
  remaining experiment can discriminate.

Synthetic-world tests hold generation constant and show that discrimination per
cost converges more often than seeded random experiment selection under the same
one-experiment budget. This is evidence for the scheduling policy only, not an
AGI or real-world discovery claim.
