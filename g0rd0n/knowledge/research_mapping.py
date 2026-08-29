"""Narrow mapping from research objects to knowledge assertions."""

from __future__ import annotations

from g0rd0n.core.research import ResearchObject

from .contract import AssertionRecord, KnowledgeStore, WriteContext

RESEARCH_PREDICATES = frozenset(
    {
        "has_hypothesis",
        "predicts",
        "tests",
        "observed_in",
        "derived_from",
        "supports",
        "contradicts",
        "depends_on",
        "invalidates",
    }
)


def research_entity(obj: ResearchObject) -> str:
    return f"g0rd0n:{obj.kind.value}:{obj.id}"


def assert_research_relation(
    store: KnowledgeStore,
    subject: ResearchObject,
    predicate: str,
    object: ResearchObject,
    context: WriteContext,
) -> AssertionRecord:
    if predicate not in RESEARCH_PREDICATES:
        raise ValueError(f"unsupported research predicate: {predicate}")
    return store.assert_(research_entity(subject), predicate, research_entity(object), context)
