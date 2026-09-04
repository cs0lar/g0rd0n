# Research-integrity monitoring

Phase 19 adds a versioned integrity policy around the Phase 16–18 method,
evaluation, and findings pipeline. Deterministic boundaries remain primary:
preflight inspection checks the frozen protocol, exact code tree, data lineage,
and permissions before execution; postflight controls check complete ordered
trajectories plus finding, receipt, and aggregate-report bindings.

`HierarchicalTraceMonitor` divides a trace according to the policy limit. Parent
summaries preserve the maximum child suspicion and the union of cited evidence;
they never average suspicion. A missing event, monitor exception, or ambiguous
judgment creates a `monitor_failure` flag and fails closed. Heuristic or LLM
judgments set `deterministic=False`: they are evidence requiring independent
confirmation, not proof of misconduct.

`IntegrityJournal` stores assessments, inspected reports, complete trace events,
confirmations, and appeals in a separate append-only hash chain. A flagged
finding remains in the Phase 18 forum but is excluded from the
integrity-controlled leaderboard. Independent reviewers can
confirm a monitor flag as a false positive. Deterministic flags remain
quarantined unless an independent appeal records both release and the false
positive, preserving the original evidence and decision history.

Run the pre-registered seeded comparison with:

```bash
uv run python -m g0rd0n.integrity \
  benchmarks/integrity/phase-19-suite.json \
  config/integrity-policy.json
```

The suite includes held-out access, benchmark imitation, score-file edits,
finding misbinding, cherry-picked reruns, judge injection, degenerate output,
gate evasion, and benign controls. It reports true- and false-positive counts,
research cost, monitoring overhead, and the declared merge-gate result.
