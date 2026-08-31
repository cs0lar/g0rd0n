# ADR 0011 — A deletion criterion resolves against the test suite, not the kernel

- **Status:** Accepted
- **Date:** 2026-08-31
- **Phase:** 7a (The Wager and pre-registration)
- **Supersedes:** the Phase 7 commitment in ADR 0001 §"Consequence for Phase 0"

## Context

ADR 0001 recorded a dated compromise and named the phase it came due in:

> Phase 0 has no Wagers — the type arrives in Phase 7 — so the requirement is applied in the
> only form available now: **prose naming the invariant the module protects, and what stops
> being checkable without it.** [...] Phase 7 tightens this to a resolvable `WagerId`, at
> which point the length floor is replaced by a lookup against the kernel. Recorded here so
> that the weaker Phase 0 form is a known, dated compromise rather than the standard quietly
> having been lowered.

Phase 7 is here. The `WagerId` exists. The promise is due, and paying it as written turns out
to be the wrong thing to do — so this ADR pays a different one and says why, rather than
letting the deadline pass in silence, which is the failure ADR 0001 was written to prevent.

## Decision

**A deletion criterion must name at least one test that exists in the suite.** The check is
still `tests/test_razor.py::test_every_module_declares_a_deletion_criterion`; it still parses
source and needs no kernel; the forty-character floor is gone, replaced by resolution of a
backticked identifier against the set of test function names under `tests/`.

Three things follow, and all three were done in this phase's diff:

1. Seven modules whose criteria named no test now name one. Six of them said some version of
   "every Phase 4 minimum test loses its verdict" — which clears forty characters
   comfortably and points at nothing. That phrasing is exactly the lazy gesture ADR 0001
   worried the length floor would not catch, and it was in the repository the whole time.
2. A criterion may name a test with or without its `test_` prefix, and may wrap across two
   lines of a docstring; the check folds the wrap. Criteria read as sentences, and
   `` `x` loses its verdict`` reads better than `` `test_x` ``.
3. Nothing about the Wager changed to accommodate this. `WagerId`s are not mentioned in
   docstrings and no module registers a wager about itself.

## Why not a `WagerId` and a kernel lookup

Three reasons, in increasing order of how much they settle it.

**A module is not a claim about the world.** A Wager is `claim + test + price + kill-criterion
→ verdict`, and the gate demands the resource held fixed, the task family, the instrument, and
the observation that would refute it. "Delete `cost.py` and every dimension but dollars goes
unchecked" has none of those and cannot be given them honestly: there is no measurement, no
instrument, no price, and no observation about the world that would refute it. Manufacturing
one per module would put twenty unfalsifiable claims into the kernel to satisfy a docstring
rule.

**It would corrupt the allocator's input.** Phase 7b ranks open Wagers and Phase 12 learns
from settled ones. Twenty wagers about g0rd0n's own source layout — none of them ever
settleable, none of them ever worth spending on — would sit in that portfolio forever, and
every "which wagers are open" question would have to filter them out. ADR 0001's own list of
failure modes includes wager inflation; this would be wager inflation as a policy.

**It would make the Razor skippable.** `tests/test_razor.py` says why it exists where it does:

> They are here rather than in `test_bridge.py` on purpose. The kernel tests need a built
> `knk` and skip without one, and an invariant that can be skipped is an invariant that will
> be. These parse source and need nothing.

A lookup against the kernel needs a built `knk`, so the Razor would begin skipping on any
machine without one — including, on a bad day, CI. Trading an unskippable weak check for a
skippable strong one is not a tightening. This reason alone is decisive; the other two are
why it is not even a close call.

## What is actually gained

The identifier resolves, which is what ADR 0001 wanted. The difference is what it resolves
*to*: a test rather than a wager, because the thing a deletion criterion is really claiming is
epistemic — "this is what stops being checkable" — and in this repository what is checkable is
what a test checks. AGENTS.md, The Imperative (2) asks that no settled Wager be lost by a
deletion; the tests are where settled questions about g0rd0n's own behaviour live.

## Failure modes

- **Naming a test that exists but is unrelated.** Not caught. The check resolves the
  identifier; it cannot judge relevance. A reviewer can, and the criterion sits in a diff.
- **A test renamed elsewhere.** Breaks the Razor, in the module whose criterion named it.
  That is the intended behaviour and the main ongoing cost of this decision: renaming a test
  now means grepping for its name in docstrings. It is a small cost and it is the price of the
  identifier resolving at all.
- **Criteria drifting back to gestures.** A module could name one real test and then say
  nothing else useful. The floor is now "at least one resolvable name" rather than "at least
  forty characters", so the cheapest way to pass is to name something true.
- **`g0rd0n why` walking a deletion criterion.** It will not, and is not meant to. Phase 11's
  walk is over the kernel's argument graph; docstrings are not in it.

## How it is tested

`test_every_module_declares_a_deletion_criterion`, tightened. Verified by replacing one
module's named tests with the prose it used to carry ("every Phase 1 minimum test", "the whole
ledger") and watching the Razor fail — the same edit that passed under the length floor.

## What this ADR does not decide

Whether package `__init__` docstrings should be checked against a *layering* test rather than
a behavioural one. Two modules currently reach past a package boundary that a sibling
`__init__` docstring claims is sealed (`cells/runtime.py` imports `g0rd0n.ledger.ledger`;
`evidence/channel.py` imports `g0rd0n.kernel.vocabulary`). Neither is a bug today — both
import names their package exports or could export — but a razor test over sealed module
boundaries would find them, and there is currently no such test. Left for whichever phase
wants it, and written down here so it is not rediscovered.
