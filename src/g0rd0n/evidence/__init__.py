"""The Evidence Channel: where a claim from outside becomes something g0rd0n believes to a degree.

Three modules. `citation` retrieves a reference and refuses to call it resolved unless the
bytes say what the citation claims they say. `channel` turns resolved findings into assertions
— corroborating, refusing to launder one source into two, preserving disagreement, and
withdrawing a claim when a source disagrees with it. `seeds` is the channel pointed at
g0rd0n's own constitution: the five unsourced numbers in AGENTS.md §The Question, and what a
primary source was actually found to say about each.

It sits above `instruments`, which fetch and commit nothing, and below `cortex`, which frames
the questions these claims answer. It is not `cells`: there is no playbook and no model here.
A Cell decides what a paper says; this decides what happens to the record when it does.

Deletion criterion: this package holds the wager that every belief in g0rd0n traces to
something somebody can go and retrieve. Delete it and `unresolvable_citation_fails_the_
ingestion_run`, `duplicate_claim_from_a_second_source_raises_confidence_and_records_both_
sources`, `contradictory_claims_produce_a_conflict_record` and `seed_claims_are_retracted_
when_the_source_disagrees` lose their verdicts at once — a fabricated reference stops being
a stopped run, two sources saying different things stop being two hypotheses, and the seed
numbers in AGENTS.md can never be retracted, only quietly outlived.
"""

from g0rd0n.evidence.channel import (
    CEILING,
    EvidenceError,
    Finding,
    Ingested,
    Retraction,
    belief,
    combine,
    ingest,
    retract,
    rivals,
    sources_for,
)
from g0rd0n.evidence.citation import (
    Citation,
    Source,
    UnresolvableCitation,
    arxiv,
    resolve,
)
from g0rd0n.evidence.seeds import (
    SEEDS,
    UNVERIFIED,
    Audited,
    Seed,
    audit,
)

__all__ = [
    "CEILING",
    "SEEDS",
    "UNVERIFIED",
    "Audited",
    "Citation",
    "EvidenceError",
    "Finding",
    "Ingested",
    "Retraction",
    "Seed",
    "Source",
    "UnresolvableCitation",
    "arxiv",
    "audit",
    "belief",
    "combine",
    "ingest",
    "resolve",
    "retract",
    "rivals",
    "sources_for",
]
