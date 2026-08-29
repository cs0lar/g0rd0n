# Knowledge Store Boundary

Phase 03 keeps temporal knowledge behind the `KnowledgeStore` protocol. Research
logic depends only on normalized named assertions and may use either
`InMemoryKnowledgeStore` or `KnkKnowledgeStore` without provider branches.

Python spells the roadmap's `assert()` operation as `assert_()` because `assert`
is a reserved keyword. The remaining operations map directly: `retract()`,
`supersede()`, `query()`, `history()`, `provenance()`, and `conflicts()`.

## `knk` boundary

`KnkMcpClient` launches an absolute `mcp_server` binary with an absolute storage
root and communicates over newline-delimited JSON-RPC 2.0. The adapter uses only
the documented MCP tools: named commits, interning, commit retraction and
supersession, temporal queries, history, provenance, and conflict discovery.
Numeric entity, predicate, and assertion IDs never escape the adapter.

The client owns its subprocess and should be closed explicitly or used as a
context manager:

```python
with KnkMcpClient(binary, storage_root) as client:
    store = KnkKnowledgeStore(client)
```

## Research mapping

`research_mapping.py` maps stable research objects to names such as
`g0rd0n:hypothesis:H-1`. Its controlled predicates cover the initial vocabulary,
including `tests`, `derived_from`, `supports`, and `contradicts`. Confidence
remains assertion metadata and never replaces an evidence relationship.

The in-memory adapter is the executable contract reference. Contract tests run
the same lifecycle through it and through the `knk` MCP adapter. Deleting
`g0rd0n/knowledge/knk.py` therefore requires no research-logic changes.
