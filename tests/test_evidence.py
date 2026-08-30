"""The Evidence Channel: resolution, corroboration, disagreement, and retraction.

Phase 6a's four minimum tests, against a real `knk` with a throwaway storage root. Nothing
here opens a socket: `Stub` is the `Fetcher` seam, and it is the only place a test decides
what the outside world says.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from g0rd0n.config import Config
from g0rd0n.evidence import channel as channel_module
from g0rd0n.evidence import citation as citation_module
from g0rd0n.evidence import seeds
from g0rd0n.evidence.channel import (
    Finding,
    Ingested,
    belief,
    ingest,
    retract,
    rivals,
    sources_for,
)
from g0rd0n.evidence.citation import Citation, UnresolvableCitation, arxiv
from g0rd0n.instruments.fetch import Fetched, Unreachable
from g0rd0n.kernel import Bridge, Claim, Ref
from g0rd0n.ledger import Cost, Ledger

QUESTION = Ref("question", "how-much-power-does-a-brain-use")
TWENTY_WATTS = Ref("hypothesis", "brain-runs-at-20-w")
TWELVE_WATTS = Ref("hypothesis", "brain-runs-at-12-w")

ESTIMATE = Cost(seconds=60.0)


#: An arXiv Atom feed, as the API really shapes one: the entry carries the abs URL, which is
#: the string a fabricated identifier's response does not contain.
def feed(identifier: str) -> bytes:
    return (
        f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        f"<id>http://arxiv.org/abs/{identifier}v1</id><title>A paper</title>"
        f"</entry></feed>"
    ).encode()


#: What arXiv really answers for an identifier that does not exist: 200, and an empty feed.
EMPTY_FEED = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


@dataclass
class Stub:
    """The `Fetcher` seam. Answers from a table; anything not in it is unreachable."""

    pages: Mapping[str, bytes]
    asked: list[str] = field(default_factory=list)

    def get(self, url: str) -> Fetched:
        self.asked.append(url)
        if url not in self.pages:
            raise Unreachable(f"{url} answered 404 Not Found")
        return Fetched(url=url, content=self.pages[url], media_type="application/atom+xml")


def stub_for(*identifiers: str) -> Stub:
    return Stub({arxiv(name).url: feed(name) for name in identifiers})


def ledger_for(config: Config) -> Ledger:
    return Ledger(config, session="s-1", campaign="c-1", phase="6")


def finding(
    hypothesis: Ref, identifier: str, confidence: float, method: str = "abstract, stated value"
) -> Finding:
    """One paper saying the brain runs at some power, as a claim under the question."""
    return Finding(
        claim=Claim(QUESTION, "hypothesises", hypothesis, confidence),
        cites=hypothesis,
        citation=arxiv(identifier),
        method=method,
    )


def run(findings: list[Finding], *, bridge: Bridge, config: Config, fetcher: Stub) -> Ingested:
    return ingest(
        findings,
        bridge=bridge,
        fetcher=fetcher,
        ledger=ledger_for(config),
        wager_id="w-006",
        estimate=ESTIMATE,
    )


# --- the four minimum tests --------------------------------------------------------------


def test_unresolvable_citation_fails_the_ingestion_run(
    bridge: Bridge, kernel_config: Config
) -> None:
    """A fabricated reference stops the run. It never becomes a low-confidence claim.

    Two shapes, and the second is the one that matters. A dead link is obvious. arXiv answers
    a *fabricated* identifier with HTTP 200 and an empty feed — verified against the live
    service — so a gate that only checked the status code would resolve a paper that does not
    exist, which is the exact failure this phase exists to prevent.
    """
    dead = Stub({})
    with pytest.raises(UnresolvableCitation, match="does not resolve"):
        run(
            [finding(TWENTY_WATTS, "1706.03762", 0.6)],
            bridge=bridge,
            config=kernel_config,
            fetcher=dead,
        )

    fabricated = Stub({arxiv("2999.99999").url: EMPTY_FEED})
    with pytest.raises(UnresolvableCitation, match="does not mention"):
        run(
            [finding(TWENTY_WATTS, "2999.99999", 0.6)],
            bridge=bridge,
            config=kernel_config,
            fetcher=fabricated,
        )

    # The one that pins the two-pass design: a good finding *ahead of* a bad one must not
    # survive it. With a single finding this assertion passes even if the run committed as it
    # went, so the run has to be one that would have got halfway.
    half_good = Stub({arxiv("1706.03762").url: feed("1706.03762")})
    with pytest.raises(UnresolvableCitation):
        run(
            [
                finding(TWENTY_WATTS, "1706.03762", 0.6),
                finding(TWELVE_WATTS, "2401.00001", 0.5),
            ],
            bridge=bridge,
            config=kernel_config,
            fetcher=half_good,
        )

    assert not bridge.assertions_for(QUESTION), "a failed run commits nothing at all"
    assert not bridge.assertions_for(TWENTY_WATTS), "not even the finding that resolved"


def test_duplicate_claim_from_a_second_source_raises_confidence_and_records_both_sources(
    bridge: Bridge, kernel_config: Config
) -> None:
    """Corroboration raises the number and keeps both sources. Neither is overwritten."""
    claim = Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6)
    fetcher = stub_for("1706.03762", "2401.00001")

    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )
    alone = belief(claim, bridge=bridge)

    run(
        [finding(TWENTY_WATTS, "2401.00001", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )
    corroborated = belief(claim, bridge=bridge)

    assert alone == pytest.approx(0.6)
    assert corroborated == pytest.approx(0.84), "noisy-OR: 1 - 0.4 * 0.4"
    assert corroborated > alone
    assert sources_for(claim, bridge=bridge) == (
        Ref("source", "arxiv-1706.03762"),
        Ref("source", "arxiv-2401.00001"),
    ), "both sources are kept; neither replaces the other"


def test_contradictory_claims_produce_a_conflict_record(
    bridge: Bridge, kernel_config: Config
) -> None:
    """Two sources that disagree become two hypotheses under one question, and stay that way.

    The record *is* the competing hypotheses (AGENTS.md §Phase 6). Nothing is averaged, nothing
    is preferred for being newer, and nothing is dropped — and `find_conflicts` is silent here
    on purpose, because rival hypotheses are the ordinary state of an open question.
    """
    fetcher = stub_for("1706.03762", "2401.00001")
    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.7), finding(TWELVE_WATTS, "2401.00001", 0.5)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    assert rivals(QUESTION, bridge=bridge) == (TWENTY_WATTS, TWELVE_WATTS)
    assert belief(Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.0), bridge=bridge) == (
        pytest.approx(0.7)
    )
    assert belief(Claim(QUESTION, "hypothesises", TWELVE_WATTS, 0.0), bridge=bridge) == (
        pytest.approx(0.5)
    )
    assert not bridge.conflicts(QUESTION, "hypothesises"), "Active-only, and nothing is Active"


def test_seed_claims_are_retracted_when_the_source_disagrees(
    bridge: Bridge, kernel_config: Config
) -> None:
    """A seed number is withdrawn when a primary source says otherwise — and stays in the log.

    AGENTS.md §Phase 6's first job. The retraction carries its own source, the claim leaves
    `hypotheses`, and both the claim and its withdrawal remain in `assertions_for`, which is
    what append-only epistemics means: g0rd0n changed its mind in public.
    """
    fetcher = stub_for("1706.03762", "2401.00001")
    claim = Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6)
    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )
    assert belief(claim, bridge=bridge) == pytest.approx(0.6)

    withdrawn = retract(
        claim,
        bridge=bridge,
        fetcher=fetcher,
        citation=arxiv("2401.00001"),
        method="table 2 measures 12 W, contradicting the seed",
    )

    assert belief(claim, bridge=bridge) == 0.0
    assert withdrawn.source == Ref("source", "arxiv-2401.00001")
    assert not [
        found for found in bridge.hypotheses(QUESTION) if found.id in withdrawn.retracted
    ], "a retracted claim is no longer an open hypothesis"

    everything = {found.id: found.status for found in bridge.assertions_for(QUESTION)}
    assert everything[withdrawn.retracted[0]] == "Retracted", "still in the log, marked"
    assert everything[withdrawn.retractions[0]] == "Retraction"
    chain = bridge.explain(withdrawn.retractions[0])
    assert [link.id for link in chain] == [withdrawn.retractions[0], withdrawn.retracted[0]]
    assert bridge.provenance_for(withdrawn.retractions[0]) is not None, "a retraction is sourced"


# --- the rules around them ---------------------------------------------------------------


def test_the_same_source_twice_does_not_raise_confidence(
    bridge: Bridge, kernel_config: Config
) -> None:
    """Reading one paper again is not corroboration. It is reading one paper again."""
    claim = Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6)
    fetcher = stub_for("1706.03762")

    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )
    again = run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    assert belief(claim, bridge=bridge) == pytest.approx(0.6)
    assert len(again.skipped) == 1
    assert "already cites" in again.skipped[0]


def test_corroboration_is_capped_below_certainty(bridge: Bridge, kernel_config: Config) -> None:
    """No number of agreeing sources makes a claim believed. Promotion needs three keys."""
    combined = 0.0
    for _ in range(20):
        combined = channel_module.combine(combined, 0.8)

    assert combined == pytest.approx(channel_module.CEILING)
    assert combined < 1.0


def test_a_citation_that_resolves_pins_the_bytes_it_resolved_to(
    bridge: Bridge, kernel_config: Config
) -> None:
    """Provenance carries the digest, so a page changing underneath a claim is detectable."""
    fetcher = stub_for("1706.03762")
    done = run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    provenance = bridge.provenance_for(done.assertions[0])
    assert provenance is not None
    assert "sha256 " in provenance.method
    assert "knk document " in provenance.method
    assert provenance.source == Ref("source", "arxiv-1706.03762")


def test_a_committed_finding_also_commits_its_cites_edge(
    bridge: Bridge, kernel_config: Config
) -> None:
    """AGENTS.md §Phase 6: claim extraction commits `cites` edges."""
    fetcher = stub_for("1706.03762")
    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    cited = [
        bridge.name_of(assertion.object)
        for assertion in bridge.assertions_for(TWENTY_WATTS)
        if bridge.predicate_of(assertion.predicate) == "cites"
    ]
    assert cited == [Ref("source", "arxiv-1706.03762")]


def test_a_citation_attaches_to_something_the_claim_is_about(
    bridge: Bridge, kernel_config: Config
) -> None:
    """`cites` is named rather than guessed, and refused before anything is fetched."""
    fetcher = stub_for("1706.03762")
    stray = Finding(
        claim=Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6),
        cites=Ref("hypothesis", "something-else"),
        citation=arxiv("1706.03762"),
        method="abstract",
    )

    with pytest.raises(channel_module.EvidenceError, match="neither end of the claim"):
        run([stray], bridge=bridge, config=kernel_config, fetcher=fetcher)
    assert fetcher.asked == [], "malformed findings are refused before the network is touched"


def test_an_extraction_with_no_method_is_refused(bridge: Bridge, kernel_config: Config) -> None:
    fetcher = stub_for("1706.03762")
    with pytest.raises(channel_module.EvidenceError, match="how it was extracted"):
        run(
            [finding(TWENTY_WATTS, "1706.03762", 0.6, method="  ")],
            bridge=bridge,
            config=kernel_config,
            fetcher=fetcher,
        )


def test_retracting_a_claim_nobody_made_is_an_error(bridge: Bridge, kernel_config: Config) -> None:
    """Silence would hide a mistake about what is actually in the record."""
    fetcher = stub_for("2401.00001")
    with pytest.raises(channel_module.EvidenceError, match="nothing to retract"):
        retract(
            Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6),
            bridge=bridge,
            fetcher=fetcher,
            citation=arxiv("2401.00001"),
            method="table 2",
        )


def test_a_retraction_needs_a_source_that_resolves(bridge: Bridge, kernel_config: Config) -> None:
    """A claim needs a source to enter, so it needs one to leave."""
    fetcher = stub_for("1706.03762")
    claim = Claim(QUESTION, "hypothesises", TWENTY_WATTS, 0.6)
    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    with pytest.raises(UnresolvableCitation):
        retract(
            claim,
            bridge=bridge,
            fetcher=fetcher,
            citation=arxiv("2999.99999"),
            method="a paper nobody can find",
        )
    assert belief(claim, bridge=bridge) == pytest.approx(0.6), "the claim survives"


def test_ingestion_is_priced_against_a_wager(bridge: Bridge, kernel_config: Config) -> None:
    """Wall-clock is a cost. AGENTS.md §Phase 4: every tool call passes through the Ledger."""
    fetcher = stub_for("1706.03762")
    ledger = ledger_for(kernel_config)
    done = ingest(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        fetcher=fetcher,
        ledger=ledger,
        wager_id="w-006",
        estimate=ESTIMATE,
    )

    assert done.cost.seconds >= 0.0
    assert not ledger.open_reservations, "settled on the way out"


def test_a_source_entity_name_survives_being_a_filename() -> None:
    """Entity names become note paths, so a DOI's slash cannot travel into one."""
    doi = Citation(
        identifier="doi:10.1103/PhysRevLett.110.168702",
        url="https://doi.org/10.1103/PhysRevLett.110.168702",
        must_contain="10.1103/PhysRevLett.110.168702",
    )

    assert doi.ref == Ref("source", "doi-10.1103-PhysRevLett.110.168702")
    assert "/" not in doi.ref.name


def test_an_arxiv_citation_points_at_the_machine_readable_record() -> None:
    cited = arxiv("arxiv:1706.03762")

    assert cited.identifier == "arxiv:1706.03762"
    assert cited.url == f"{citation_module.ARXIV_QUERY}1706.03762"
    assert cited.must_contain == "arxiv.org/abs/1706.03762"
    with pytest.raises(UnresolvableCitation):
        arxiv("")


def test_nothing_in_the_evidence_channel_reaches_the_network_in_tests(
    bridge: Bridge, kernel_config: Config
) -> None:
    """A guard on the seam itself: the stub records every URL asked for."""
    fetcher = stub_for("1706.03762")
    run(
        [finding(TWENTY_WATTS, "1706.03762", 0.6)],
        bridge=bridge,
        config=kernel_config,
        fetcher=fetcher,
    )

    assert fetcher.asked == [f"{citation_module.ARXIV_QUERY}1706.03762"]
    assert all(url.startswith("https://export.arxiv.org/") for url in fetcher.asked)


def test_the_shipped_allowlist_covers_the_endpoint_citations_resolve_through(
    tmp_path: Path,
) -> None:
    """The config g0rd0n ships with must be able to resolve the citations it can mint."""
    from g0rd0n.config import load

    shipped = load(Path(__file__).resolve().parents[1] / "config" / "g0rd0n.toml")
    from g0rd0n.instruments.fetch import check_host

    check_host(arxiv("1706.03762").url, shipped.network_allowlist)


# --- the seed audit ----------------------------------------------------------------------


def audit_stub() -> Stub:
    """Answers every citation the shipped audit makes, and nothing else."""
    return Stub(
        {
            arxiv(finding.citation.identifier.removeprefix("arxiv:")).url: feed(
                finding.citation.identifier.removeprefix("arxiv:")
            )
            for finding in seeds.AUDIT
        }
    )


def test_seed_claims_enter_as_unverified_hypotheses(bridge: Bridge, kernel_config: Config) -> None:
    """AGENTS.md gets no exemption from its own provenance rule.

    Its numbers enter named as its own, at a confidence that says "somebody asserted this",
    and nothing about being in the constitution makes them evidence.
    """
    committed = seeds.commit(bridge)

    assert len(committed) == len(seeds.SEEDS)
    for seed in seeds.SEEDS:
        assert belief(seed.claim, bridge=bridge) == pytest.approx(seeds.SEED_CONFIDENCE)
        assert sources_for(seed.claim, bridge=bridge) == (seeds.SEED_SOURCE,)
    provenance = bridge.provenance_for(committed[0])
    assert provenance is not None
    assert "unverified" in provenance.method


def test_seeding_twice_does_not_make_the_constitution_two_sources(
    bridge: Bridge, kernel_config: Config
) -> None:
    seeds.commit(bridge)

    assert seeds.commit(bridge) == ()
    assert belief(seeds.LANDAUER.claim, bridge=bridge) == pytest.approx(seeds.SEED_CONFIDENCE)


def test_the_audit_corroborates_what_a_source_states_and_leaves_the_rest(
    bridge: Bridge, kernel_config: Config
) -> None:
    """Two seeds have primary sources on the allowlist. Three do not, and stay as they were."""
    done = seeds.audit(
        bridge=bridge,
        fetcher=audit_stub(),
        ledger=ledger_for(kernel_config),
        wager_id="w-006-seed-audit",
    )
    standing = {seed.hypothesis.name: confidence for seed, confidence in done.standing}

    assert standing[seeds.LANDAUER.hypothesis.name] > seeds.SEED_CONFIDENCE
    assert standing[seeds.TRANSFORMER_CLASS.hypothesis.name] > seeds.SEED_CONFIDENCE
    for seed, _ in seeds.UNVERIFIED:
        assert standing[seed.hypothesis.name] == pytest.approx(seeds.SEED_CONFIDENCE)


def test_an_unverified_seed_is_not_a_retracted_one(bridge: Bridge, kernel_config: Config) -> None:
    """Failing to find a source is not finding one that disagrees.

    A channel that conflated the two would delete every claim it happened not to look hard
    enough for, which is worse than leaving one standing at a confidence that says so.
    """
    seeds.audit(
        bridge=bridge,
        fetcher=audit_stub(),
        ledger=ledger_for(kernel_config),
        wager_id="w-006-seed-audit",
    )

    for seed, why in seeds.UNVERIFIED:
        assert belief(seed.claim, bridge=bridge) > 0.0, (
            f"{seed.hypothesis.name} was retracted, and nothing disagreed with it"
        )
        assert sources_for(seed.claim, bridge=bridge) == (seeds.SEED_SOURCE,)
        assert why.strip(), "an unverified seed says why it is unverified"


def test_the_audit_is_rerunnable_without_inflating_confidence(
    bridge: Bridge, kernel_config: Config
) -> None:
    """`g0rd0n evidence audit` twice must not turn two readings of one paper into two papers."""
    first = seeds.audit(
        bridge=bridge,
        fetcher=audit_stub(),
        ledger=ledger_for(kernel_config),
        wager_id="w-006-seed-audit",
    )
    again = seeds.audit(
        bridge=bridge,
        fetcher=audit_stub(),
        ledger=ledger_for(kernel_config),
        wager_id="w-006-seed-audit",
    )

    assert dict(map(reversed, first.standing)) == dict(map(reversed, again.standing))  # type: ignore[arg-type]
    assert again.seeded == ()
    assert again.ingested.assertions == ()
    assert len(again.ingested.skipped) == len(seeds.AUDIT)


def test_two_independent_sources_reach_the_ceiling_and_stop(
    bridge: Bridge, kernel_config: Config
) -> None:
    """The transformer seed has two sources. It gets capped, not certain."""
    done = seeds.audit(
        bridge=bridge,
        fetcher=audit_stub(),
        ledger=ledger_for(kernel_config),
        wager_id="w-006-seed-audit",
    )
    standing = {seed.hypothesis.name: confidence for seed, confidence in done.standing}

    assert standing[seeds.TRANSFORMER_CLASS.hypothesis.name] == pytest.approx(
        channel_module.CEILING
    )
    assert standing[seeds.TRANSFORMER_CLASS.hypothesis.name] < 1.0


def test_every_audit_finding_points_at_a_seed_and_says_how_it_was_read() -> None:
    """A finding that cites nothing in `SEEDS` is auditing something nobody seeded."""
    hypotheses = {seed.hypothesis for seed in seeds.SEEDS}

    for finding in seeds.AUDIT:
        assert finding.cites in hypotheses
        assert finding.claim.object in hypotheses
        assert len(finding.method) > 60, "'the paper says so' is not an extraction method"
        assert finding.citation.identifier.startswith("arxiv:")


def test_the_shipped_allowlist_can_reach_every_citation_the_audit_makes() -> None:
    """An audit the shipped config cannot run is an audit nobody can reproduce."""
    from g0rd0n.config import load
    from g0rd0n.instruments.fetch import check_host

    shipped = load(Path(__file__).resolve().parents[1] / "config" / "g0rd0n.toml")
    for finding in seeds.AUDIT:
        check_host(finding.citation.url, shipped.network_allowlist)
