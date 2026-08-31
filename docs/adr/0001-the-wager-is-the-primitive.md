# ADR 0001 — The Wager is the primitive

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 0 (Skeleton and Constitution)

Every subsequent ADR answers the same four questions this one does: what is the invariant,
why this design, what are the failure modes, how is it tested.

## Context

`g0rd0n` has to do three things that are normally three systems:

1. keep a research programme honest — claims, refutations, provenance;
2. keep a budget — what was spent, on what, against which cap;
3. improve how it works — which approach produced results per dollar.

Built separately, these drift. The ledger says a session cost $40; the notes say the session
was productive; nothing connects the two, and no one can say what the $40 bought. That
drift is not a reporting inconvenience, it is the specific way research programmes fool
themselves about their own progress.

## Decision

One primitive:

```
claim  +  test  +  price  +  kill-criterion  →  verdict
```

A **Wager** is a falsifiable claim with money attached and a stated way to lose. No token is
spent except in service of settling a Wager, and no Wager is opened without a parent
Question.

### The invariant

*Every unit of spend is attributable to exactly one Wager, and every Wager states in advance
the observation that would refute it.*

Everything downstream follows mechanically:

- A claim with no kill-criterion is not a hypothesis, so `g0rd0n` refuses to open a Wager on
  it. The falsifiability gate is code, not a norm.
- A Wager's price is reserved before work starts, so "what did this session buy?" is a
  `GROUP BY` rather than an interview.
- A settled Wager is a labelled training example for the allocator — *this playbook, at this
  price, produced this verdict* — so meta-learning is statistics over settled Wagers rather
  than a separate subsystem.

## Why this design

The alternatives, and why each loses:

- **Task or plan as the primitive.** A task can be completed. Completion is not evidence.
  This is the failure mode where a system reports a productive day and cannot name one thing
  it now believes that it did not believe yesterday.
- **Agent as the primitive.** Leads to an agent framework, a base-class hierarchy, and
  spend attributed to a component rather than to a claim. `AGENTS.md` forbids the framework
  for exactly this reason.
- **Hypothesis as the primitive, with a separate budget system.** This is the drift case
  above, one level down: two ledgers that agree only by convention.
- **Experiment as the primitive.** Excludes the cheapest and most valuable moves — reading a
  paper, asking a person, retracting a seed number — which settle claims without an
  experiment.

The Wager is the smallest object that carries a claim, its price, and its refutation
condition at once, which is the only combination that makes all three questions answerable
from one record.

## Failure modes

- **Post-hoc kill criteria.** The easiest way to fool yourself: run the experiment, then
  decide what would have counted as failure. Structurally prevented by pre-registration —
  claim, test, price and kill-criterion are committed to the kernel *before* the run
  (Phase 7).
- **Running out of money recorded as a verdict.** Budget exhaustion says nothing about the
  world. `Verdict` is a closed enum and `abandoned` requires a reason; exhaustion settles
  cleanly and is never recorded as `refuted` or `inconclusive`.
- **Wager inflation.** Slicing work into many small Wagers to make each look cheap. The
  allocator ranks by `P(flip) × value(flip) / price`, so a Wager that cannot flip anything
  ranks last however cheap it is.
- **The deletion criterion degenerating into boilerplate.** See below.
- **Prose that outruns the record.** A claim in a vault note or a PR description that has no
  assertion behind it. The vault is a derived projection and is never read back as fact
  (Phase 3).

## Consequence for Phase 0: the deletion criterion

`AGENTS.md` requires every module to state, in its docstring, the settled Wager that would
lose its verdict if the module were deleted. Phase 0 has no Wagers — the type arrives in
Phase 7 — so the requirement is applied in the only form available now: **prose naming the
invariant the module protects, and what stops being checkable without it.**

`tests/test_razor.py::test_every_module_declares_a_deletion_criterion` checks that a
`Deletion criterion:` marker is present and says something (a length floor, which catches
the empty gesture but not a lazy one). Phase 7 tightens this to a resolvable `WagerId`, at
which point the length floor is replaced by a lookup against the kernel. Recorded here so
that the weaker Phase 0 form is a known, dated compromise rather than the standard quietly
having been lowered.

> **Amended 2026-08-31, Phase 7a.** The tightening happened; the identifier is not a
> `WagerId`. The criterion must now name at least one test that **exists in the suite**, and
> the length floor is gone. Resolving against the kernel instead would have required a wager
> per module — unfalsifiable claims, permanently open in the allocator's portfolio — and
> would have made the Razor skip on any machine without a built `knk`, which is the one
> property `tests/test_razor.py` exists to have. See
> [ADR 0011](0011-a-deletion-criterion-resolves-against-the-test-suite.md). Seven modules
> were found to be naming no test at all under the old floor, all of them clearing forty
> characters.

## How it is tested

Phase 0 can only test the parts of the invariant that exist yet:

- `every_module_declares_a_deletion_criterion` — the Razor over docstrings.
- `config_is_injected_never_read_from_env_inside_components` — no ambient configuration, so
  two runs that look the same in the record were the same.
- `doctor_reports_missing_kernel_and_vault_without_crashing` — the system refuses to start
  before it half-starts.

The invariant's real tests arrive with the machinery they describe, and are permanent from
then on (`AGENTS.md`, Testing Requirements): `no_priced_call_without_a_reservation`,
`costs_attributed_to_a_wager_sum_to_the_session_total`,
`wager_without_a_kill_criterion_is_rejected`,
`experiment_result_committed_before_preregistration_is_rejected`.

## What this ADR does not decide

How a Wager is scored, priced, or allocated over (Phase 7); what a verdict costs to reach;
and whether the Charter's separation shape is S1, S2, or S3 (Phase 5). This ADR fixes only
that the Wager is the unit those decisions are made in.
