# ADR 0002 — The ledger journal is append-only, and every total is derived from it

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 1 (The Ledger)

## Context

Phase 1 has to price and account for work before the kernel exists to record it in. The
report it owes — "what did this cost and what did it buy", by wager, phase, agent, and day —
must be answerable across processes, so the ledger needs somewhere durable to write, and
Phase 2 is where durable memory arrives.

The obvious shortcut is to keep totals in memory and print them at the end of a session.
That fails the phase's own test list twice: `budget_exhaustion_settles_cleanly_and_loses_no_
records` has nothing to lose records *to*, and a cap can only be enforced against the current
process, which makes a standing cap meaningless.

## Decision

The ledger writes an append-only JSONL journal — one record per `reserve`, `spend`, and
`settle` — at the path in `config.ledger_journal`. **Every total is derived by replaying it.**
Nothing else is authoritative. The running totals the caps are checked against, the open
reservations `open_session` settles, and the `g0rd0n cost` report are all folds over the same
file, computed fresh.

### The invariant

*A total that exists is a total the journal already agrees with.*

Records are appended **before** in-memory state is updated (`Ledger._append` is called before
the accumulator moves), which is knk's durable-before-visible rule applied to money. A crash
between the write and the update loses nothing: the next replay recomputes the same total. A
crash between the update and the write is impossible, because that order never happens.

### Relationship to the kernel

The Ledger cuts across every layer and is owned by none (AGENTS.md, Keep layers separate), so
it does not depend on the kernel bridge. `ledger/` imports `config` and nothing else in
`g0rd0n`, and money is durable here before it is anywhere else.

AGENTS.md's vocabulary reserves `costs wager → cost` for settled costs. **It is not committed
yet, and this ADR used to claim it was.**

> *Corrected 2026-08-30.* The original text read: "From Phase 2, settled costs are also
> committed to the kernel as `costs wager → cost`." No such edge has ever been written. The
> only `hypothesise` call sites outside the bridge are `runtime`'s `plays` edge and
> `charter`'s `asks` and `refines` edges.

Two consequences are live today and should be read as known gaps rather than design:

- `wager_id` is a bare string in a JSON line, and nothing checks that it names a wager the
  kernel has heard of. The chain AGENTS.md §4 requires — every dollar back to a question —
  crosses a store boundary with no join, so `g0rd0n why` cannot yet walk it.
- The vault's `Wagers/` and `Costs/` folders are permanently empty, so "the graph view *is*
  the argument structure" holds for the argument and not for its price.

Phase 7 mints the `WagerId`s there would be to point at, and Phase 11's `why` is the first
caller that needs the join. When the edge is built it is a **projection** of this journal,
committed after the money is already durable here — the same relationship the vault has to
the kernel, one layer down, and never the reverse.

A disagreement between a total and the journal is always the total's fault.

## Why this design

- **Against an in-memory ledger:** see Context. Fails two of the five Phase 1 tests by
  construction.
- **Against SQLite:** it would work, and it would be the first dependency, the first schema,
  and the first migration. A `GROUP BY` over a few thousand JSON lines is not the bottleneck
  in a system whose unit of work is a model call. If the journal ever gets big enough to
  matter, an index over it is a derived artifact and can be added without changing what is
  true.
- **Against writing straight to the kernel and deferring the ledger to Phase 2:** it would
  invert the layering, and it would put Phase 1 behind Phase 2 for no reason other than
  avoiding one file format.
- **Against a mutable running-total file:** a total that can be rewritten is a total that can
  be wrong without anything noticing. The point of an append-only record is that the history
  of how the number changed is as available as the number.

## Failure modes

- **A damaged journal read as a shorter one.** Silently skipping a line that will not parse
  is how a ledger starts lying. `replay` raises `JournalError` naming the file and line, and
  the CLI turns it into a message rather than a traceback. The cost of this choice is that
  one corrupt byte stops all reporting until a human looks — which is the correct trade for
  a record whose only value is being trusted.
- **Unbounded growth.** Every reservation is kept forever, and replay is O(history). At the
  rate money is committed this is irrelevant for a long time; when it stops being irrelevant,
  the fix is a snapshot plus a tail, exactly as knk does it, and it changes nothing about
  what is true.
- **Reservations that are never settled.** Money the ledger believes is still promised to a
  claim nobody is working on, quietly shrinking every subsequent budget. `open_session`
  settles what is open in a `finally`, so it happens however the session ends — normally, on
  `BudgetExhausted`, or on any other exception.
- **Clock skew and local time.** A journal in local time lies twice a year. All timestamps
  are UTC, from one function.

## Two decisions inside this one

**Overspend is checked in every dimension, not just dollars.** A reservation is a promise
about all six — tokens, dollars, wall-clock, GPU-seconds, human attention — and an estimate
that was right about money and wrong about a person's time is still an estimate that was
wrong. AGENTS.md wants systematic underestimation to be a bug with a test, which requires
knowing *which way* it was wrong. Caps, by contrast, are stated in dollars, because that is
what the config declares and because dollars are the fungible dimension.

**Costs are floats, and cap comparisons carry a tolerance.** `Cost.usd` is a `float` because
AGENTS.md's Core Types say so. A total accumulated in a different order can land a few
machine-epsilons either side of a cap, so `_check_caps` compares with a `TOLERANCE_USD` of
1e-4 — a tenth of a cent, well below the precision anyone budgets in, and far above float
dust. Whether money should be `Decimal` is a real question and is **deferred**, not settled:
Phase 11 requires `status_reconciles_with_the_ledger_to_the_cent`, and if float accumulation
threatens that, this is the ADR that gets superseded.

## What deviates from AGENTS.md, and why

- **`reserve` takes an `agent`.** AGENTS.md gives the signature as `reserve(wager_id,
  estimate) → Reservation`, but the same phase requires a report grouped by agent, and
  attribution that is optional is attribution that will be missing when it matters. `phase`
  is carried by the session rather than the reservation, since a session runs in one phase
  while agents vary within it.
- **`spend(reservation, actual)` and `settle(reservation)`, per the Phase 1 text.**
  Architectural Principle 3 sketches `settle(reservation, actual)`. The two-operation
  reading loses the ability to record a cost mid-run, so the Phase 1 signatures win and the
  principle's snippet is read as shorthand.
- **`--dry-run` is wired but inert.** The mechanism is real and tested — a dry-run ledger
  prices a whole plan, enforces caps against the true history, and writes nothing — but no
  command spends yet, so the flag changes nothing today and its help text says so. A plan
  *file* was deliberately not invented: a list of prospective claims with prices is a list of
  Wagers, and inventing a second way to express one before Phase 7 defines the first would
  break the Imperative's one-primitive rule.

## How it is tested

`no_priced_call_without_a_reservation` and `costs_attributed_to_a_wager_sum_to_the_session_
total` are permanent CI invariants from here on. The first is structural: it pins the
`Ledger` surface to exactly three operations and asserts that `spend` and `settle` take a
`Reservation`, so a fourth operation or a `spend` that accepts a bare wager id breaks it on
the way in. The second is checked in every dimension, and against the journal rather than
against another total the report computed, so the two cannot agree by sharing a mistake.

Also permanent: the report must reconcile with the sum of all reservations under every
grouping (AGENTS.md, Budget Discipline: "a discrepancy fails CI").
