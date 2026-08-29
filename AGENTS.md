# AGENTS.md

## Project: g0rd0n

`g0rd0n` is a research instrument with a single task:

> Find a computable AGI paradigm that is provably more powerful than deep neural
> networks / transformers, and that supports energy profiles approximating or improving
> on a brain's (~20 W, continuous).

It pursues that task by organising networks of agents, humans, tools, skills, knowledge
kernels, and external channels, and by improving how it organises them as it learns what
works.

`g0rd0n` is not a chatbot, an autonomous researcher, or a model-training pipeline. It is a
**bookkeeping machine for a research programme**: it records what is claimed, who claimed
it, what would refute it, what it cost to find out, and what happened when someone tried.
Everything else in this document is downstream of that.

---

## Core Concept

The primitive is not a task, a prompt, a plan, or an agent. The primitive is a **Wager**:

```
claim  +  test  +  price  +  kill-criterion  →  verdict
```

A Wager is a falsifiable claim with money attached and a stated way to lose. Nothing in
`g0rd0n` spends a token except in service of settling a Wager, and no Wager is opened
without a parent Question.

This single primitive collapses three systems into one:

- **Scientific method.** A claim with no kill-criterion is not a hypothesis, and `g0rd0n`
  refuses to open a Wager on it.
- **Budget control.** A Wager's price is reserved before work starts, so every dollar in
  the ledger maps to exactly one claim. "What did this session buy?" is a `GROUP BY`.
- **Self-improvement.** A settled Wager is a labelled training example for the allocator:
  *this playbook, at this price, produced this verdict.* Meta-learning is just statistics
  over settled Wagers.

The whole loop:

```
Question  →  Wagers  →  Settlement  →  supersede/retract  →  better Question
```

The loop always re-enters at the Question. A refuted candidate is not a dead end; it is
evidence that the question was wrong, and the question is the thing `g0rd0n` improves
first.

---

## The Imperative

**Simple, clever, elegant.** Non-negotiable, and enforced, not aspirational.

Operationally, for every PR and every artifact `g0rd0n` produces:

1. **One primitive.** If a change introduces a second way to express something the Wager
   or the assertion vocabulary already expresses, the change is wrong.
2. **Deletion criterion.** Every module states, in its docstring, the settled Wager that
   would lose its verdict if the module were deleted. No such Wager, no module.
3. **One page.** Every mechanism must be explainable on one page to a competent outsider.
   If it can't be, it is not understood well enough to be built yet.
4. **Cleverness is leverage, not obscurity.** A clever design does more with less
   machinery. A design that does the same with more machinery is neither clever nor
   elegant, whatever it is called in the PR description.

Reviewers ask one question before any other: *could this be half the size?*

---

## The Two Energies (do not conflate)

Two distinct quantities in this project are both measured in joules and are constantly
confused. Keep them separate everywhere in code, docs, and vault notes:

- **`operating_cost`** — what `g0rd0n` itself spends to do research: tokens, USD,
  wall-clock, GPU-hours, human attention. Budgeted, reserved, and settled per Wager.
- **`target_energy`** — the energy profile of a *candidate paradigm* being evaluated:
  joules per unit of task-relevant work. This is a **measured outcome variable**, never a
  budget. It is the thing the research is about.

`g0rd0n` running expensively is acceptable. A candidate paradigm scoring badly on
`target_energy` is a result.

---

## The Question (seed framing, Phase 5 output supersedes this)

The task as stated is not yet well-posed, and the first real work is making it so. This
section is the *seed*, committed to the kernel as `Hypothesis`-status assertions. Phase 5
supersedes it with a versioned Charter. It is written down here so that the first thing
`g0rd0n` does is disagree with something specific.

### The Turing trap

"Provably more powerful than transformers" is ill-posed on its face. A decoder with
unbounded chain-of-thought and unbounded precision is already Turing-complete, and so is
any candidate worth calling AGI. Two Turing-complete systems cannot be separated on
computability. Any well-posed version of the question must therefore be
**resource-relative**: it must name the resource held fixed.

Three admissible separation shapes:

- **S1 — Expressivity at fixed resource.** A task family solvable by paradigm P within
  budget B that no transformer solves within B. Seed anchor: fixed-depth, log-precision
  transformers are believed to sit inside uniform `TC⁰`, and chain-of-thought buys depth
  back by spending serial steps. Any S1 claim must state which of depth, precision, steps,
  or parameters is pinned.
- **S2 — Learnability.** A sample-complexity, gradient-complexity, or
  continual-learning separation on a task family, rather than an expressivity one. A
  paradigm that can represent something no one can train it to represent is not more
  powerful in any sense that matters here.
- **S3 — Thermodynamic.** Joules per unit of task-relevant information at *matched
  capability*. Seed anchors, all to be verified before use: Landauer's floor ~3×10⁻²¹ J
  per irreversible bit at 300 K; brain ~20 W across ~10¹⁴–10¹⁵ synapses at low average
  firing rates, implying something like 10⁻¹⁴ J per synaptic event, which is many orders
  above Landauer and therefore leaves headroom; contemporary accelerator inference
  measured at the wall, which is where the interesting gap probably is.

**Numbers in this section are unverified seeds.** They enter the kernel as `Hypothesis`
with provenance `"AGENTS.md seed, unverified"`, and Phase 6 must either corroborate them
against primary sources or retract them. An agent that cites them as established fact has
violated the provenance rule.

### Falsifiability gate

Before any spend, a candidate must state:

1. the resource held fixed,
2. the task family,
3. the measurement procedure and its instrument,
4. the observation that would kill it, and its price.

No item 4, no Wager. This gate is code (Phase 7), not a norm.

### Candidate portfolio (priors, not endorsements)

Seeded so Phase 7 has something to allocate over, and so that the first act of the
Evidence Channel is to prune it: predictive coding / active inference; spiking and
event-driven computation on neuromorphic substrates; equilibrium propagation and analog
in-memory learning; hyperdimensional computing / vector-symbolic architectures;
energy-based and Hopfield-style associative models; program synthesis and
compression-driven induction (MDL, Solomonoff-flavoured); neural cellular automata and
local-update systems; reservoir and physical computing; sparse-conditional and
mixture-routed architectures as the "transformers, but not really" control arm.

The control arm is mandatory. A candidate that beats a badly-tuned transformer baseline
has demonstrated nothing.

---

## Current Roadmap

Each phase is **one PR**, sized to be understood in one sitting. Agents must not jump
ahead. If a phase's diff grows past what a reviewer can hold in their head, split it and
say so in the PR description; the phase numbering tolerates `4a`/`4b`.

Ordering rationale: the first four PRs build the parts that make everything else
auditable (money, memory, projection, execution). No model is called until spending it can
be priced and every claim it makes can be attributed. This is deliberate and is not
negotiable for schedule reasons. The root branch for this project is `feature/claude` and every PR must target this branch.

### Phase 0 — Skeleton and Constitution

**Deliverable:** a repository that can hold the project, and a machine-checkable statement
of what the project refuses to do.

- `AGENTS.md` (this file), `README.md`, `LICENSE`, `CONTRIBUTING.md`.
- Python 3.12 + `uv`; `ruff` + `mypy --strict`; `pytest`. No frameworks yet.
- `g0rd0n` CLI entry point with `version`, `doctor`, `config` subcommands and nothing else.
- `config/g0rd0n.toml`: paths to the knk storage root, the Obsidian vault, budget caps,
  the network allowlist.
- `docs/adr/0001-the-wager-is-the-primitive.md` — ADR format for every subsequent design
  decision, answering knk's four questions: what is the invariant, why this design, what
  are the failure modes, how is it tested.
- CI: lint, types, tests, plus `test_razor.py`.

**Minimum tests:**

- `every_module_declares_a_deletion_criterion` (the Razor, as a test over docstrings)
- `config_is_injected_never_read_from_env_inside_components`
- `doctor_reports_missing_kernel_and_vault_without_crashing`

**Review checklist:** does the repo do nothing yet, loudly and correctly?

### Phase 1 — The Ledger

**Deliverable:** `g0rd0n` can price and account for work it has not yet learned to do.

- `Cost` type: `tokens_in`, `tokens_out`, `usd`, `seconds`, `gpu_seconds`, `human_seconds`.
  Additive, immutable, serialisable.
- `Ledger` with three operations and no others: `reserve(wager_id, estimate) → Reservation`,
  `spend(reservation, actual)`, `settle(reservation) → Cost`. Over-spend against a
  reservation raises; it never silently succeeds.
- **Priced-before-run invariant** (the analogue of knk's durable-before-visible): a
  reservation exists before any priced call is made, never after.
- Three caps: per-session, per-campaign, standing. Exceeding a cap raises `BudgetExhausted`,
  which is caught at exactly one place and triggers clean settlement, not a crash.
- `--dry-run` prices a whole plan without executing any of it.
- `g0rd0n cost` report: by wager, by phase, by agent, by day.

**Minimum tests:**

- `no_priced_call_without_a_reservation`
- `overspend_against_a_reservation_raises`
- `budget_exhaustion_settles_cleanly_and_loses_no_records`
- `dry_run_produces_a_cost_estimate_and_makes_no_calls`
- `costs_attributed_to_a_wager_sum_to_the_session_total`

**Review checklist:** can a human answer "what did this cost and what did it buy" from one
command, before the system has ever done anything?

### Phase 2 — The Kernel Bridge

**Deliverable:** durable, provenance-carrying memory, via `knk`.

- MCP stdio client speaking to `knk`'s `mcp_server` as a subprocess. `g0rd0n` **never**
  links the C++ API, vendors the kernel, or forks it. If a needed operation is missing, the
  correct move is an issue against `knk`, not a workaround here.
- A **closed predicate vocabulary**, mirroring knk's closed command layer. Nothing outside
  this list is ever committed:

  ```
  asks          question    → statement
  refines       question    → question          (supersession chain of the Charter)
  hypothesises  question    → hypothesis
  predicts      hypothesis  → observation
  kills         hypothesis  → observation       (the falsifier)
  tests         experiment  → hypothesis
  measures      experiment  → result
  corroborates  result      → hypothesis
  refutes       result      → hypothesis
  costs         wager       → cost              (settled Cost, as a payload)
  cites         claim       → source
  plays         run         → playbook_version
  ```

- Every claim from an external channel is committed with `record_provenance` naming the
  source entity and the extraction method. Unsourced commits are rejected at the bridge.
- Machine-suggested claims use `commit_hypothesis`, never `commit`. Promotion to `Active`
  happens only through Phase 10's referee.
- `find_conflicts` is polled after every ingestion pass; conflicts are surfaced, never
  auto-resolved.

**Minimum tests:**

- `unsourced_claim_is_rejected_at_the_bridge`
- `predicate_outside_the_closed_vocabulary_is_rejected`
- `machine_suggested_claims_land_as_hypothesis_status`
- `conflicting_claims_are_surfaced_not_silently_reconciled`
- `bridge_survives_kernel_subprocess_restart`

### Phase 3 — The Vault

**Deliverable:** the Obsidian vault, as a **derived projection**.

The kernel is the source of truth. The vault is an index over it: human-readable,
link-navigable, and **rebuildable from scratch**. This mirrors knk's first architectural
principle exactly, and it exists to prevent the standard failure mode where prose and
ledger drift apart and nobody notices which one is lying.

- One-way projection: kernel → vault. Nothing is ever read back from the vault as fact.
- Note types, one folder each: `Questions/`, `Hypotheses/`, `Experiments/`, `Results/`,
  `Sources/`, `Playbooks/`, `Sessions/`.
- YAML frontmatter carries `assertion_id`, `status`, `confidence`, `provenance`,
  `superseded_by`. Wikilinks mirror the predicate edges, so the graph view *is* the
  argument structure.
- Hand-edits are permitted and are treated as human input: a `vault rebuild` overwrites
  them, and the projector warns before it does. Human prose that should survive gets
  committed to the kernel as a payload first.
- `g0rd0n vault rebuild` drops and regenerates the whole vault.

**Minimum tests:**

- `vault_rebuilds_deterministically_from_an_empty_directory`
- `rebuild_is_idempotent_byte_for_byte`
- `refuted_hypothesis_note_shows_its_refutation_and_is_never_deleted`
- `superseded_charter_remains_linked_from_its_successor`

### Phase 4 — The Cell Runtime

**Deliverable:** the ability to run an agent at all.

- A `Cell` is an agent with: a role, a system prompt from a versioned Playbook, a tool
  allowlist, a budget reservation, and a typed output schema. Nothing else. There is no
  agent base class hierarchy.
- Cell composition is a plain DAG of calls, described in data, not a framework.
- Every tool call passes through the Ledger and the network allowlist.
- Every transcript is stored via `intern_document` and linked with `plays` to the Playbook
  version used, so any run is reproducible and any result is attributable to a prompt.
- Human cells: a `HumanQuery` is a Cell whose instrument is a person. It has a price in
  wall-clock, a deadline, and a fallback if the deadline passes. Humans are resources in
  the network with the same accounting as models.

**Minimum tests:**

- `cell_cannot_call_a_tool_outside_its_allowlist`
- `cell_output_failing_its_schema_is_a_failed_run_not_a_parsed_guess`
- `transcript_is_interned_and_linked_to_its_playbook_version`
- `human_query_times_out_to_its_declared_fallback`

### Phase 5 — The Question Engine

**Deliverable:** `CHARTER.md`, the well-posed version of the task. This is the first phase
that does research rather than build plumbing.

- Reformulation loop: the current Charter is criticised, and each criticism is committed as
  a `refines` edge. The Charter is **superseded, never overwritten**; the old version stays
  linked and readable, so "why did we stop asking it that way" always has an answer.
- The Charter must fix: the separation shape (S1/S2/S3, or a defended fourth), the resource
  held fixed, the task families, the capability metric, the energy metric and instrument,
  and the matched-capability protocol.
- Formal definitions live in `docs/charter/definitions.md` with one worked example each. A
  definition that cannot be applied to a worked example is not yet a definition.
- The Turing trap section above is the first thing this engine is asked to attack.

**Minimum tests:**

- `charter_revision_supersedes_and_never_overwrites`
- `charter_without_a_named_fixed_resource_is_rejected`
- `every_definition_has_a_worked_example`

**Review checklist:** the human reviewer signs the Charter. This is a gate, not a
notification.

### Phase 6 — The Evidence Channel

**Deliverable:** grounded, attributed literature and data ingestion.

- Search and fetch against the allowlist; preference for primary sources (papers,
  proceedings, datasheets, benchmark repositories) over secondary summaries.
- Claim extraction commits `cites` edges. **A citation that cannot be resolved to a
  retrievable artifact is a hard failure**, not a low-confidence claim. Fabricated
  references are the single most damaging failure mode available to this system, and the
  gate against them is mechanical: resolve, fetch, hash, or discard.
- Deduplication against existing assertions; contradictions raised through `find_conflicts`
  and routed to the referee rather than averaged away.
- First job: verify or retract the seed numbers in "The Question" above.

**Minimum tests:**

- `unresolvable_citation_fails_the_ingestion_run`
- `duplicate_claim_from_a_second_source_raises_confidence_and_records_both_sources`
- `contradictory_claims_produce_a_conflict_record`
- `seed_claims_are_retracted_when_the_source_disagrees`

### Phase 7 — The Wager and the Allocator

**Deliverable:** the mechanism that decides what to spend next on.

- `Wager` type, the falsifiability gate as code, and pre-registration: claim, test,
  price, and kill-criterion are committed to the kernel **before** the experiment runs.
  Post-hoc criteria are the easiest way to fool yourself and are structurally impossible
  here.
- Allocation policy, default: **cheapest falsifier first.** Rank open Wagers by
  `P(verdict flips the leading candidate) × value(flip) / price`, and run the one that
  could kill the current leader for the least money. Popper as a budget function.
- Portfolio over candidate families with explicit priors and explicit kill criteria per
  family. A family that survives only because nobody has tried to kill it is flagged as
  such in the cockpit.
- Stopping rules: per-Wager price cap, per-family patience, and a "this question is
  exhausted" trigger that returns control to Phase 5.

**Minimum tests:**

- `wager_without_a_kill_criterion_is_rejected`
- `experiment_result_committed_before_preregistration_is_rejected`
- `allocator_prefers_the_cheaper_of_two_equally_informative_wagers`
- `exhausted_question_triggers_reformulation_not_more_spending`

### Phase 8 — The Bench

**Deliverable:** the empirical arbiter. Matched-capability, matched-joule evaluation.

This is the phase most likely to be over-built. Keep it small enough that one person can
verify it is not lying.

- Task suite drawn from the Charter's task families, with a transformer control arm that is
  honestly tuned. Baseline configs are versioned artifacts.
- Energy measurement with declared instruments and declared error bars: wall-power where
  available, RAPL / `nvidia-smi` where not, and analytic models for substrates that cannot
  be run here (neuromorphic, analog). **An analytic estimate is labelled as such in the
  result assertion and can never be compared directly against a measured number without
  the comparison being flagged.**
- Reporting: joules per correct answer, joules per bit of task-relevant information,
  capability at matched joules. Never raw accuracy alone.
- Every run commits `measures` with the full config hash, so a result nobody can reproduce
  is visibly a result nobody can reproduce.

**Minimum tests:**

- `measured_and_estimated_energy_are_never_compared_without_a_flag`
- `baseline_arm_runs_on_every_evaluation`
- `result_carries_its_config_hash_and_instrument`
- `energy_measurement_reports_an_error_bar`

### Phase 9 — The Formal Cell

**Deliverable:** the ability to make a separation claim precisely, and to know when one has
not been made.

- Claims are staged: `conjecture` → `proof sketch` → `machine-checked`. The status is part
  of the assertion, and the cockpit never displays a conjecture in the same visual weight
  as a theorem.
- Optional Lean/Coq integration for separation lemmas that reach the third stage. Optional,
  because a real proof here would be a major result and the system should be honest about
  how unlikely that is per-session; the value of the stage machinery is that it makes
  overclaiming visible.
- Complexity-class bookkeeping: every S1 claim records the class, the uniformity
  assumption, and the unproven separations it is contingent on (`TC⁰ ≠ NC¹` and friends).
  A claim contingent on an open problem is *labelled as contingent*, forever.

**Minimum tests:**

- `separation_claim_records_its_contingent_assumptions`
- `proof_sketch_is_never_reported_as_a_theorem`
- `machine_checked_status_requires_a_checker_artifact`

### Phase 10 — The Referee

**Deliverable:** the promotion gate. Nothing becomes believed without surviving an attack.

- An adversarial cell whose only job is to kill the leading candidate, budgeted separately
  so it cannot be starved by the thing it is attacking.
- Promotion `Hypothesis → Active` requires: a settled Wager, a survived falsification
  attempt, and a human sign-off. Three keys, and the human key is never automatable.
- Failed attacks are recorded too. "We tried to kill this and could not, here is how" is
  the actual evidence, and it is worth more than the promotion itself.

**Minimum tests:**

- `promotion_requires_all_three_keys`
- `failed_falsification_attempt_is_recorded_as_evidence`
- `referee_budget_is_isolated_from_the_candidate_it_attacks`

### Phase 11 — The Cockpit

**Deliverable:** the human's view. Full cost and epistemic transparency in one place.

- `g0rd0n status`: current question, open Wagers with prices, leading candidate, what would
  kill it, spend to date against caps.
- `g0rd0n why <assertion>`: walks `explain` and provenance to the root. Every belief is
  one command from its justification.
- `g0rd0n diff --since <t>`: uses `changes_since` to answer "what did we believe last week
  that we no longer believe, and what changed our mind."
- Session digest written to `Sessions/` in the vault: what was asked, what was spent, what
  was learned, what was killed.

**Minimum tests:**

- `why_walks_to_a_root_source_for_every_active_assertion`
- `status_reconciles_with_the_ledger_to_the_cent`
- `digest_lists_refutations_as_prominently_as_confirmations`

### Phase 12 — The Meta-Loop

**Deliverable:** self-improvement, PR-gated. The most dangerous phase; the most constrained.

- Playbooks (prompts, cell graphs, allocator policies, decomposition strategies) are
  versioned artifacts in the repo, not runtime state.
- `g0rd0n` proposes changes to them as **a git branch and a PR**, with the evidence: the
  replay suite of past sessions, the measured delta in verdicts-per-dollar, and the
  regression check on settled Wagers.
- **`g0rd0n` never merges its own PR.** This is the hard line of the project. Self-modifying
  research is fine; self-approving research is not.
- Replay suite: past sessions re-run against a new playbook, scored on cost to reach the
  same verdict. A playbook that reaches different verdicts on settled Wagers is a
  regression until proven otherwise.

**Minimum tests:**

- `proposed_playbook_change_arrives_as_a_pr_and_is_never_self_merged`
- `playbook_change_without_replay_evidence_is_rejected`
- `verdict_regression_on_a_settled_wager_blocks_the_proposal`

### Phase 13 — Campaign 001

**Deliverable:** the first real run, end to end, on the leading candidate from Phase 7.

Pre-registered, budgeted, refereed, and written up whatever the outcome. The success
criterion for this PR is **not** that a candidate wins. It is that the artifact produced is
one an external researcher could act on: a well-posed question, a pre-registered test, a
measured result with error bars, and a clear statement of what was ruled out.

A campaign that rules out three candidate families cheaply is a better outcome than one
that produces an unfalsifiable claim about a winner.

---

## Architectural Principles

### 1. The kernel is the source of truth

`knk`'s assertion log records what `g0rd0n` believes and why. The vault, caches, indexes,
and cockpit views are derived and rebuildable. Do not make the vault authoritative. Do not
let a claim exist in prose that does not exist as an assertion.

### 2. Append-only epistemics

Hypotheses are never edited. They are superseded or retracted. A refuted candidate stays in
the record with its refutation attached, because the history of how the programme changed
its mind is the most valuable thing this system produces.

### 3. Priced-before-run

A reservation exists before a call is made, never after. The analogue of
durable-before-visible. Correct order:

```
reservation = ledger.reserve(wager_id, estimate)
result = cell.run(...)
ledger.settle(reservation, actual)
```

### 4. The question is upstream

No hypothesis without a parent question. No experiment without a parent hypothesis. No
spend without a parent Wager. The chain from any dollar to a question is unbroken, and
`g0rd0n why` walks it.

### 5. Provenance or it didn't happen

Every claim from outside carries a resolvable source and an extraction method. No
exceptions for "well-known facts". The seed numbers in this file are held to this standard
too.

### 6. Keep layers separate

```
Cortex        question framing, allocation, meta-loop
Cells         agents and humans, with playbooks and schemas
Instruments   tools: search, fetch, bench, prover, sandbox
Kernel        knk, via MCP
Vault         Obsidian, derived projection
Ledger        cuts across all of them and is owned by none
```

The Cortex must not know about MCP framing. The Kernel bridge must not know what a Wager
is. Instruments must not commit assertions directly; they return results that a Cell
commits.

### 7. Failure is cheap, self-deception is not

Every mechanism here trades some efficiency for auditability. That trade is always taken.
A fast system that cannot show its work is worthless for this task.

---

## Recommended Repository Structure

```
g0rd0n/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── config/
│   └── g0rd0n.toml
├── src/g0rd0n/
│   ├── cli.py
│   ├── ledger/          # Cost, Reservation, caps, reports
│   ├── kernel/          # knk MCP client, closed predicate vocabulary
│   ├── vault/           # Obsidian projector
│   ├── cells/           # runtime, schemas, human queries
│   ├── cortex/          # question engine, wagers, allocator, meta-loop
│   ├── instruments/     # search, fetch, bench, prover, sandbox
│   └── cockpit/         # status, why, diff, digest
├── playbooks/           # versioned prompts, cell graphs, policies
├── bench/               # task suites, baseline configs, energy harness
├── docs/
│   ├── adr/
│   ├── charter/
│   └── benchmarks.md
└── tests/
```

Prefer short, explicit names: `Wager`, `Ledger`, `Cell`, `Charter`, `Referee`. Avoid
`Manager`, `Handler`, `Processor`, `Engine` where a real noun exists.

---

## Core Types

```python
QuestionId   = str   # kernel EntityId, rendered
WagerId      = str
RunId        = str
AssertionId  = int   # knk AssertionId

@dataclass(frozen=True)
class Cost:
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    seconds: float = 0.0
    gpu_seconds: float = 0.0
    human_seconds: float = 0.0

@dataclass(frozen=True)
class Wager:
    id: WagerId
    question: QuestionId
    claim: str            # the falsifiable statement
    test: str             # the procedure that settles it
    kill: str             # the observation that refutes it
    price: Cost           # the reservation estimate
    prior: float          # P(claim) before running
```

`Verdict` is a closed enum: `corroborated`, `refuted`, `inconclusive`, `abandoned`.
`abandoned` requires a reason and is a legitimate outcome; running out of money is not a
verdict about the world and must never be recorded as one.

---

## Budget Discipline

- Every session declares a budget before it starts. No budget, no session.
- Estimates are recorded alongside actuals so the estimator can be scored and improved.
  Systematic underestimation is a bug with a test.
- Rate limits, quotas, and network access are modelled as costs, not as errors to retry
  through. A retry storm is a spending decision made by nobody, which is exactly what this
  system exists to prevent.
- The allocator optimises **verdicts per dollar**, not tokens, calls, or notes written.
- `g0rd0n cost --by wager` must reconcile with the sum of all reservations. A discrepancy
  fails CI.
- A hard kill switch stops all cells, settles all open reservations, and leaves the kernel
  consistent. Tested, not assumed.

---

## Testing Requirements

Every semantic change has a test. Use `pytest` and temporary directories; never a fixed
path. The kernel under test is a throwaway storage root per test.

Beyond the per-phase lists, these invariants are permanent and are checked in CI:

```
no_priced_call_without_a_reservation
costs_attributed_to_a_wager_sum_to_the_session_total
unsourced_claim_is_rejected_at_the_bridge
machine_suggested_claims_land_as_hypothesis_status
wager_without_a_kill_criterion_is_rejected
experiment_result_committed_before_preregistration_is_rejected
vault_rebuilds_deterministically_from_an_empty_directory
refuted_hypothesis_is_never_edited_only_superseded
promotion_requires_all_three_keys
proposed_playbook_change_is_never_self_merged
every_module_declares_a_deletion_criterion
```

---

## Style

Python 3.12, `mypy --strict`, `ruff`. Prefer dataclasses and plain functions over classes
with behaviour. Prefer data over framework: a cell graph is a dict, not a subclass tree.

Prefer clear code over clever code, and clever design over elaborate design. These are not
in tension: cleverness belongs in what you choose not to build.

No LangChain-style abstraction layers. No agent framework. The runtime in Phase 4 is a few
hundred lines and should stay that way; if it grows, the growth is a design failure
somewhere upstream.

---

## Do Not Do Yet

Unless explicitly instructed, do not implement:

```
autonomous merging of any PR
unattended spend above a declared cap
network access outside the allowlist
training runs beyond the per-campaign GPU budget without human sign-off
publishing, emailing, or posting anything outside the repository and vault
a general agent framework
a query language over the kernel
a web UI
persistent long-running daemons
speculative optimisation of anything before the Bench exists
```

Two of these deserve their reasons stated, because they will be argued with:

- **Autonomous merging** stays forbidden permanently, not until some capability threshold.
  The value of this system is that a human can trust its record. A system that can approve
  its own changes to how it reasons cannot offer that.
- **A web UI** is forbidden until Phase 11 has been used in anger for a month. Interfaces
  built before the work is understood encode the wrong nouns, and they are expensive to
  un-encode.

---

## Agent Workflow

When making changes:

1. Read this file.
2. Identify the current phase. Do not jump ahead.
3. Keep the change small enough to review in one sitting.
4. Add or update tests.
5. Run lint, types, and tests.
6. Update the ADR if a design decision was made or reversed.
7. State the tradeoff you took and the thing you deliberately did not build.
8. Answer the Razor: could this be half the size?

A good PR is one where the reviewer finishes with fewer questions than they started with.

---

## Current North Star

`g0rd0n` should be able to answer, at any moment, in one command each:

```
What is the current question, and what was wrong with the last one?
Which wagers are open, what do they cost, and which is the cheapest falsifier?
Which candidate paradigm currently leads, on which metric, at matched capability?
What would kill the leader, has anyone tried, and what did the attempt cost?
What did we believe last week that we no longer believe, and what changed our mind?
Which claims rest on unverified seeds or open complexity-theoretic assumptions?
What did this session cost, and what did it buy?
```

The last question is the one that keeps the system honest.

`g0rd0n` is not searching for an answer. It is building the smallest machine that can tell
the difference between an answer and a story about one.
