# Frozen Method Protocol

Phase 16 prevents a successful result from changing the story of what was
proposed. Before execution, a researcher creates a results-free
`MethodProtocol` describing the mechanism, evidence base, configuration,
assumptions, expected result, falsifiers, and compliance declarations.
`MethodJournal.freeze()` stores the complete protocol in a hash-chained log and
assigns its canonical SHA-256 digest.

## Approval and execution

Approval records bind four things: method ID, frozen protocol hash, deterministic
artifact-tree hash, and review-policy version. The artifact tree must be a
self-contained directory of regular files; symbolic links are rejected so a
digest cannot silently refer outside the reviewed boundary.

`record_execution()` hashes the tree again and refuses a receipt unless the
protocol and code match the exact approval. The receipt carries the approval,
protocol, code, and result-artifact hashes. It establishes identity and
provenance; it does not claim that the result is correct. Phase 17 owns isolated
evaluation and score validity.

## Revision and replay

A frozen method is never edited. A changed proposal receives a new stable ID and
the journal records explicit supersession. The prior protocol, approval, and
execution receipts remain available during replay. Superseded methods cannot
receive new approvals or executions.

The JSON schema documents the portable protocol shape. Runtime validation also
rejects unknown top-level fields and completed-result references embedded in
configuration. Narrative neutrality remains a human review obligation; this
phase does not pretend that keyword filtering can establish scientific honesty.
