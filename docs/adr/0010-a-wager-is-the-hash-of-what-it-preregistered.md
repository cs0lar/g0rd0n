# ADR 0010 — A Wager is the hash of what it pre-registered

- **Status:** Accepted
- **Date:** 2026-08-31
- **Phase:** 7a (The Wager and pre-registration)

## Context

ADR 0001 fixed the Wager as the system's primitive and named its worst failure mode:

> **Post-hoc kill criteria.** The easiest way to fool yourself: run the experiment, then
> decide what would have counted as failure. Structurally prevented by pre-registration —
> claim, test, price and kill-criterion are committed to the kernel *before* the run
> (Phase 7).

"Structurally prevented" is the load-bearing word, and Phase 7 is where it has to be made
true. A pre-registration that a later step can amend is not a pre-registration; it is a
convention, and conventions are what this repository exists not to rely on.

Three things had to be decided to get there: what identifies a wager, how a wager attaches to
the argument graph given a closed predicate vocabulary that has no predicate for it, and where
the price is recorded.

## Decision

### 1. A wager's identity is the hash of its own substance

`Wager.id` is `f"{label}-{version}"`, where `version` is `version_of(substance)` — the same
twelve hex characters a `Playbook` and a `Charter` get, from the same function. The substance
is every field the wager pre-registers, rendered canonically in a fixed order: label,
question, hypothesis, claim, resource, task family, test, instrument, kill, price, prior.

**The invariant: there is no edit to a wager that keeps its id.** Soften the kill criterion
after seeing the result and you do not have an amended wager; you have a different wager, with
a different id, which the kernel has never heard of, which `register` will accept as new and
`record` will refuse to attach a result to on the strength of the old one's registration.
Post-hoc criteria are not forbidden, they are unrepresentable.

The label is inside the hash rather than beside it. It is what `g0rd0n cost --by wager`
prints, and a label that could be moved between wagers would make two of them
indistinguishable in the one report that has to reconcile with the money.

Free text is whitespace-normalised before hashing, for the same reason the Charter hashes
canonically ordered sections rather than file bytes: reflowing a paragraph is not a new wager,
and changing a word is.

### 2. A wager mints two entities under one name

The closed vocabulary (AGENTS.md §Phase 2) gives `wager` exactly one appearance: as the
subject of `costs`. It is never an object, and no predicate joins a wager to a question, a
hypothesis, or an experiment. So a wager registers as two entities sharing a name:

- `wager:<id>` — the priced face. `costs cost:<id>-price`.
- `experiment:<id>` — the argument face. `tests hypothesis:<h>`, and later
  `measures result:<id>-result`.

The shared name is the join, and it is a convention rather than an edge because the
alternative is a thirteenth predicate that would say only what both notes already say. The
vocabulary is closed; widening it to save a lookup is the trade AGENTS.md §Phase 2 exists to
refuse.

### 3. Registration commits the test, the kill, and the price — and not the actual cost

```
experiment:<id>  tests       hypothesis:<h>          the test
hypothesis:<h>   kills       observation:<id>-kill   the kill criterion
wager:<id>       costs       cost:<id>-price         the price
```

All three at confidence 1.0, which asserts what was *registered* — a fact about the
registration — and not a degree of belief in the hypothesis. What g0rd0n believes about the
world moves when a result arrives, and is only promoted by Phase 10's referee.

The **estimate** goes into the kernel because it is a commitment: you said in advance what
finding out would cost, and that is auditable. The **actual** does not, because the journal
already holds it and a second copy is a second thing to disagree with. ADR 0002 settled that
the journal is the record of money; this ADR does not reopen it. The kernel holds what you
said it would cost, the ledger holds what it did, and the wager id is the join.

### 4. No spend without a registration, and no re-pricing at the door

`cortex.wager.reserve(ledger, registration, agent)` takes a `Registration` — which only
`register` produces — and takes **no estimate**. The reservation is the price the wager
pre-registered.

The Ledger will price any string handed to it. It has to: it cuts across every layer and is
owned by none, so it cannot know what a Wager is. `reserve` is the one function where the
string becomes a claim somebody committed to first. This is the same enforcement shape as
`Ledger.spend` taking a `Reservation`, one layer up, and it is deliberate that it looks
identical.

Taking no estimate matters as much as taking the token. Re-pricing a wager at the moment you
run it is the post-hoc move wearing a different hat: a budget nobody committed to in advance
can always be found, afterwards, to have been exactly enough.

### 5. "No Wager without a parent Question" is checked against the kernel

`register` refuses a wager whose `question` does not actually `hypothesises` its
`hypothesis`, read from the kernel via `evidence.channel.rivals`. A `question` field is a
string until something resolves it, and a chain `g0rd0n why` cannot walk is not a chain.

## Failure modes

- **A token nobody minted.** A caller can construct a `Registration` by hand, exactly as they
  can a `Reservation`. `record` therefore also looks the assertion up and checks it is the
  pre-registration *of this wager* — not merely that some assertion exists. Both halves are
  needed: existence alone passes for any wager once any wager has been registered.
- **Registration after running, before recording.** Neither the token nor a kernel lookup can
  see when an experiment physically ran, so neither can rule this out today. Phase 8's Bench
  is where it closes: the run takes a `Registration`, so the token has to exist before the
  measurement does. Recorded here as a known gap rather than left to be discovered.
- **A null result laundered into support.** `inconclusive` and `abandoned` commit a `measures`
  edge and no edge from the result to the hypothesis. `ARGUES` maps them to `None` explicitly
  rather than by omission, so making an inconclusive run count as weak corroboration is a
  visible change to a table.
- **Budget exhaustion recorded as a verdict.** `Verdict` is a closed `StrEnum` of four, and
  `BudgetExhausted` is not one of them and is raised from a different module entirely. A
  wager stopped by the cap is `abandoned` with a reason, or it is nothing.
- **Wager inflation** — slicing work into many cheap wagers so each looks affordable. Not
  addressed here. It is the allocator's problem and is Phase 7b's: ranking by
  `P(flip) × value(flip) / price` puts a wager that cannot flip anything last however cheap
  it is.
- **A wager whose hypothesis nobody put under a question.** Refused, above. The cost is one
  round trip per registration, which is the cheapest check in the module.

## How it is tested

`tests/test_wager.py`, against a real `knk` and a throwaway storage root:

- `wager_without_a_kill_criterion_is_rejected` — the AGENTS.md minimum test, both halves of
  item 4: a wager that cannot lose, and one that costs nothing to find out.
- `experiment_result_committed_before_preregistration_is_rejected` — the other minimum test,
  with a forged `Registration`, checking that nothing reaches the kernel.
- `every_item_the_gate_demands_is_refused_when_missing` — `GATE` walked field by field, so a
  refusal names what is missing rather than that something is.
- `a_wager_is_identified_by_what_it_preregistered` and
  `every_field_a_wager_preregisters_is_inside_its_version` — a field outside the hash is a
  field that can be changed after registration, so the second test asserts `SUBSTANCE` covers
  every one and that changing each moves the version.
- `reflowing_the_prose_is_not_a_new_wager` — the other side of that.
- `a_wager_whose_question_does_not_ask_it_is_refused`, `a_wager_is_registered_once`,
  `a_wager_gets_one_verdict`, `an_abandoned_wager_must_say_why`,
  `a_verdict_that_settles_nothing_argues_nothing`,
  `a_registration_naming_another_wagers_preregistration_is_rejected`.
- `no_spend_against_an_unregistered_wager` — structural, over `reserve`'s signature, so an
  `estimate` parameter appearing later breaks a test rather than a habit.

Each of these was verified by breaking the invariant it guards and watching it fail.

## What this ADR does not decide

How wagers are ranked, what a portfolio of candidate families looks like, when a question is
exhausted, or how patience per family is spent — all Phase 7b. Nor what produces a verdict:
the Bench is Phase 8, and until it exists `record` is called by hand.
