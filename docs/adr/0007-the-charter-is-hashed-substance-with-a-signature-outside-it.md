# ADR 0007 — The Charter is hashed substance, and the signature sits outside it

- **Status:** Accepted
- **Date:** 2026-08-30
- **Phase:** 5 (The Question Engine)

## Context

AGENTS.md §Phase 5 asks for `CHARTER.md`, "the well-posed version of the task", with four
properties: it fixes six named things; it is **superseded, never overwritten**, with each
criticism committed as a `refines` edge; its formal definitions live in
`docs/charter/definitions.md` with one worked example each; and a human reviewer signs it —
"a gate, not a notification".

Three of those four are in tension with the obvious implementation. A markdown file is
edited in place, which is overwriting. A signature is added to the file, which changes the
file, which changes any identity derived from it. And a definitions file that lives beside
the Charter can be changed underneath it without the Charter's identity moving at all.

The seed framing in AGENTS.md §The Question is the thing being replaced. It is not a
well-posed question: it asks for a paradigm "provably more powerful than transformers", which
two Turing-complete systems cannot be separated on; it names three separation shapes and picks
none; and its energy metric names no instrument. That is what this Charter's criticisms say,
and they are the first six `refines` edges in the record.

## Decision

### A charter's identity is the hash of its substance, exactly as a playbook's is

`version_of` is reused from `cells.playbook`, unchanged. A charter cannot be edited, because
an edit produces a different charter with a different name. `question:charter-329c9f00e917` is
the entity, and the previous one keeps its own.

The hash covers a **canonical rendering** — every section, in a fixed order, normalised — not
the file's bytes. Reordering a document is not a new question and must not be a new version,
and the canonical form is also what lets the signature sit outside the hash without the two
disagreeing about what "the charter" is.

### Sections are a closed vocabulary, and no prose sits outside them

Eight required sections for the eight things the Charter must fix, plus `Definitions`, and
optionally `Supersedes`, `Criticisms`, and `Signed-off-by`. An undeclared section is rejected,
a required one that is absent or empty is rejected naming it, and prose above the first
heading is rejected too.

AGENTS.md lists six things to fix, one of them compound ("the energy metric and instrument").
It is checked as two. A metric with no named instrument is exactly the failure this document
exists to prevent: joules per solved instance is a number until something measures it, and
then it is a result.

### The signature is outside the hash and names the hash

A document cannot contain the hash of itself-including-the-signature, so the signature is the
one section the version does not cover. That would leave a hole — edit the body after signing
and somebody's name stays attached to text they never read — so the signature carries the
version it signed:

```
## Signed-off-by

A Reviewer <handle>, 2026-08-30, charter-329c9f00e917
```

A signature naming a different version is a hard error, not a charter treated as unsigned.
Silently downgrading would lose the fact that someone signed something.

**`commit` refuses an unsigned charter.** That is the gate. An unsigned charter can be read,
printed, reviewed and argued with; it never becomes the question a Wager descends from.

### No supersession without a criticism, one `refines` edge each

`Supersedes` and `Criticisms` travel together in both directions: a supersession with no
criticism is rejected, and a criticism with nothing to point at is rejected. Each criticism
becomes its own `refines` edge from the new question to the old, carrying its text in the
provenance method. The charter's own bytes are interned once and cited from every edge.

This is the same discipline as "no Wager without a kill-criterion", applied one level up:
there is no way to stop asking the question a given way without writing down why first.

### The Charter names its definitions file by version

`## Definitions` holds the hash of `docs/charter/definitions.md`, and it is inside the
substance. Editing a definition therefore changes the Charter's version and costs it a fresh
signature. A question whose terms can be redefined underneath it is a question that can be
changed without being superseded, which is the one thing this module exists to prevent.

Definitions themselves are **not** committed to the kernel. They fix what the Charter's words
mean; they are not claims about the world, carry no confidence, and nothing can refute them.
Putting non-claims into an assertion store would make "what does g0rd0n believe" a question
with a footnote.

## Why this design

**Hashing rather than a version field** removes a failure no test could catch. An edited
document with a stale version number attributes a question to text that never posed it, and
the record would be internally consistent and wrong.

**Capability at a fixed energy budget (S4) rather than the seed's S3.** This is a decision the
Charter makes rather than the code, but it is the reason the phase produced a document at all.
S3 — joules at matched capability — requires the candidate to first reach the control arm's
capability, and every candidate in the portfolio is behind, so a charter built on S3 can never
take its first measurement. Fixing the joules and measuring the capability is measurable on
day one, and sweeping the budget recovers the S3 number exactly. Nothing is lost by the swap.

**The Turing trap closes when you charge for the tape.** Two Turing-complete systems cannot be
separated on what they compute; they separate on what they compute inside a fixed energy
budget, because a serial step of chain-of-thought costs joules. That is one sentence, and it
is the whole reformulation.

**No critic cell in this phase.** The obvious move is a Cell that criticises the Charter and
produces the criticisms automatically. It is deliberately not built: the criticisms that
retire the project's founding question are the thing a human must own, Phase 10's referee is
already the adversarial cell and is budgeted separately, and a second one here would be the
second way to express something — the Imperative's first rule.

## Failure modes

- **A typo'd `Supersedes` forks the chain silently.** The target is not checked for existence,
  because the first charter supersedes the seed framing, which is a question the kernel has
  never seen. Accepted: the target is printed by `charter show` and is visible in the vault as
  a `superseded_by` link, and the criticisms — which are checked — are the part that makes the
  supersession readable.
- **A criticism is a single line.** Continuation lines fold in, but the text lands in a
  provenance method, so a criticism that wants to be an essay is being written in the wrong
  place. The Charter's prose sections are where an argument goes.
- **The definitions hash makes typo fixes expensive.** Correcting a comma in `definitions.md`
  supersedes the Charter. This is the same discipline a playbook already has, taken
  deliberately: a cheap edit path is how a document stops meaning what it said.
- **Nothing checks that the Charter's terms and the definitions' terms are the same set.** A
  definition nobody uses, or a term nobody defines, both pass. Doing better would need a
  parser over English rather than over markdown.

## How it is tested

`tests/test_charter.py`, against a real `knk` with a throwaway storage root for the ones that
commit:

- `charter_without_a_named_fixed_resource_is_rejected` — absent and empty, and the same loop
  over all eight elements from the same table validation reads.
- `charter_revision_supersedes_and_never_overwrites` — the first charter's assertions have the
  same ids after the second is committed, and the second's `refines` edges carry one criticism
  each.
- `every_definition_has_a_worked_example` — over the file this repository ships, so the rule
  cannot pass on synthetic input while the real document stops obeying it.
- `an_unsigned_charter_is_never_committed`, `a_charter_is_never_committed_twice`,
  `the_signature_names_the_version_it_signed`,
  `editing_a_definition_supersedes_the_charter_rather_than_amending_it`,
  `the_version_does_not_depend_on_the_order_of_the_sections`.

Each of those was verified by breaking the thing it checks and watching it fail.
