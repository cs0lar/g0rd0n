# ADR 0016 — A proof stage is an edge, and a contingency is part of the claim

- **Status:** Accepted
- **Date:** 2026-09-18
- **Phase:** 9 (The Formal Cell)

## Context

AGENTS.md §Phase 9's deliverable is "the ability to make a separation claim precisely, and to
know when one has not been made." Three requirements:

- Claims are staged `conjecture` → `proof sketch` → `machine-checked`, "the status is part of
  the assertion", and nothing displays a conjecture with the weight of a theorem.
- Optional Lean/Coq integration for claims that reach the third stage — optional "because a
  real proof here would be a major result", and the value of the stages "is that it makes
  overclaiming visible".
- Every S1 claim records the class, the uniformity assumption, and the unproven separations it
  is contingent on, and "a claim contingent on an open problem is *labelled as contingent*,
  forever".

`CHARTER.md` §Separation shape sets the scale. The Charter chose S4 over S1 because an S1
separation that bites here is contingent on an open problem, and a question that can only be
settled by resolving one is a question this instrument cannot spend against. S1 results are
admitted "as evidence … with its contingent assumptions attached, permanently". So this phase
is a recording discipline, not a research programme, and its size should match.

The hard constraint is the kernel. The closed vocabulary has twelve predicates and none of
them means "is at proof stage X" or "depends on". AGENTS.md §Phase 2 says nothing outside that
list is ever committed, and knk's own status field is epistemic — `Hypothesis` or `Active` —
and belongs to Phase 10's referee.

## Decision

### 1. The stage is carried by *which edge exists*, not by a field

Proof stage and belief are orthogonal. A machine-checked proof of the wrong formal statement is
still a `Hypothesis`; a promoted claim could in principle have no proof at all. So the stage
cannot be knk's status, and it cannot be a new predicate. It is carried by the edge that
*is* each stage, through the vocabulary as it stands:

| Stage | Edge | Provenance source |
|---|---|---|
| conjecture | `question hypothesises hypothesis:<id>` | `source:<id>`, the claim document |
| proof sketch | `hypothesis:<id> cites source:<id>-sketch-<v>` | the sketch document |
| machine-checked | `result:<id>-checked-<v> corroborates hypothesis:<id>` | the checker's artifact |

Every edge's provenance method is headed by the stage it is. `stage_of` reads the stage back
from the kernel alone — the highest stage with a live edge, provided the conjecture itself is
live — so the stage is a fact about the record rather than a value somebody set.

Two consequences come free. **Stepping back needs no special case**: retracting the sketch's
`cites` edge returns the claim to a conjecture, and both edges stay in the record. And **the
vault shows the stage without knowing what one is**: it prints provenance beside every edge,
so the claim's note reads "proof sketch (not machine-checked)" on the line where the sketch
appears. `note.py` is unchanged.

The shared-name join between a claim and its sketch and result entities is a convention, as
`wager:<id>` / `experiment:<id>` is in ADR 0010, and for the same reason: widening the
vocabulary to say something the names already say would be a poor trade.

### 2. A contingency is inside the claim's identity

A `Separation`'s id is `f"{label}-{version}"` where the version hashes the family, the
statement, the classes, the uniformity, what is pinned, what it is contingent on, and the
prior — exactly as a `Wager`'s does. There is no edit that drops a contingency and keeps the
id, and no stage transition that clears one. The only way to stop being contingent is to be a
different claim; the old one stays, labelled.

Every edge the module commits repeats `label_of_contingency` in its provenance, so a reader who
meets the claim from any direction — its conjecture, its sketch, its checked result — meets
"CONTINGENT on …" on the same line. That is what "forever" is.

### 3. Open problems are a closed table

`OPEN` names each open separation a claim may depend on, by the identifier a formal proof would
give the axiom assuming it. Closed for the same reason the predicate vocabulary is: two claims
contingent on one problem must say so in one spelling, or "which of our results fall if this is
settled?" has no answer. Adding a row is admitting a new dependency, in a diff.

### 4. Stages are reached in order, and a sketch pins the formal statement

A claim cannot jump from conjecture to machine-checked. The sketch is where the *formal
statement* — what a checker would have to prove — is written down next to the prose argument,
in front of a human reader. The correspondence between a prose claim and a formal statement is
the one thing no checker can check, so it has to be pinned somewhere it can be argued with,
before any proof is presented.

`checked` then requires the checker to have proved **exactly** that statement (whitespace
aside), against the sketch the kernel actually holds. A proof of a theorem with the same name
and a friendlier type does not advance the claim.

### 5. What a checker is trusted for is its axiom report

A proof assistant will check a proof that assumes what it set out to prove, if the assumption
is an axiom, and a proof with a hole in it, if the hole is spelled `sorry`. Both compile. So a
`Checked` artifact carries the complete axiom list, and `prover.unadmitted` sorts it:

- the checker's foundational axioms (`TRUSTED`) — Lean 4's `propext`, `Classical.choice`,
  `Quot.sound` — which say nothing about the claim;
- a hole (`HOLES` — `sorryAx`), which is **refused outright**, not reported as "contingent on
  sorry";
- everything else, which is an assumption the proof made and must already be one of the
  claim's declared contingencies.

That third pile is where the bookkeeping stops being a label and becomes a check. A claim
declared unconditional whose proof assumes `nc1_not_in_l_uniform_tc0` is refused, because it
is a stronger claim than what was proved. `Lean.ofReduceBool` — `native_decide`'s trust in the
compiler — is deliberately not foundational and has to be declared like any other assumption.

A checker absent from the tables is refused rather than trusted: its foundations could not be
told apart from what its proofs assume.

### 6. "Theorem" is said exactly once

`describe` is the only wording there is. Machine-checked and unconditional is a "theorem";
machine-checked and contingent is a "conditional result — holds only if …; not a separation
until they are settled"; a sketch is "an argument, not machine-checked"; a conjecture has "no
proof held". The checked edge's provenance names the Lean *declaration* rather than calling it
a theorem, so a conditional result never reads as one in the vault either. Every rendering
ends by saying a stage is not belief and promotion is Phase 10's.

### 7. No checker is shipped

There is no Lean and no Coq on the machine this was written on. A runner for a tool nobody can
run it against is the speculative driver Phase 8b declined to write for a wall-plug meter, and
for the same reason. `Checker` is the seam; `Checked` is what arrives through it. The third
stage is therefore reachable only from a test today, which is the honest state: a system that
could reach `machine-checked` without a checker would be the overclaim this phase exists to
catch.

### 8. The shipped claim is a conjecture, contingent on the stronger assumption

`T1_WITHOUT_CHAIN_OF_THOUGHT` is the worked example: no family of fixed-depth, log-precision,
single-pass transformers computes T1 at every size. Two decisions in it are the point.

**It is contingent on `nc1_not_in_l_uniform_tc0`, not `tc0_ne_nc1`.** The transformer bound in
the kernel is *logspace*-uniform — the seed audit's correction to AGENTS.md's unqualified
"uniform" (docs/seed-audit.md) — so the separation the argument needs is from logspace-uniform
TC⁰. That implies `TC⁰ ≠ NC¹` and is not known to follow from it. Writing the familiar one
would understate what the claim assumes, which is precisely what the uniformity field exists
to surface.

**It is a conjecture**, although the literature treats the conditional as known. The stage is
about what g0rd0n holds. The upper bound is in the kernel at 0.95; the NC¹-completeness of the
S₅ word problem (Barrington, 1989) is not in the kernel at all, and a sketch resting on a
premise the record does not hold would be the Evidence Channel's rule broken one layer up. The
sketch waits for that premise.

## Failure modes

- **The Lean axiom names are from documentation and have never been run here.** `propext`,
  `Classical.choice`, `Quot.sound` and `sorryAx` are Lean 4's as I know them, and `#print
  axioms` is how a runner would get the list. If any is wrong, the error is conservative in
  both tables: an unrecognised foundation is refused as an undeclared assumption, and so is an
  unrecognised hole, because a claim can only declare names from `OPEN` — though the hole would
  be refused with the wrong explanation. What would *not* be conservative is a name wrongly
  listed in `TRUSTED`. The first real runner should test both tables against real output
  before anything else.
- **Axiom names are matched to contingencies by spelling.** A proof that assumes
  `nc1_not_in_l_uniform_tc0` is taken to assume the open problem `OPEN` describes by that name.
  Nothing checks that the axiom's *statement* says what the table's prose says. That is a
  formalisation-correspondence question, the same one the sketch pins for the claim itself,
  and it is a referee's to ask.
- **Statement matching is textual.** Two formal statements that are definitionally equal but
  spelled differently do not match, and a proof of one does not advance a sketch of the other.
  Conservative, and occasionally annoying.
- **The prose-to-formal correspondence is unchecked by construction.** A sketch can pin a
  formal statement that does not mean the claim. The sketch is where that is visible, and
  Phase 10 is where it is attacked.
- **A declared contingency the proof did not use is allowed.** The claim is then weaker than
  what was proved. That is an underclaim rather than an overclaim, and it is recorded in the
  checked edge's provenance ("declared but not used") rather than refused; an unconditional
  claim is a different registration.
- **One sketch and one check per claim.** A better argument arrives by retracting the old one,
  which keeps both in the record. Two live sketches of one claim are not supported.
- **`stage_of` reads the whole log**, as `allocator.read` does, because two of the three edges
  point *at* the claim and knk answers by subject. Fine at today's size.

## What this does not decide

- **No Formal Cell agent.** AGENTS.md calls the phase a "Cell", and nothing here calls a model.
  A cell that drafts sketches or proofs is a spend against a wager like any other and can be
  built on this machinery when a wager wants one; the deliverable — make a claim precisely,
  know when one has not been made — needs the stages and the bookkeeping, not an author.
- **No sketch of the shipped claim.** It waits for Barrington's theorem to enter the kernel
  through the Evidence Channel.
- **Coq.** The tables are Lean 4's only. A second checker is a row in each table and a runner.
- **The cockpit's visual weight.** Phase 11 builds `status`; what it needs — the stage, and
  the contingency on every edge — is in the kernel now.

## How it is tested

`tests/test_formal.py`, thirteen tests, plus two in `tests/test_cli.py` (one refusing before a
kernel, one end to end through `charter commit`, `formal seed` twice and `formal status`
against a real `knk`). The checker is a stand-in that hands back whatever artifact a test
chooses, so these tests check what g0rd0n does *with* a checker's report and nothing about
whether Lean would produce it.

Phase 9's three minimum tests: `separation_claim_records_its_contingent_assumptions`,
`proof_sketch_is_never_reported_as_a_theorem` (exhaustive over every stage and both kinds of
claim) and `machine_checked_status_requires_a_checker_artifact`.

Twenty-three deliberate breaks were applied one at a time — contingencies left out of the id,
a claim pinning nothing, a contingency accepted as any string, a sketch described as a theorem,
a contingent checked result called one, the contingency dropped from a sketch's or a checked
result's provenance, stages skippable, a proof of a different statement accepted, a proof not
tied to a live sketch, undeclared assumptions let through, retractions ignored, a withdrawn
conjecture keeping its stage, `sorry` treated as an ordinary assumption or not recognised at
all, `native_decide`'s compiler axiom trusted silently, an unknown checker trusted, and the
shipped claim declaring the familiar weaker contingency. **Twenty-three of twenty-three turned
a test red on the first pass.**
