# ADR 0003 — Entity references carry their kind, and the vocabulary fixes edge direction

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 2 (The Kernel Bridge)

## Context

AGENTS.md §Phase 2 gives the closed predicate vocabulary as a typed table:

```
refutes       result      → hypothesis
corroborates  result      → hypothesis
tests         experiment  → hypothesis
```

Rejecting a predicate outside the list is easy — a set membership test. Rejecting
`refutes(hypothesis, result)`, written backwards, is not: the kernel stores entities as
opaque interned strings, so nothing at the bridge knows that `h-001` is a hypothesis and
`r-002` is a result.

A backwards edge is the most dangerous mistake available here, because it typechecks, commits
cleanly, and reads plausibly in every view. `g0rd0n why` would walk it and produce an argument
that is precisely inverted. Recording a predicate's declared types and then not enforcing them
would be worse than not declaring them, because the table would look load-bearing.

## Decision

**An entity reference is a kind and a name, rendered `kind:name`**, and that rendered form is
what gets interned in the kernel: `hypothesis:h-001`, `source:arxiv-2401-00001`,
`experiment:bench-run-7`. The `Ref` type parses and renders it; the vocabulary table maps each
predicate to the sets of kinds its subject and object may have; `check` compares them.

### The invariant

*Every edge in the argument graph uses a predicate from the closed vocabulary, and runs in the
direction that predicate declares.*

The kind travels with the name, so the direction check needs no registry, no extra round trip,
and no state that could disagree with the kernel. It also makes knk's entity log readable on
its own: a human paging through interned names sees what each one is without resolving
anything.

`cites` is the one predicate whose subject is a supertype — AGENTS.md types it `claim →
source`, and a claim is anything assertable — so its subject set is the six claim-like kinds
rather than one.

## Why this design

- **Against a kind registry at the bridge:** state that can drift from the kernel, plus a
  lookup per commit. The naming convention is free and cannot disagree with itself.
- **Against a `has_kind` assertion in the kernel:** it would need a thirteenth predicate, and
  the vocabulary is closed. Spending the one-primitive budget on bookkeeping about the
  primitive is exactly the trade the Imperative says not to make.
- **Against checking predicates only, not directions:** leaves the table in AGENTS.md as
  decoration and leaves the backwards edge undetectable.
- **Against encoding kinds in a separate field on every call:** the caller would restate what
  the reference already implies, and could restate it wrongly.

The cost is a naming convention that the whole system must keep: an entity interned as a bare
`h-001` by some later phase would be invisible to the check. `Ref.__post_init__` rejects a
name containing `:` so the rendering stays unambiguous, and `Ref` is the only way to name an
entity through the bridge.

## Failure modes

- **A kind typo.** `Ref("wagerr", ...)` is rejected on construction against `KINDS`, which is
  derived from the vocabulary table rather than written out again.
- **A later phase interning a bare name.** Not currently preventable at the bridge, since
  `intern_document` returns an entity the kernel names itself. If Phase 3's projector or Phase
  6's ingester needs raw names, this ADR needs revisiting rather than quietly working around.
- **The vocabulary drifting.** A thirteenth predicate is a change to one table, which a
  reviewer sees, and `test_the_vocabulary_is_exactly_the_twelve_predicates_agents_md_names`
  fails until it is deliberate.

## When find_conflicts starts to matter

AGENTS.md originally required `find_conflicts` to be polled after every ingestion pass, with
`conflicting_claims_are_surfaced_not_silently_reconciled` as a minimum test. Verified against
a running `mcp_server`: **knk's `find_conflicts` considers `Active` assertions only.** Every
claim the bridge writes is a `Hypothesis`, because promotion needs Phase 10's three keys, so
`find_conflicts` returns nothing at this phase and will keep returning nothing until something
is promoted.

Two readings were possible: that knk should grow status-aware conflict detection — an issue
filed against knk, never a workaround here — or that the spec was ahead of itself.

**Resolved in favour of the second: knk's behaviour is correct, and AGENTS.md was changed.**
Two rival hypotheses are not a conflict; they are the ordinary state of an open question, and
the whole portfolio in §Candidate portfolio is built out of them. A conflict is two things
*believed* that cannot both be true, which first becomes possible at promotion. AGENTS.md
§Phase 2 now says what `find_conflicts` covers and why it is quiet, §Phase 6 records
disagreement as competing hypotheses with their sources, and §Phase 10 gains the rule this
implies: a promotion that would put an `Active` assertion into conflict with an existing one
is blocked and surfaced to the human key, never auto-resolved in either direction.

The bridge is unchanged by the decision: `conflicts()` is a faithful pass-through, and nothing
in g0rd0n reconciles anything. What it does mean is that the pass-through is finished rather
than provisional, and that the code Phase 10 will need is a caller for it, not a replacement.

What *is* tested here is the half of the invariant g0rd0n owns at this phase: two contradictory
claims about the same subject and predicate both persist, each keeping its own id, confidence,
and provenance, and both readable afterwards. Nothing is averaged, preferred for being newer,
or dropped. The test also asserts that `conflicts()` is currently empty, so the day the
kernel's behaviour changes, it says so rather than passing silently.

## Two smaller decisions

**The bridge has one write path.** `hypothesise` is the only way in, and there is no `commit`.
Machine-suggested claims land as `Hypothesis`; promotion to `Active` needs a settled Wager, a
survived falsification attempt, and a human key, none of which exist before Phase 10. A
`commit` method here would be a hole with a comment next to it, so there is no method to
comment on. `test_the_bridge_has_no_way_to_commit_an_active_assertion` pins that.

**Provenance is checked at the bridge as well as by the kernel.** knk's `commit_hypothesis`
requires a source entity, which is most of the rule, but it accepts an empty `method` string.
"Where did this come from" without "how was it got out of there" is not provenance, so the
bridge rejects an empty or whitespace method and a source reference that is not of kind
`source`, before anything is sent.

## How it is tested

Against a real `mcp_server` subprocess with a throwaway storage root per test — never a fake.
A bridge verified against a mock is a bridge verified against what its author believed knk
does, which is the specific self-deception this project exists to prevent. CI checks out and
builds knk from source (about ten seconds, cached) and passes the binary path explicitly, so a
kernel that failed to build fails the run rather than silently skipping the invariants.

Probing the running server also corrected two guesses this design started with:
`provenance_for` returns a single object rather than a list, and `get` answers a missing id
with a JSON `null` rather than an error — the latter is turned into a raised `ToolError`,
because a caller handed `None` will eventually forget to check for it.
