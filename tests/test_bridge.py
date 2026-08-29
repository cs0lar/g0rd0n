"""The bridge, against a real `knk`. Four of the five Phase 2 minimum tests live here.

These run against an actual `mcp_server` subprocess with a throwaway storage root per test,
never a fake. A bridge verified against a mock is a bridge verified against what its author
believed knk does.
"""

import json
from pathlib import Path

import pytest

from g0rd0n.config import Config
from g0rd0n.kernel import (
    Bridge,
    Claim,
    Provenance,
    ProvenanceError,
    Ref,
    ToolError,
    VocabularyError,
    connect,
)
from g0rd0n.kernel.mcp import Client

SEED = Provenance(source=Ref("source", "agents-md-seed"), method="AGENTS.md seed, unverified")


def a_claim(obj: str = "h-001", confidence: float = 0.5) -> Claim:
    return Claim(Ref("question", "q-001"), "hypothesises", Ref("hypothesis", obj), confidence)


def test_machine_suggested_claims_land_as_hypothesis_status(bridge: Bridge) -> None:
    """`commit_hypothesis`, never `commit`. Promotion to Active is Phase 10's, with three keys."""
    assertion_id = bridge.hypothesise(a_claim(), SEED)

    assert bridge.get(assertion_id).status == "Hypothesis"


def test_the_bridge_has_no_way_to_commit_an_active_assertion() -> None:
    """A `commit` here would be a hole with a comment next to it."""
    writes = [
        name
        for name, member in vars(Bridge).items()
        if callable(member) and not name.startswith("_") and "commit" in name
    ]

    assert writes == []
    assert not hasattr(Bridge, "commit")


def test_unsourced_claim_is_rejected_at_the_bridge(bridge: Bridge) -> None:
    """No exemption for well-known facts. The kernel wants a source; the bridge wants both."""
    with pytest.raises(ProvenanceError, match="must say how the claim was extracted"):
        bridge.hypothesise(a_claim(), Provenance(source=Ref("source", "arxiv"), method="   "))

    with pytest.raises(ProvenanceError, match="must name a source entity"):
        bridge.hypothesise(a_claim(), Provenance(source=Ref("result", "r-1"), method="ocr"))


def test_a_rejected_claim_never_reaches_the_kernel(bridge: Bridge) -> None:
    """Rejected *at the bridge* means the kernel never hears about it."""
    with pytest.raises(ProvenanceError):
        bridge.hypothesise(a_claim(), Provenance(source=Ref("source", "arxiv"), method=""))
    with pytest.raises(VocabularyError):
        bridge.hypothesise(
            Claim(Ref("question", "q-001"), "insinuates", Ref("hypothesis", "h-1"), 0.5), SEED
        )

    assert bridge.assertions_for(Ref("question", "q-001")) == []


def test_provenance_comes_back_out_with_the_claim(bridge: Bridge) -> None:
    assertion_id = bridge.hypothesise(a_claim(), SEED)

    assert bridge.provenance_for(assertion_id) == SEED


def test_conflicting_claims_are_surfaced_not_silently_reconciled(bridge: Bridge) -> None:
    """Two sources disagreeing is evidence, and both halves of it survive.

    g0rd0n never averages, prefers the newer, or drops the older: both claims keep their own
    id, confidence, and provenance, and both are readable afterwards.

    knk's `find_conflicts` considers `Active` assertions only, so it reports nothing while
    every claim g0rd0n writes is a `Hypothesis` — asserted here so the day that changes, this
    test says so. That is by design: a conflict is two things believed that cannot both be
    true, which first becomes possible at promotion. See AGENTS.md §Phase 2 and ADR 0003.
    """
    subject = Ref("hypothesis", "h-spiking-beats-transformer")
    first = bridge.hypothesise(
        Claim(subject, "predicts", Ref("observation", "o-lower-joules"), 0.7),
        Provenance(Ref("source", "paper-a"), "abstract, claimed result"),
    )
    second = bridge.hypothesise(
        Claim(subject, "predicts", Ref("observation", "o-higher-joules"), 0.4),
        Provenance(Ref("source", "paper-b"), "table 3, measured at the wall"),
    )

    both = bridge.hypotheses(subject)
    assert [assertion.id for assertion in both] == [first, second]
    assert [assertion.confidence for assertion in both] == [0.7, 0.4]
    assert bridge.provenance_for(first) != bridge.provenance_for(second)

    assert bridge.conflicts(subject, "predicts") == []


def test_a_refuted_claim_is_never_deleted(bridge: Bridge) -> None:
    """Append-only epistemics: the record of how the programme changed its mind is the point."""
    subject = Ref("hypothesis", "h-001")
    predicted = bridge.hypothesise(Claim(subject, "predicts", Ref("observation", "o-1"), 0.8), SEED)
    bridge.hypothesise(
        Claim(Ref("result", "r-1"), "refutes", subject, 0.9),
        Provenance(Ref("source", "bench-run-7"), "measured, RAPL"),
    )

    assert bridge.get(predicted).id == predicted
    assert len(bridge.assertions_for(subject)) == 1


def test_the_kernel_says_no_and_the_bridge_says_which(bridge: Bridge) -> None:
    """A tool that ran and refused is not the same failure as g0rd0n being broken."""
    with pytest.raises(ToolError, match="get"):
        bridge.get(9999)


def test_an_interned_document_can_be_cited(bridge: Bridge) -> None:
    entity = bridge.intern_document(b"we show that fixed-depth transformers sit inside TC0")

    assert entity > 0


def test_explain_walks_back_to_a_root(bridge: Bridge) -> None:
    assertion_id = bridge.hypothesise(a_claim(), SEED)

    assert [assertion.id for assertion in bridge.explain(assertion_id)] == [assertion_id]


def test_changes_since_sees_what_was_just_committed(bridge: Bridge) -> None:
    assertion_id = bridge.hypothesise(a_claim(), SEED)

    assert assertion_id in [assertion.id for assertion in bridge.changes_since(0)]


def test_bridge_survives_kernel_subprocess_restart(kernel_config: Config) -> None:
    """The kernel's log is the source of truth, so a dead subprocess costs a replay and no more.

    Kills the server mid-session, then keeps using the same bridge: the client notices, starts
    a fresh subprocess, and the assertion committed before the kill is still there — because
    it was on disk before it was ever visible.
    """
    with connect(kernel_config) as bridge:
        before = bridge.hypothesise(a_claim(), SEED)

        _kill_the_kernel(bridge)

        after = bridge.hypothesise(a_claim("h-002"), SEED)

        assert _client_of(bridge).restarts == 1, "the kill must actually have been noticed"
        assert bridge.get(before).status == "Hypothesis"
        assert after != before
        assert len(bridge.hypotheses(Ref("question", "q-001"))) == 2


def test_a_kernel_that_cannot_start_is_a_clear_error(kernel_config: Config, tmp_path: Path) -> None:
    from dataclasses import replace

    from g0rd0n.kernel import KernelUnavailable

    with connect(replace(kernel_config, kernel_mcp_server=tmp_path / "nope")) as bridge:  # noqa: SIM117
        with pytest.raises(KernelUnavailable, match="cannot start"):
            bridge.hypothesise(a_claim(), SEED)


def test_entity_names_carry_their_kind_into_the_kernel(bridge: Bridge) -> None:
    """A human reading knk's entity log can see what each name is without resolving it."""
    entity = bridge.intern(Ref("source", "arxiv-2401-00001"))
    assertion_id = bridge.hypothesise(a_claim(), SEED)
    raw = json.loads(json.dumps(bridge.get(assertion_id).__dict__))

    assert entity > 0
    assert raw["status"] == "Hypothesis"


def _client_of(bridge: Bridge) -> Client:
    """Reach past the bridge, which is the only way to watch it reconnect."""
    return bridge._client


def _kill_the_kernel(bridge: Bridge) -> None:
    """Kill the subprocess the way a crash would, leaving the bridge holding a dead pipe."""
    process = _client_of(bridge)._process
    assert process is not None, "no subprocess to kill; the test proves nothing"
    process.kill()
    process.wait()
