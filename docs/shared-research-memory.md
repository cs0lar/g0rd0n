# Shared research memory

Phase 18 lets fresh, isolated research sessions extend durable work without
sharing a growing model context. `ResearchMemoryJournal` is an append-only,
hash-chained JSONL source of truth. Literature survey entries, proposals,
findings, and attributable reviews are reconstructed by replay; the survey,
forum, leaderboard, and session briefing are deterministic projections only.

Survey entries record applicability, mechanism, reproduction steps,
limitations, and source provenance. Proposal admission performs token-set
novelty comparison under the journal lock, before execution. Rejected
duplicates are retained as events so repeated work can trigger a stopping rule.

Findings bind a proposal to its frozen protocol hash, code hash, execution
receipt, result artifact, aggregate evaluation, failures, interpretation, and
full `ProgramCost`. Failed and invalid findings remain visible. Only valid,
eligible findings can enter the leaderboard, and each row exposes its evaluation
purpose. Final-test findings are excluded from fresh-session briefings so
held-out evidence cannot steer later search. Literature marked
`briefing_safe=False` is similarly omitted.

```python
memory = ResearchMemoryJournal(Path("runs/shared-memory.jsonl"))
decision = memory.propose(proposal)
if decision.accepted:
    # Freeze, approve, execute, and evaluate before recording the finding.
    memory.add_finding(finding)

briefing = memory.briefing(mission=mission, remaining_budget=budget)
```

Concurrent writers coordinate with an advisory file lock and reload the latest
chain while holding it. A fresh process can therefore reconstruct the same
state, while hash verification exposes edited, reordered, or incomplete events.
