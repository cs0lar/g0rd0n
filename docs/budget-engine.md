# Transparent Budget Engine

Phase 06 treats budget as scientific state. `BudgetEngine` registers program and
session scopes, performs preflight checks, reserves declared maximum cost across
both scopes, invokes a resource, and settles actual cost into a hash-chained
JSONL `CostLedger`.

Each action records resource and capability IDs, estimate, declared maximum,
actual cost, outcome, soft warnings, invocation ID, and a diagnostic note. Failed
calls that reached the invocation boundary are charged; preflight denials have
zero actual cost but remain auditable actions.

## Limits and reservations

Hard and soft ceilings independently cover currency micros, tokens, calls, and
wall-clock milliseconds. A missing ceiling is unlimited. Hard checks use the
declared maximum—not the optimistic estimate—and include concurrent
reservations. This prevents normal execution from starting work that could
exceed a scope. Providers that report actual cost above their declared maximum
are recorded explicitly as contract violations because already-consumed
resources cannot honestly be hidden or retroactively prevented.

Stop conditions support cost dimensions, action count, and failure count. Soft
limits warn but permit work; hard limits and reached stop conditions deny it.

## Reports

`report()` emits Markdown with per-scope class, actions, failures, actual usage,
and aggregate estimated-versus-actual variance. The file-backed ledger replays
usage after restart and detects changed, removed, reordered, or partial events.
