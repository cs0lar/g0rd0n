"""Turning resolved findings into assertions: dedup, corroboration, and retraction.

The committing half of the Evidence Channel. An instrument returns bytes; this is where they
become something g0rd0n believes to a degree, with a source attached (AGENTS.md §6).

Four rules, and they are the whole module:

- **Resolve everything before committing anything.** An unresolvable citation fails the run,
  and a run that failed halfway would leave the kernel holding the claims that happened to
  come first. Two passes: retrieve every citation, then commit. (Interning a document is a
  kernel write, so a later failure can leave an orphan document entity behind. It carries no
  assertion and nothing points at it, which is the cheapest of the available wrongs.)
- **A second source raises confidence; the same source twice does not.** Reading one paper
  again is not corroboration, and a channel that let it be would let a single source
  manufacture certainty by being cited repeatedly.
- **Disagreement is preserved, never averaged.** Two sources that say different things produce
  two hypotheses under one question, each keeping its own confidence and provenance. There is
  no merge step, because the merge is the thing that destroys the interesting record.
- **A retraction needs a source too.** A claim needs one to enter, so it needs one to leave.
  "We stopped believing this" with nobody's name on it is how a record quietly loses the
  inconvenient half of its own history.

Corroboration combines by noisy-OR — `1 - (1-a)(1-b)` — capped at `CEILING`. The cap is not
decoration: noisy-OR assumes the sources are independent, two papers citing one original are
not, and without a ceiling a pile of secondary sources arithmetically approaches certainty.
The cap says no number of citations makes a claim believed; promotion needs Phase 10's three
keys, and this number never reaches them on its own.

Deletion criterion: this module holds the wager that evidence accumulates without being
laundered. Delete it and `duplicate_claim_from_a_second_source_raises_confidence_and_records_
both_sources`, `contradictory_claims_produce_a_conflict_record`, and `seed_claims_are_
retracted_when_the_source_disagrees` all lose their verdicts at once, and two disagreeing
papers become one averaged number nobody can trace.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from g0rd0n.evidence.citation import Citation, Source, resolve
from g0rd0n.instruments.fetch import Fetcher
from g0rd0n.kernel import Assertion, AssertionId, Bridge, Claim, Ref
from g0rd0n.kernel.vocabulary import CLAIM_KINDS, check
from g0rd0n.ledger import Cost, Ledger

#: How the ledger attributes this work. Not a Cell — no playbook, no model, no turns — but it
#: spends wall-clock against a Wager like everything else does.
AGENT = "evidence"

#: The most confidence corroboration alone can produce. See the module docstring.
CEILING = 0.95

#: Statuses that no longer say anything. knk marks a withdrawn claim `Retracted` and the
#: withdrawal itself `Retraction`; neither counts as a live claim for corroboration or belief.
DEAD = frozenset({"Retracted", "Retraction"})


class EvidenceError(Exception):
    """A finding could not be ingested as described."""


@dataclass(frozen=True)
class Finding:
    """One claim extracted from one source, with the citation that carries it.

    `cites` names which end of the claim the citation attaches to, and is required rather than
    inferred. For `question:q hypothesises hypothesis:h` the citation belongs on the
    hypothesis, not the question — the question was ours and the hypothesis came from the
    paper — and a rule that guessed would eventually attribute one of our own questions to
    somebody else's work.
    """

    claim: Claim
    cites: Ref
    citation: Citation
    method: str


@dataclass(frozen=True)
class Ingested:
    """What one ingestion run put into the kernel, and what it declined to."""

    assertions: tuple[AssertionId, ...]
    sources: tuple[Ref, ...]
    corroborated: tuple[Ref, ...]
    skipped: tuple[str, ...]
    cost: Cost


@dataclass(frozen=True)
class Retraction:
    """A claim withdrawn, and the source that disagreed with it."""

    retracted: tuple[AssertionId, ...]
    retractions: tuple[AssertionId, ...]
    source: Ref


def ingest(
    findings: Sequence[Finding],
    *,
    bridge: Bridge,
    fetcher: Fetcher,
    ledger: Ledger,
    wager_id: str,
    estimate: Cost,
) -> Ingested:
    """Resolve every citation, then commit what survives.

    Raises `UnresolvableCitation` before anything is committed if any citation does not
    resolve, and `EvidenceError` before anything is fetched if a finding is malformed.
    """
    for finding in findings:
        _check(finding)

    reservation = ledger.reserve(wager_id, estimate, AGENT)
    spent = Cost()
    try:
        started = time.monotonic()
        sources: dict[str, Source] = {}
        for finding in findings:
            if finding.citation.identifier not in sources:
                sources[finding.citation.identifier] = resolve(
                    finding.citation, bridge=bridge, fetcher=fetcher
                )
        spent = Cost(seconds=time.monotonic() - started)
        ledger.spend(reservation, spent)

        committed: list[AssertionId] = []
        corroborated: list[Ref] = []
        skipped: list[str] = []
        for finding in findings:
            source = sources[finding.citation.identifier]
            live = _live(finding.claim, bridge=bridge)
            if source.ref in {supporting for _, supporting in live}:
                skipped.append(
                    f"{finding.claim.subject} {finding.claim.predicate} {finding.claim.object} "
                    f"already cites {source.ref}"
                )
                continue

            confidence = finding.claim.confidence
            if live:
                standing = max(found.confidence for found, _ in live)
                confidence = combine(standing, confidence)
                corroborated.append(finding.cites)
            committed.append(
                bridge.hypothesise(
                    Claim(
                        subject=finding.claim.subject,
                        predicate=finding.claim.predicate,
                        object=finding.claim.object,
                        confidence=confidence,
                    ),
                    source.provenance(finding.method),
                )
            )
            committed.append(
                bridge.hypothesise(
                    Claim(finding.cites, "cites", source.ref, 1.0),
                    source.provenance(f"citation given with {finding.method}"),
                )
            )
    finally:
        ledger.settle(reservation)

    return Ingested(
        assertions=tuple(committed),
        sources=tuple(source.ref for source in sources.values()),
        corroborated=tuple(corroborated),
        skipped=tuple(skipped),
        cost=spent,
    )


def retract(
    claim: Claim,
    *,
    bridge: Bridge,
    fetcher: Fetcher,
    citation: Citation,
    method: str,
) -> Retraction:
    """Withdraw every live assertion of a claim, on the authority of a source that disagrees.

    The citation is resolved first, for the same reason ingestion resolves before committing:
    a retraction justified by a reference nobody can retrieve is worse than no retraction,
    because it removes a sourced claim in favour of an unsourced one.

    Raises `EvidenceError` if nothing live says the claim. Retracting something that is not
    there is a mistake about what is in the record, and silence would hide it.
    """
    source = resolve(citation, bridge=bridge, fetcher=fetcher)
    live = _live(claim, bridge=bridge)
    if not live:
        raise EvidenceError(
            f"nothing live says {claim.subject} {claim.predicate} {claim.object}, so there is "
            "nothing to retract"
        )
    retracted = tuple(found.id for found, _ in live)
    retractions = tuple(
        bridge.retract(assertion_id, source.provenance(method)) for assertion_id in retracted
    )
    return Retraction(retracted=retracted, retractions=retractions, source=source.ref)


def belief(claim: Claim, *, bridge: Bridge) -> float:
    """The strongest live confidence for this exact triple, or 0.0 if nothing says it.

    The strongest rather than the newest, so the answer does not depend on assertion order.
    Corroboration only ever raises a confidence, so for anything this module wrote the two
    readings agree — but "strongest" stays true if something else ever writes a weaker one.
    """
    return max((found.confidence for found, _ in _live(claim, bridge=bridge)), default=0.0)


def sources_for(claim: Claim, *, bridge: Bridge) -> tuple[Ref, ...]:
    """Every source behind a claim, in the order they were recorded. Both halves of a
    corroboration are here, which is the point of not merging them."""
    return tuple(supporting for _, supporting in _live(claim, bridge=bridge))


def rivals(question: Ref, *, bridge: Bridge) -> tuple[Ref, ...]:
    """The competing hypotheses under one question, which is what a conflict record *is*.

    AGENTS.md §Phase 2: rival hypotheses are not a conflict, they are the ordinary state of an
    open question, and knk's `find_conflicts` speaks only for the promoted set. So the record
    of a disagreement is this list — every hypothesis the question has, each keeping its own
    confidence and its own sources — and nothing reconciles it.
    """
    found = []
    for assertion in bridge.assertions_for(question):
        if assertion.status in DEAD or bridge.predicate_of(assertion.predicate) != "hypothesises":
            continue
        ref = bridge.name_of(assertion.object)
        if ref not in found:
            found.append(ref)
    return tuple(found)


def combine(standing: float, arriving: float) -> float:
    """Noisy-OR, capped. Two independent sources agreeing is worth more than either alone."""
    return min(CEILING, 1.0 - (1.0 - standing) * (1.0 - arriving))


def _live(claim: Claim, *, bridge: Bridge) -> list[tuple[Assertion, Ref]]:
    """Every assertion of this exact triple that has not been retracted, with its source.

    Resolved one assertion at a time because knk answers by subject and hands back ids. At the
    rate evidence arrives this is cheaper than an index that could disagree with the log.
    """
    found: list[tuple[Assertion, Ref]] = []
    for assertion in bridge.assertions_for(claim.subject):
        if assertion.status in DEAD:
            continue
        if bridge.predicate_of(assertion.predicate) != claim.predicate:
            continue
        if bridge.name_of(assertion.object) != claim.object:
            continue
        provenance = bridge.provenance_for(assertion.id)
        if provenance is not None:
            found.append((assertion, provenance.source))
    return found


def _check(finding: Finding) -> None:
    """Refuse a malformed finding before anything is fetched, let alone committed."""
    check(finding.claim)
    if finding.cites not in (finding.claim.subject, finding.claim.object):
        raise EvidenceError(
            f"{finding.cites} is neither end of the claim it cites for; a citation attaches to "
            "something the claim is about"
        )
    if finding.cites.kind not in CLAIM_KINDS:
        raise EvidenceError(
            f"a {finding.cites.kind!r} cannot cite anything; `cites` runs claim → source"
        )
    if not finding.method.strip():
        raise EvidenceError("a finding must say how it was extracted; 'LLM' is not a method")
