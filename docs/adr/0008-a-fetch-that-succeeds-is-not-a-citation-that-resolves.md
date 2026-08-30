# ADR 0008 — A fetch that succeeds is not a citation that resolves

- **Status:** Accepted
- **Date:** 2026-08-30
- **Phase:** 6a (The Evidence Channel: resolution and ingestion)

## Context

AGENTS.md §Phase 6 names the stake plainly: "Fabricated references are the single most
damaging failure mode available to this system, and the gate against them is mechanical:
resolve, fetch, hash, or discard." It also asks that two sources agreeing raise confidence
while keeping both, that two sources disagreeing stay disagreeing, and that the seed numbers
in §The Question be verified or **retracted**.

The obvious implementation of "resolve" is an HTTP GET that returns 200. Probing the live
arXiv API while designing this showed why that is not enough:

```
id_list=1706.03762   →  200, 2965 bytes, 1 entry
id_list=2999.99999   →  200,  694 bytes, 0 entries
```

A fabricated identifier does not 404. It returns a valid, empty feed. Publishers' soft-404
pages behave the same way. A gate that checked the status code would resolve a reference to a
paper that does not exist, which is exactly the failure it was built to stop.

## Decision

### A citation declares what its own resolution must contain

```python
Citation(identifier=..., url=..., must_contain=...)
```

`resolve` fetches, then searches the bytes for `must_contain`, and raises
`UnresolvableCitation` if it is absent. One field, checked in one place, instead of a parser
per source scheme — the citation asserts "if this is real, its record says *this*", and
`arxiv()` fills it in for the one scheme this phase ships.

It must be an identifier, never a title: titles are how two different papers resolve to each
other.

Resolution establishes that the reference exists and pins the bytes that were seen. It does
**not** fetch the full text — reading the paper is a Cell's job, through its own fetch with
its own budget.

### Resolve everything before committing anything

Two passes. An unresolvable citation fails the run, and a run that committed as it went would
leave the kernel holding whichever findings happened to come first — on an append-only store,
permanently. Interning a document is still a kernel write, so a later failure can orphan a
document entity; it carries no assertion and nothing points at it, which is the cheapest of
the available wrongs.

### The allowlist moves to `instruments.fetch`, and is checked on every redirect hop

`check_host` and `NetworkRefused` were in `cells/model.py`. An instrument cannot import from
Cells without inverting AGENTS.md's layering, and two copies of an allowlist is one allowlist
that will eventually be enforced in one place only. So the rule moves down to the egress layer
and `cells/model.py` imports it.

`urlopen` follows redirects silently, so a first-URL-only check is decoration. `_Allowlisted`
re-checks every hop. This is not adversarial hypothesis: `doi.org` is on the shipped allowlist
*because* it redirects, so a citation resolved through it lands wherever the publisher says.

### Corroboration is noisy-OR, capped, and never from the same source twice

`combine(a, b) = min(CEILING, 1 − (1−a)(1−b))`, `CEILING = 0.95`.

A second *distinct* source raises the number and both provenances persist; nothing is
overwritten and nothing is merged. The same source cited twice is skipped, because reading one
paper again is not corroboration, and a channel that let it be would let one source
manufacture certainty by being cited repeatedly.

The cap is load-bearing. Noisy-OR assumes independence; two papers citing one original are not
independent, and without a ceiling a pile of secondary sources approaches certainty
arithmetically. The cap says no quantity of citation makes a claim *believed* — promotion needs
Phase 10's three keys, and this number never reaches them on its own.

### Disagreement has no merge step

Two sources saying different things become two hypotheses under one question, each with its
own confidence and sources. `rivals()` lists them; nothing reconciles them. The conflict record
**is** the competing hypotheses, exactly as AGENTS.md §Phase 6 specifies, and
`bridge.conflicts` stays silent because it speaks for the promoted set (ADR 0003).

### `Bridge.retract` is the second write path, and the last one

AGENTS.md §2 requires it — "hypotheses are never edited, they are superseded or retracted" —
and knk supports it. Probed live: `commit_retraction` gives the retraction status `Retraction`,
flips the original to `Retracted`, drops it out of `hypotheses_for`, keeps both in
`assertions_for`, and `explain` walks from one to the other.

That is why it does not breach "the bridge never writes an `Active` assertion": a retraction is
not a belief. **It requires provenance anyway.** A claim needs a source to enter, so it needs
one to leave; "we stopped believing this" with nobody's name on it is how a record quietly
loses the inconvenient half of its own history. knk's `commit_retraction` takes no source, so
the bridge pairs it with `record_provenance`, and that pairing exists in exactly one place.

**The write surface is pinned structurally**, in `tests/test_razor.py`, as a table naming each
method and the knk tools it may reach. Going from one write path to two turned a bright line
into a judgement call, and a judgement call in a docstring is one nobody re-reads: the next
person with a good reason inherits the argument shape and no obstacle. `merge_entities` is the
one to watch — knk offers it, it is "not a belief" by exactly the argument that admits
`retract`, and it would let g0rd0n silently collapse two entities. The table means a third
write path fails CI rather than passing review.

The test lives with the Razor rather than in `test_bridge.py` deliberately: the kernel tests
skip without a built `knk`, and an invariant that can be skipped is one that will be.

## Why this design

**Against making an unresolvable citation a low-confidence claim.** That is the intuitive move
and it is wrong: it converts "this paper does not exist" into "this paper is weak evidence",
which is the one transformation that makes fabrication survivable.

**Against averaging disagreement.** Averaging two sources is the cheapest way to destroy the
most interesting thing in the record. The disagreement is the finding.

**Against a per-scheme resolver registry.** A `must_contain` string is one field a human can
read in the citation itself. A registry is a place where the arXiv rule and the DOI rule drift
apart, and only one of them gets tested.

**`evidence/` is its own package, not part of `cells/` or `instruments/`.** An instrument
returns results and never commits (AGENTS.md §6), so this cannot live there. It is not a Cell
either: no playbook, no model, no turns. A Cell decides what a paper *says*; this decides what
happens to the record when it does.

## Failure modes

- **`must_contain` is only as good as what the citation declares.** A citation that names a
  string appearing on every page of a site resolves anything on that site. `arxiv()` is
  correct by construction; a hand-written `Citation` is the author's responsibility.
- **A digest pins bytes, not meaning.** arXiv's API record is stable enough for this; a
  publisher that reflows its metadata will change the hash without changing the paper, and
  that shows up as a mismatch nobody can act on until Phase 8 gives it somewhere to go.
- **`_live` resolves one assertion at a time.** N round trips per claim. At the rate evidence
  arrives this is cheaper than an index that could disagree with the log, but it is the first
  thing that will need attention if ingestion ever runs at volume.
- **Independence is assumed and unverifiable here.** The ceiling bounds the damage; it does not
  detect the case. Phase 10's referee is where a pile of correlated sources should be attacked.
- **An orphaned document entity per failed run.** See above; deliberate, and cheap.
- **The bridge does not enforce what the Evidence Channel enforces.** "A retraction needs a
  source that resolves" is real in `evidence/channel.py`, which retrieves the citation first.
  At the bridge, `_check_provenance` only requires kind `source` and a non-empty method, so
  `bridge.retract(id, Provenance(Ref("source", "because-i-said-so"), "trust me"))` passes.
  `hypothesise` has the same hole, so it is not new — and it is close to inherent, since the
  bridge cannot know what "resolved" means without knowing about the Evidence Channel, which
  would invert the layering. It is sharper for `retract`, because retraction removes.
- **Retraction is irreversible and asymmetric.** There is no un-retract, and knk refuses to
  retract an already-retracted assertion. A wrong retraction is permanent: the claim can be
  re-committed as a *new* assertion, but the original stays `Retracted` and the log then holds
  one triple twice with different statuses. Recoverable, and muddy.
- **Two new statuses arrived with no vault work.** `Retracted` and `Retraction` project into a
  note's `claims:` list as a `status` field, so they are visible — but a retraction carries the
  *same predicate* as the original, so it reads as another claim at confidence 0.0. Nothing
  marks the note as withdrawn the way `superseded_by` marks supersession. That belongs to
  Phase 11's cockpit, which is where "what did we stop believing, and why" gets a display.

## How it is tested

`tests/test_evidence.py` and `tests/test_fetch.py`. Nothing in the suite opens a socket — the
`Fetcher` seam takes a stub, and one test asserts which URLs were asked for.

- `unresolvable_citation_fails_the_ingestion_run` — three shapes: a dead link, a live 200 with
  an empty feed, and a good finding *ahead of* a bad one, which is the case that pins the
  two-pass design. With a single finding the "commits nothing" assertion passes even if the
  run committed as it went.
- `duplicate_claim_from_a_second_source_raises_confidence_and_records_both_sources`
- `contradictory_claims_produce_a_conflict_record`
- `seed_claims_are_retracted_when_the_source_disagrees` — including that the retraction is
  sourced, that both assertions stay in the log with their statuses, and that `explain` walks
  the chain.
- `a_redirect_off_the_allowlist_is_refused_mid_flight`, against a real `urllib` redirect
  handler rather than by trusting the library.
- `the_bridge_has_exactly_the_write_paths_it_declares` and
  `no_module_reaches_past_the_bridge_to_the_kernel_client`, in `tests/test_razor.py`: an AST
  pass over `bridge.py` matching each method against the knk tools it calls. Structural rather
  than behavioural on purpose — a test that committed something and checked its status would
  pass happily beside a newly added `Bridge.merge` that nobody exercised. Both were verified by
  adding the violation and watching them fail.

Nine invariants were verified by breaking them and watching the right test fail, including the
two-pass rule, the ceiling, the same-source skip, and the retraction's provenance requirement.

Also run once against the live arXiv API: a real citation resolved and committed with its
digest in provenance; `arxiv:2999.99999` was refused by the real service's real behaviour.
