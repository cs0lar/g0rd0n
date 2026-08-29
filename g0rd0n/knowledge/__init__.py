"""Replaceable temporal knowledge-store boundary."""

from .contract import (
    AssertionRecord,
    AssertionStatus,
    Conflict,
    KnowledgeStore,
    ProvenanceRecord,
    Query,
    WriteContext,
)
from .memory import InMemoryKnowledgeStore

__all__ = [
    "AssertionRecord",
    "AssertionStatus",
    "Conflict",
    "InMemoryKnowledgeStore",
    "KnowledgeStore",
    "ProvenanceRecord",
    "Query",
    "WriteContext",
]
