# ADR 0009 — Search returns identifiers, and a missing source is not a refutation

- **Status:** Accepted
- **Date:** 2026-08-30
- **Phase:** 6b (search, and the seed audit)

## Context

Phase 6a built resolution and ingestion behind a `Fetcher` seam. 6b adds the other half of
AGENTS.md §Phase 6 — "search and fetch against the allowlist; preference for primary sources
(papers, proceedings, datasheets, benchmark repositories) over secondary summaries" — and does
the phase's stated first job: "verify or retract the seed numbers in 'The Question' above."

Both halves turned on the same question, which is the one this project keeps meeting: *what
does it mean for a retrieval to have worked?*

## Decision

### Search returns citable identifiers, never passages

`Found` carries an arXiv identifier, title, date, and abstract. `evidence.arxiv(identifier)`
turns it straight into a citation the channel can resolve.

The "prefer primary sources" rule is expressed **structurally**, not as advice in a prompt: the
instrument queries a preprint server's own API, so there is no code path by which a blog post
or a summary of a paper comes back from it. A Cell handed these results can misread an
abstract; it cannot conjure a reference, because every reference in front of it already has a
URL that resolves.

Identifiers keep their version (`2207.00729v4`). arXiv accepts and echoes them, so a claim
cites the text it was read from rather than whatever the latest revision says.

### A document that parses is not a result list that arrived

The 6a lesson, met again in a second costume. An HTML error page is well-formed XML: it parses
without complaint, contains no Atom `<entry>` elements, and comes back as **"nothing matched"**.
That is the same shape of lie as a citation resolving because the fetch returned 200 — a
successful-looking answer to a question that was never asked.

So `parse` checks the root element is an Atom `feed` before believing an empty result. Found by
writing the test and watching it not raise.

Two smaller refusals for the same reason: a feed carrying `<!DOCTYPE` or `<!ENTITY` is not
parsed at all (`xml.etree` expands internal entities, so a hostile feed can cost far more than
its `MAX_BYTES`), and an entry with no arXiv identifier is an error rather than a result — a
result nothing can cite is worse than no result.

### The query goes in unquoted

`all:"log-precision transformers circuit complexity"` matches the whole thing as one exact
phrase and returns **zero results** against the live API, which reads as "no such literature
exists" rather than as a broken query. Found by searching for a paper that certainly exists and
getting nothing back. The test pins the constructed URL, which is checkable without a socket.

### A missing source is not a refutation

This is the decision that shaped the audit's outcome, and it is the one worth arguing with.

AGENTS.md says Phase 6 must "corroborate or retract" the seeds. Two of five were corroborated
against primary sources. For the other three no primary source exists **on this project's
allowlist** — the brain-energy literature is journal work on hosts nobody allowlisted, and
arXiv is simply the wrong corpus for it.

They are left standing at their seed confidence of 0.30, with `UNVERIFIED` recording why, and
**nothing was retracted**. Retraction requires a source that disagrees. A channel that treated
"I looked and found nothing" as grounds for withdrawal would delete every claim it happened not
to look hard enough for, and would do it silently, on an append-only store.

The distinction has teeth here: one of the three is not merely unsourced but suspect. The seed
divides ~20 W by ~10¹⁴–10¹⁵ synapses and reports ~10⁻¹⁴ J *per synaptic event*, while the
nearest primary figure on the allowlist (arXiv:1204.3928v1) gives a **power per synapse**. The
two coincide only at ~1 Hz average firing, which the seed asserts and does not source. That
figure was deliberately **not** committed as corroboration: it is adjacent, in different units,
and turning it into support would be the laundering the channel exists to prevent.

### The seeds and the audit are both data in the repository

`SEEDS` and `AUDIT` are tables in `evidence/seeds.py`, reviewable in a diff, and
`docs/seed-audit.md` is the argument over them. An audit whose inputs live only in somebody's
session is an audit nobody can check.

## Why this design

**Against a general web search.** It would satisfy "search" and destroy "primary sources": the
instrument would return URLs, and the preference for primary literature would become a
sentence in a prompt rather than a property of the type.

**Against retracting the unverifiable three.** It would let the phase report "verify or
retract: done", which is exactly the tidy outcome that makes a record untrustworthy. The honest
result is two corroborated, three standing at low confidence with a written reason.

**Against committing the glucose figure as support.** It is the nearest thing to evidence that
exists on the allowlist and it is in the wrong units. Using it would have made the seed look
checked.

## Failure modes

- **The allowlist decides what can be known.** This audit's main finding is a fact about
  `config/g0rd0n.toml`, not about neuroscience. That is the right place for the constraint to
  live — a reachable host enters through one reviewed file — but it means "unverified" here
  means "unverified from arXiv", and the report has to say so every time.
- **An abstract is a paper's own account of itself.** Every corroboration in this audit reads
  an abstract, not a result. `SOURCED_CONFIDENCE = 0.9` rather than 1.0 is the whole of the
  hedge, and it is thin. Reading the paper is a Cell's job and needs a model.
- **The extraction was done by a person, not a Cell.** No API key exists in this repository, so
  the `AUDIT` table was written by hand from retrieved abstracts. The provenance says which
  sentence of which abstract and what arithmetic was applied, which is repeatable — but it is
  not the machine pipeline AGENTS.md §Phase 6 ultimately describes, and a reviewer should read
  the `method` strings rather than trusting the table.
- **`sortBy=relevance` is arXiv's judgement, not ours.** A different ranking would surface
  different papers, and nothing records which ranking a search saw.

## How it is tested

`tests/test_search.py` and the seed-audit half of `tests/test_evidence.py`. Nothing opens a
socket; the `Fetcher` seam takes a stub that records the URLs it was asked for.

- `search_results_are_citable_identifiers_not_prose`
- `a_multi_word_query_is_not_an_exact_phrase_search` — pins the constructed URL
- `a_document_that_parses_is_not_a_result_list_that_arrived`
- `a_feed_with_entity_declarations_is_not_parsed`,
  `an_entry_without_an_arxiv_identifier_is_an_error`
- `seed_claims_enter_as_unverified_hypotheses`
- `an_unverified_seed_is_not_a_retracted_one`
- `the_audit_is_rerunnable_without_inflating_confidence`
- `two_independent_sources_reach_the_ceiling_and_stop`
- `the_shipped_allowlist_can_reach_every_citation_the_audit_makes`

Six invariants were verified by breaking them and watching the right test fail. One of those
breaks found a real bug: `seeds.commit` checked idempotence by asking whether the hypothesis
*entity* existed, but a seed's hypothesis is the **object** of its claim, so the two seeds that
had gained a `cites` edge skipped correctly while the three without silently re-committed. It
now asks whether `SEED_SOURCE` already supports the claim.

The audit itself was run once against the live arXiv API, end to end, and its output is
`docs/seed-audit.md`.
