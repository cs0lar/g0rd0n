"""The closed predicate vocabulary. No kernel needed: these refusals happen before any call."""

import pytest

from g0rd0n.kernel import VOCABULARY, Claim, Ref, VocabularyError
from g0rd0n.kernel.vocabulary import KINDS, check


def claim(subject: str, predicate: str, obj: str, confidence: float = 0.5) -> Claim:
    return Claim(Ref.parse(subject), predicate, Ref.parse(obj), confidence)


def test_the_vocabulary_is_exactly_the_twelve_predicates_agents_md_names() -> None:
    """AGENTS.md §Phase 2. A thirteenth is a change to this list and to this test."""
    assert set(VOCABULARY) == {
        "asks",
        "refines",
        "hypothesises",
        "predicts",
        "kills",
        "tests",
        "measures",
        "corroborates",
        "refutes",
        "costs",
        "cites",
        "plays",
    }


def test_predicate_outside_the_closed_vocabulary_is_rejected() -> None:
    """Nothing outside the list is ever committed. Not 'should not be' — is not."""
    with pytest.raises(VocabularyError, match="not in the closed vocabulary"):
        check(claim("question:q-1", "suggests", "hypothesis:h-1"))


def test_an_edge_written_backwards_is_rejected() -> None:
    """`refutes` runs result → hypothesis. The other direction is a different claim."""
    check(claim("result:r-1", "refutes", "hypothesis:h-1"))

    with pytest.raises(VocabularyError, match="takes a subject of kind 'result'"):
        check(claim("hypothesis:h-1", "refutes", "result:r-1"))


def test_an_object_of_the_wrong_kind_is_rejected() -> None:
    with pytest.raises(VocabularyError, match="takes an object of kind 'hypothesis'"):
        check(claim("question:q-1", "hypothesises", "result:r-1"))


def test_cites_accepts_any_claim_like_subject() -> None:
    """AGENTS.md types `cites` as claim → source, and a claim is anything assertable."""
    for kind in ("hypothesis", "result", "observation", "question", "statement", "claim"):
        check(claim(f"{kind}:x", "cites", "source:arxiv-2401-00001"))

    with pytest.raises(VocabularyError, match="takes a subject of kind"):
        check(claim("run:r-1", "cites", "source:arxiv-2401-00001"))


def test_every_predicate_joins_kinds_the_vocabulary_knows() -> None:
    """A kind that appears in no predicate is a typo nobody would ever notice."""
    for subjects, objects in VOCABULARY.values():
        assert subjects <= KINDS and objects <= KINDS


def test_a_reference_renders_and_parses_back() -> None:
    reference = Ref("hypothesis", "h-001")

    assert str(reference) == "hypothesis:h-001"
    assert Ref.parse("hypothesis:h-001") == reference


def test_a_reference_of_an_unknown_kind_is_refused() -> None:
    with pytest.raises(VocabularyError, match="not a kind this vocabulary has"):
        Ref("wagerr", "w-1")


def test_a_reference_without_a_kind_is_refused() -> None:
    with pytest.raises(VocabularyError, match="not a kind:name reference"):
        Ref.parse("h-001")


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    with pytest.raises(VocabularyError, match=r"confidence must be in \[0, 1\]"):
        check(claim("question:q-1", "asks", "statement:s-1", confidence=1.5))
