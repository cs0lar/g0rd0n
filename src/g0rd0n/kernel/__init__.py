"""The Kernel bridge: durable, provenance-carrying memory, via `knk`.

Three modules, one mechanism each: `vocabulary` is the closed set of predicates and the
directions they run in, `mcp` is the JSON-RPC conversation with the subprocess, `bridge` is
the one place a claim is committed or refused.

`knk` is a separate C++20 bitemporal assertion store and is reached **only** as an MCP stdio
subprocess. g0rd0n never links its API, vendors it, or forks it: a missing kernel operation is
an issue filed against knk, not a workaround here.

This package does not know what a Wager is (AGENTS.md, Keep layers separate). It moves claims,
provenance, and assertions, and it depends on `config` and nothing else in g0rd0n.

Deletion criterion: this module holds the wager that the kernel is one import away and the
MCP framing is invisible above it. Delete it and callers reach into `g0rd0n.kernel.bridge`
past the boundary, coupling the Cortex to JSON-RPC — the exact inversion AGENTS.md's layering
rule exists to prevent.
"""

from g0rd0n.kernel.bridge import (
    Assertion,
    AssertionId,
    Bridge,
    EntityId,
    Provenance,
    ProvenanceError,
    connect,
)
from g0rd0n.kernel.mcp import (
    KernelError,
    KernelProtocolError,
    KernelUnavailable,
    ToolError,
)
from g0rd0n.kernel.vocabulary import VOCABULARY, Claim, Ref, VocabularyError

__all__ = [
    "VOCABULARY",
    "Assertion",
    "AssertionId",
    "Bridge",
    "Claim",
    "EntityId",
    "KernelError",
    "KernelProtocolError",
    "KernelUnavailable",
    "Provenance",
    "ProvenanceError",
    "Ref",
    "ToolError",
    "VocabularyError",
    "connect",
]
