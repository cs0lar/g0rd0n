# AGENTS.md — g0rd0n

> **Mission:** find a computable Artificial General Intelligence paradigm that is provably more capable than current Deep Neural Network / Transformer approaches under explicit, scientifically meaningful resource bounds, while supporting continuous-operation energy profiles that approach or improve on the human brain's roughly 20 W power envelope.

This file is the operating contract and development roadmap for humans and coding agents working on `g0rd0n`.

Each roadmap phase below corresponds to **one reviewable pull request**. A phase is complete only when its acceptance criteria are satisfied, its experiments are reproducible, and its claims are no stronger than the evidence permits.

---

## 0. Prime directive

`g0rd0n` has one task:

> **Discover a simple, clever, elegant, computable AGI paradigm with a formally defensible advantage over contemporary DNN/Transformer paradigms and a plausible path to brain-like continuous energy use.**

Everything in the repository must serve this task.

If a component does not improve our ability to formulate questions, generate hypotheses, test them, preserve evidence, allocate resources, or derive proofs, it should not exist.

### Non-negotiable design imperative

When several designs satisfy the same scientific requirement, prefer the one that is:

1. **simpler** — fewer concepts, moving parts, dependencies, and hidden state;
2. **cleverer** — obtains more leverage from structure, reuse, inference, sparsity, or abstraction;
3. **more elegant** — clearer invariants, composable interfaces, and explanations a human can audit.

Complexity requires evidence.

---

# 1. Ask the right question first

The first job of every research cycle is not to answer a question. It is to improve the question.

The initial mission statement contains an important ambiguity:

> “provably more powerful than Transformers”

A sufficiently general computational model implemented with neural networks or Transformers may already be computationally universal under idealized assumptions. Therefore `g0rd0n` MUST NOT define success as “computes a larger set of computable functions” unless a genuine computability-theoretic separation is formally established.

Instead, the default research question is:

> **Does there exist a computable cognitive architecture that exhibits a strict, reproducible and preferably provable capability advantage over defined DNN/Transformer baselines under explicit resource bounds, while admitting a path to approximately 20 W continuous operation at useful scale?**

Candidate resource bounds include:

- energy per useful inference or learned bit;
- steady-state power;
- memory;
- communication bandwidth;
- training data;
- adaptation samples;
- wall-clock latency;
- sequential depth;
- parameter/storage footprint;
- compute operations;
- hardware area;
- catastrophic-forgetting resistance;
- continual-learning cost;
- transfer cost;
- search complexity;
- verification cost.

The system must keep the distinction between:

- **computability** — what can be computed at all;
- **complexity** — resources required to compute it;
- **learnability** — resources required to acquire the behaviour;
- **generality** — breadth of tasks and transfer;
- **autonomy** — ability to continue learning and acting;
- **efficiency** — useful capability per unit resource;
- **physical realizability** — whether the required computation can plausibly be embodied.

No claim may silently substitute one for another.

---

# 2. Definition of success

`g0rd0n` succeeds only when it produces a candidate paradigm satisfying all of the following.

## 2.1 Computable

The paradigm has an executable operational semantics or a precise reduction to a known computable model.

## 2.2 General

It demonstrates transfer or competence across sufficiently heterogeneous task families under a pre-registered evaluation protocol.

No single benchmark score counts as AGI evidence.

## 2.3 Strict advantage

At least one meaningful strict separation is established against named, reproducible DNN/Transformer baselines.

Preferred evidence, strongest first:

1. theorem with mechanically or independently checkable proof;
2. asymptotic separation under explicit assumptions;
3. lower-bound / upper-bound separation;
4. verified algorithmic advantage on a formally defined task family;
5. reproducible empirical Pareto dominance across a pre-registered suite.

Empirical superiority alone must be labelled empirical.

## 2.4 Energy path

The candidate has:

- a defined physical system boundary;
- measured or modelled energy consumption;
- idle and active power profiles;
- energy-per-operation or energy-per-task accounting;
- an explicit scaling model;
- a credible route toward approximately 20 W continuous operation.

“20 W” is a target envelope, not a rhetorical comparison. CPU/GPU/accelerator power, memory, communication, storage and supporting control logic must be accounted for when material.

## 2.5 Falsifiability

The paradigm has explicit observations that would cause `g0rd0n` to reject or downgrade it.

---

# 3. Scientific operating loop

Every research cycle follows this state machine:

```text
QUESTION
  ↓
DEFINITIONS + ASSUMPTIONS
  ↓
HYPOTHESES
  ↓
PREDICTIONS
  ↓
EXPERIMENT / PROOF ATTEMPT
  ↓
EVIDENCE
  ↓
REPLICATION / ADVERSARIAL REVIEW
  ↓
UPDATE BELIEFS + RESOURCE MODEL
  ↓
REVISE QUESTION
```

Skipping a state requires a written reason.

## Required research objects

Every serious candidate must have durable objects for:

- `Question`
- `Definition`
- `Assumption`
- `Hypothesis`
- `Prediction`
- `Experiment`
- `Observation`
- `Result`
- `Claim`
- `Counterexample`
- `ProofAttempt`
- `Proof`
- `Failure`
- `Decision`
- `ResearchProgram`

Each object must carry provenance.

---

# 4. Epistemic rules

## 4.1 Claims are not facts because an agent said them

Agent outputs are proposals until supported.

## 4.2 Negative results are first-class knowledge

A failed approach must record:

- what was tried;
- why it was plausible;
- the exact failure criterion;
- observed evidence;
- whether the failure is local or general;
- reusable lessons;
- what question should be asked next.

## 4.3 Preserve disagreement

Conflicting hypotheses or interpretations must coexist until resolved. Do not overwrite inconvenient evidence.

## 4.4 Separate observation from interpretation

Raw measurements, transformed data, statistical analysis and narrative conclusions must remain distinguishable.

## 4.5 Reproducibility before scale

Do not spend more compute on a result that cannot be reproduced at small scale.

## 4.6 Proof obligations travel with claims

Every claim should point to its evidence and, where applicable, its proof obligations.

---

# 5. Architectural principles

The orchestration architecture should remain small.

A minimal conceptual decomposition is:

```text
┌──────────────────────────────┐
│ Human / External Channels    │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ Research Governor            │
│ question · strategy · budget │
└───────┬─────────┬────────────┘
        │         │
        │         └───────────────┐
        ▼                         ▼
┌───────────────┐        ┌────────────────┐
│ Resource Mesh │        │ Evidence Store │
│ agents/tools  │        │ knk + artifacts│
└───────┬───────┘        └────────┬───────┘
        │                          │
        └───────────┬──────────────┘
                    ▼
           ┌─────────────────┐
           │ Evaluation Loop │
           │ tests + proofs  │
           └─────────────────┘
```

Avoid a zoo of named agents unless specialization is demonstrated to improve outcomes.

Prefer **roles as data** over hard-coded agent classes.

---

# 6. Resource mesh

A resource is anything `g0rd0n` can invoke:

- human;
- model/agent;
- program;
- theorem prover;
- simulator;
- benchmark;
- dataset;
- compiler;
- knowledge source;
- external API/channel;
- hardware target;
- experimental apparatus.

Each resource should expose a capability profile:

```yaml
id:
kind:
capabilities:
inputs:
outputs:
cost_model:
latency_model:
reliability:
rate_limits:
context_limits:
permissions:
provenance:
historical_performance:
```

The governor chooses resources based on expected information gain or expected progress **per unit cost**, not prestige or novelty.

---

# 7. Self-improvement

`g0rd0n` may improve:

- resource selection;
- task decomposition;
- agent topology;
- prompt/program policies;
- retrieval strategy;
- experiment scheduling;
- hypothesis ranking;
- budget allocation;
- stopping rules;
- replication policy.

It must not silently redefine its mission or success criteria.

Every self-modification must produce a before/after evaluation and retain the previous strategy so the change is reversible.

A self-improvement is accepted only if it improves a declared metric on held-out historical or synthetic research episodes without degrading critical invariants.

---

# 8. Budget governance

Budget is part of the scientific state.

Track at minimum:

- tokens by provider/model;
- monetary cost;
- API calls;
- rate-limit consumption;
- wall-clock time;
- CPU/GPU/accelerator time;
- energy where measurable;
- network bytes where material;
- human review time where estimable.

Every research action should have:

```yaml
estimated_cost:
maximum_cost:
expected_value:
stop_condition:
actual_cost:
```

The default scheduling heuristic is:

> **maximize expected information gain × mission relevance ÷ total resource cost**

This heuristic is advisory until validated.

## Budget classes

Use explicit classes:

- `tiny` — question refinement, retrieval, local tests;
- `small` — cheap hypothesis elimination;
- `medium` — controlled experiments;
- `large` — replication or scaling;
- `exceptional` — only after human approval and strong prior evidence.

Large expenditure before cheap falsification is an architectural failure.

---

# 9. Knowledge architecture

`g0rd0n` may use [`knk`](https://github.com/cs0lar/knk) as its machine-facing knowledge kernel.

`knk` is a strong fit because it provides an append-only, bitemporal assertion model with provenance, hypotheses, conflict discovery and an MCP command surface. Its log-as-source-of-truth model aligns with `g0rd0n`'s requirement to preserve how scientific beliefs change over time.

The integration MUST keep `knk` replaceable behind a narrow `KnowledgeStore` interface until usage proves otherwise.

## Proposed assertion vocabulary

Examples:

```text
<Question Q> --has_hypothesis--> <Hypothesis H>
<Hypothesis H> --predicts--> <Prediction P>
<Experiment E> --tests--> <Hypothesis H>
<Observation O> --observed_in--> <Experiment E>
<Result R> --derived_from--> <Observation O>
<Result R> --supports--> <Hypothesis H>
<Result R> --contradicts--> <Hypothesis H>
<Claim C> --supported_by--> <Result R>
<Claim C> --depends_on--> <Assumption A>
<Failure F> --invalidates--> <ResearchPath X>
```

Confidence is never a substitute for evidence links.

---

# 10. Obsidian repository

Obsidian may be the human-facing repository for long-form textual work because it operates on local/open files and supports linked notes.

The Obsidian vault is a **projection and authoring surface**, not the machine source of truth for structured assertions.

Suggested layout:

```text
vault/
  00-mission/
  01-questions/
  02-definitions/
  03-hypotheses/
  04-experiments/
  05-results/
  06-theories/
  07-proofs/
  08-failures/
  09-decisions/
  10-reviews/
  20-literature/
  30-candidates/
  40-benchmarks/
  90-sessions/
  99-generated/
```

Machine-generated notes must be visibly marked as generated.

Stable IDs should connect notes to knowledge-kernel entities.

---

# 11. Repository conventions

Suggested initial layout:

```text
g0rd0n/
  AGENTS.md
  README.md
  pyproject.toml
  g0rd0n/
    core/
    models/
    resources/
    governor/
    knowledge/
    research/
    evaluation/
    budget/
    adapters/
  experiments/
  proofs/
  benchmarks/
  schemas/
  tests/
  docs/
  vault/
```

Keep the core free of provider-specific logic.

External systems belong behind adapters.

---

# 12. Roadmap — one phase = one pull request

The roadmap intentionally builds the scientific spine before autonomous orchestration.
The root branch for this project is `feature/gpt`; every PR will target that branch.

---

## PR 01 — Mission, vocabulary and falsifiable success contract

### Goal

Make the problem precise enough that the system can fail.

### Deliver

- repository skeleton;
- this `AGENTS.md`;
- machine-readable `MissionSpec`;
- glossary for computability, capability, generality, efficiency and energy;
- definition of baseline families;
- claim-strength taxonomy;
- success/failure criteria;
- ADR template;
- research-object schemas.

### Critical decision

Adopt **resource-bounded separation** as the default interpretation of “more powerful.”

### Tests

- schemas validate;
- contradictory definitions are rejected;
- every success criterion has a measurable or formally checkable field.

### Merge gate

A skeptical reviewer can answer:

> “What exact observation would prove this project wrong?”

If the answer is unclear, do not merge.

---

## PR 02 — Reproducible research ledger

### Goal

Represent the scientific method as durable state.

### Deliver

- data models for the research objects in §3;
- immutable event/transition log;
- provenance model;
- content hashing;
- deterministic serialization;
- local file-backed reference implementation.

### Tests

- complete research cycle can be replayed from an empty store;
- no mutation destroys previous scientific state;
- a result can be traced to raw evidence.

### Merge gate

Replaying the same ledger reconstructs the same research state.

---

## PR 03 — KnowledgeStore interface + `knk` adapter

### Goal

Give `g0rd0n` temporal, provenance-aware knowledge without coupling the project to one storage engine.

### Deliver

```text
KnowledgeStore
  assert()
  retract()
  supersede()
  query()
  history()
  provenance()
  conflicts()
```

- in-memory adapter;
- `knk` adapter via its supported command/MCP surface;
- mapping between research objects and assertions;
- conflict and temporal-query tests.

### Tests

Contract tests run identically against both adapters.

### Merge gate

Deleting the `knk` adapter does not require changes to research logic.

---

## PR 04 — Obsidian projection

### Goal

Make the research state legible and editable by humans.

### Deliver

- deterministic Markdown projection from research state;
- note templates;
- stable object IDs;
- wikilinks between related objects;
- generated/manual ownership markers;
- import policy for human edits.

### Tests

- projection is deterministic;
- regenerating does not destroy human-authored regions;
- all scientific claims link back to structured evidence.

### Merge gate

A human can audit one complete experiment from question to conclusion using only the vault and linked evidence.

---

## PR 05 — Resource registry and invocation boundary

### Goal

Model agents, humans, tools and channels uniformly without building a complex agent framework.

### Deliver

- `Resource` and `Capability` schemas;
- invocation protocol;
- permission model;
- rate-limit model;
- timeout/cancellation;
- mock resources;
- adapter API for LLMs, programs and humans.

### Tests

- deterministic fake resources;
- timeout and failure recovery;
- permissions enforced;
- costs recorded for every invocation.

### Merge gate

Adding a new model/provider requires only an adapter and configuration.

---

## PR 06 — Transparent budget engine

### Goal

Make resource use inspectable before autonomous work begins.

### Deliver

- token/currency/call/time accounting;
- per-session and per-program budgets;
- hard/soft limits;
- pre-flight estimates;
- stop conditions;
- cost ledger;
- human-readable session report.

### Tests

- hard budget cannot be exceeded by normal execution;
- failed calls still account for cost;
- estimated vs actual cost is reported.

### Merge gate

Every action in an integration test has attributable cost.

---

## PR 07 — Minimal research governor

### Goal

Implement the smallest useful closed research loop.

### Deliver

A governor capable of:

1. loading mission and current question;
2. proposing improved questions;
3. selecting one;
4. generating hypotheses;
5. proposing cheap discriminating tests;
6. invoking resources;
7. recording evidence;
8. updating hypothesis status;
9. deciding stop/continue/escalate.

No dynamic multi-agent network yet.

### Selection policy

Prefer experiments with high expected discrimination and low cost.

### Tests

Use synthetic worlds where the correct hypothesis is known.

### Merge gate

The governor converges more reliably than random search on the synthetic suite within a fixed budget.

---

## PR 08 — Baseline laboratory

### Goal

Make comparisons against DNN/Transformer systems reproducible and fair.

### Deliver

- baseline manifest format;
- model/version/hardware/environment capture;
- benchmark harness;
- seed control;
- container/reproducibility manifest;
- statistical comparison library;
- Pareto-front reporting.

Initial benchmark families should test more than language modelling, for example:

- algorithmic generalization;
- compositional transfer;
- continual learning;
- online adaptation;
- causal/system identification;
- memory;
- planning;
- program induction.

### Tests

Known toy systems produce expected rankings.

### Merge gate

A third party can reproduce at least one complete baseline result from the manifest.

---

## PR 09 — Energy accounting laboratory

### Goal

Turn the 20 W target into an engineering measurement problem.

### Deliver

- `EnergyProfile` schema;
- clear system-boundary definitions;
- idle/active/average power;
- joules/task;
- joules/learned update;
- energy-delay product;
- optional hardware counters;
- modelled-energy fallback with uncertainty;
- scaling projections.

### Rules

Never compare a candidate chip-level number against a baseline whole-system number.

Always report measurement boundaries and uncertainty.

### Tests

Synthetic meters plus at least one real host measurement path where supported.

### Merge gate

The same workload can produce a capability-cost-energy record suitable for Pareto comparison.

---

## PR 10 — Candidate paradigm specification language

### Goal

Represent alternative cognitive architectures as executable, comparable hypotheses rather than essays.

### Deliver

A minimal declarative `ParadigmSpec`, for example:

```yaml
id:
primitives:
state:
memory:
learning_rule:
inference_rule:
communication:
adaptation:
hardware_assumptions:
complexity_claims:
energy_hypothesis:
falsifiers:
```

Provide a runner interface for executable candidates.

Candidate families might include, without presupposing success:

- sparse/event-driven computation;
- program synthesis / algorithmic induction;
- active inference;
- predictive processing;
- differentiable + symbolic hybrids;
- cellular/graph rewriting systems;
- reservoir/dynamical systems;
- neuromorphic/spiking approaches;
- memory-centric architectures;
- self-modifying program systems.

This list is search-space scaffolding, not endorsement.

### Tests

At least two radically different toy paradigms execute through the same interface.

### Merge gate

The evaluation harness is paradigm-neutral.

---

## PR 11 — Hypothesis search and adversarial science

### Goal

Let `g0rd0n` search ideas without becoming its own confirmation machine.

### Deliver

- candidate generator;
- critic role;
- falsifier role;
- replication role;
- novelty/deduplication check;
- explicit alternative hypotheses;
- red-team review;
- evidence-weight update;
- stopping rules for dead programs.

Roles may share the same underlying model; role separation is epistemic, not necessarily computational.

### Required behaviour

For every promoted hypothesis, generate:

- strongest plausible competing explanation;
- cheapest falsifying experiment;
- hidden assumptions;
- known failure modes.

### Merge gate

On seeded flawed hypotheses, the adversarial loop rejects them more often than the non-adversarial PR-07 loop at comparable cost.

---

## PR 12 — Adaptive resource topology

### Goal

Add the self-organising agent/resource network only after simple orchestration has a baseline.

### Deliver

- strategy representation;
- topology as data;
- historical performance model;
- allocation policy;
- dynamic spawn/retire/reuse;
- strategy checkpoints;
- rollback;
- held-out meta-evaluation.

Possible policy objective:

```text
expected research progress
--------------------------
expected total resource cost
```

### Tests

Compare adaptive scheduling against fixed policies on historical/synthetic research workloads.

### Merge gate

Adaptive topology must demonstrate statistically credible improvement over the simpler fixed governor.

If it cannot, keep the simpler system.

---

## PR 13 — Proof and formal-analysis workbench

### Goal

Distinguish “interesting benchmark win” from “provable advantage.”

### Deliver

- formal claim schema;
- assumptions;
- proof obligations;
- theorem-prover adapters where useful;
- proof artifact storage;
- independent verification command;
- counterexample search;
- complexity-bound templates.

### Target theorem shape

Prefer statements like:

> For task family **T**, under assumptions **A**, architecture **X** achieves bound **Bₓ**, while architecture class **Y** requires bound **Bᵧ**, with **Bₓ** strictly better in resource **R**.

Avoid vague global-superiority theorems.

### Merge gate

Repository contains at least one fully checkable toy separation theorem end-to-end through the workbench.

---

## PR 14 — Automated research-program lifecycle

### Goal

Run bounded autonomous research programs safely and reproducibly.

### Deliver

- `ResearchProgram` specification;
- explicit budget;
- session checkpoints;
- resumability;
- escalation policy;
- human-review gates;
- experiment queue;
- failure recovery;
- end-of-session research report.

### Required final report

Every autonomous session emits:

- question asked;
- hypotheses considered;
- experiments performed;
- evidence obtained;
- claims changed;
- failures;
- money/tokens/compute/energy spent;
- unresolved uncertainty;
- best next question.

### Merge gate

A multi-session synthetic discovery task can be paused, replayed and audited.

---

## PR 15 — First real discovery campaign

### Goal

Use the machinery to test `g0rd0n` on its actual mission.

### Before running

Pre-register:

- question;
- candidate space;
- Transformer/DNN baselines;
- task families;
- resource constraints;
- energy boundary;
- success thresholds;
- falsifiers;
- total campaign budget.

### Campaign sequence

1. literature and prior-art map;
2. formalize strongest candidate separations;
3. eliminate candidates with cheap counterexamples;
4. implement smallest surviving candidates;
5. test on toy separations;
6. test generalization/continual-learning suite;
7. measure resource curves;
8. replicate;
9. attempt formal bound/proof;
10. revise the question.

### Merge gate

The PR does **not** need to discover AGI.

It must produce a scientifically useful outcome:

- a surviving candidate with stronger evidence;
- a falsified candidate class;
- a new theorem/bound;
- a negative result that narrows the space;
- or a materially better formulation of the central question.

---

# 13. PR review protocol

Every PR must contain:

```markdown
## Question
What question does this PR answer?

## Hypothesis
What do we believe will improve?

## Minimal change
Why is this the smallest coherent implementation?

## Evidence
What tests/experiments support it?

## Falsifier
What result would tell us this approach is wrong?

## Cost
What did development/evaluation consume?

## Complexity delta
What concepts, dependencies and state were added?

## Reversibility
How can this change be removed or rolled back?

## New knowledge
What did we learn regardless of merge outcome?
```

A reviewer should reject a PR when complexity is justified only by anticipated future needs.

---

# 14. Testing hierarchy

Use the cheapest valid test first:

1. schema/type/property test;
2. deterministic unit test;
3. synthetic counterexample;
4. toy-world experiment;
5. small real benchmark;
6. ablation;
7. replication;
8. scaling experiment;
9. hardware experiment;
10. formal proof / independent proof verification where applicable.

Do not jump to level 8 when level 3 can kill the hypothesis.

---

# 15. Evidence and benchmark discipline

A benchmark is useful only if it discriminates between hypotheses.

Avoid optimizing against a static leaderboard.

For every benchmark record:

- task family;
- reason it matters to general intelligence;
- known shortcuts;
- train/test contamination risk;
- baseline details;
- uncertainty;
- resource usage;
- energy boundary;
- whether the result was exploratory or confirmatory.

Use held-out confirmatory tests for promoted claims.

---

# 16. Candidate promotion ladder

Candidates move through:

```text
IDEA
→ COHERENT
→ EXECUTABLE
→ NOT-TRIVIALLY-FALSIFIED
→ TOY-ADVANTAGE
→ REPLICATED-ADVANTAGE
→ RESOURCE-SEPARATION
→ FORMAL-SUPPORT
→ HARDWARE-PATH
→ GENERALITY-EVIDENCE
→ LEADING-CANDIDATE
```

Promotion requires evidence.

Demotion is normal.

---

# 17. Simplicity budget

Track architectural complexity like any other cost.

Possible indicators:

- source lines;
- dependency count;
- number of abstractions;
- number of persistent state types;
- number of resource-specific branches;
- configuration surface;
- cognitive load in ADR review.

No metric is absolute; the purpose is to make complexity visible.

Every new subsystem must identify the subsystem or repeated manual process it replaces.

---

# 18. Human role

Humans are first-class resources, not merely approval endpoints.

Humans should be preferentially invoked for:

- redefining ambiguous goals;
- judging scientific importance;
- spotting category errors;
- reviewing surprising evidence;
- approving exceptional budgets;
- interpreting failures;
- deciding whether a candidate is elegant enough to pursue.

The system should optimize human attention as a scarce resource.

---

# 19. Safety and containment

Although the goal is scientific discovery, self-improvement must remain bounded.

Default rules:

- least privilege;
- explicit external-write permissions;
- no silent credential acquisition;
- no uncontrolled replication;
- no bypass of budget gates;
- reversible strategy changes;
- full invocation provenance;
- no modification of mission invariants by autonomous processes.

Capability research and operational autonomy are distinct concerns.

---

# 20. Initial implementation choices

Until evidence says otherwise:

- prefer Python for orchestration and experiments;
- use typed schemas;
- use subprocess/tool boundaries rather than deep framework coupling;
- keep core logic deterministic where possible;
- store raw artifacts content-addressably;
- use Git as the review boundary;
- use Markdown for human-readable scientific output;
- keep `knk` behind `KnowledgeStore`;
- keep Obsidian as a view/editor over open Markdown files;
- do not adopt a heavyweight “multi-agent framework” in the first ten PRs.

---

# 21. What not to build yet

Do **not** initially build:

- a general distributed agent platform;
- a custom LLM;
- a custom vector database;
- a GUI;
- an elaborate agent personality system;
- autonomous code deployment;
- a complex ontology;
- a full workflow DSL;
- custom hardware;
- large-scale training infrastructure.

Any of these may become justified by evidence later.

---

# 22. First research question after the platform exists

The platform should begin with a narrower version of the mission:

> **Which computational primitives permit strict reductions in adaptation, memory movement, or sequential-compute cost for continual algorithmic learning, relative to strong Transformer baselines, without sacrificing broad transfer?**

Why start here:

- it is narrower than “find AGI”;
- it exposes formal complexity questions;
- it connects directly to energy through memory movement and sparse/event-driven computation;
- it admits synthetic tasks with known structure;
- candidates can be killed cheaply;
- successful primitives can compose into larger architectures.

The system should still be permitted to reformulate this question when evidence warrants it.

---

# 23. Repository-wide definition of done

A change is done when:

- it advances the mission;
- its assumptions are explicit;
- it is tested;
- its evidence is reproducible;
- its costs are visible;
- its provenance is preserved;
- it is simpler than reasonable alternatives or demonstrates why added complexity pays;
- a human can understand why it exists;
- removing it later is possible.

---

# 24. Guiding maxim

> **Do not build an artificial scientist that looks intelligent. Build the smallest system that makes the science better.**
