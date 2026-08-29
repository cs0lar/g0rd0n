# Research Ledger

The Phase 02 ledger represents scientific work as immutable, hash-chained JSON
events. `events.jsonl` is the source of truth; in-memory state is always rebuilt
by replay. Raw evidence is stored under `artifacts/sha256/<digest>` and attached
to observations through ledger events.

## Event model

- `object_recorded` introduces a provenance-bearing research object.
- `status_transitioned` records an allowed lifecycle change and its reason.
- `relation_recorded` connects objects without modifying either one.
- `artifact_attached` links content-addressed raw evidence to an object.

Event hashes cover the complete normalized event and the preceding hash. A
changed, removed, reordered, or partially written event therefore fails replay.
Serialization sorts keys, preserves Unicode, rejects non-finite numbers, and
normalizes timestamps to timezone-aware ISO 8601 text.

## Traceability

Use explicit predicates such as `tests`, `observed_in`, `derived_from`,
`supports`, and `contradicts`. For example:

```text
Result R --derived_from--> Observation O --observed_in--> Experiment E
```

`ResearchState.trace_sources("R")` follows these upstream relations. The raw
artifact digests attached to `O` remain distinguishable from its interpretation
in `R`.

The implementation is intentionally local and dependency-free. Concurrent
writers are not supported by this reference adapter; a later storage boundary
must provide atomic compare-and-append semantics before multi-process use.
