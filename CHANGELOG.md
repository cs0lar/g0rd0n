# Changelog

All notable changes to this project are recorded here. Phases refer to the roadmap in
[`AGENTS.md`](AGENTS.md).

## [Unreleased]

### Added — Phase 1: The Ledger

- `Cost` — the six-dimensional unit of what work took (tokens in/out, USD, wall-clock, GPU
  seconds, human seconds). Immutable, additive, serialisable; negative costs rejected.
- `Ledger` with three operations and no others: `reserve`, `spend`, `settle`. The
  priced-before-run invariant is enforced by the API's shape — `spend` takes a `Reservation`,
  and `reserve` is the only thing that makes one.
- Overspend against a reservation raises in **any** dimension, not just dollars, and records
  nothing when it does.
- Three caps — session, campaign, standing — checked against money *committed* (settled
  actuals plus open estimates), raising `BudgetExhausted`. Caught at exactly one place, the
  CLI's error boundary.
- `open_session`, which settles every open reservation on the way out however the session
  ends: normally, on exhaustion, or on any other exception.
- An append-only JSONL journal at `[ledger] journal`, written before any total is believed.
  Every total, cap check, and report is a fold over it. See
  `docs/adr/0002-the-ledger-journal-is-append-only.md`.
- `g0rd0n cost [--by wager|phase|agent|day]` — the derived report, answerable before anything
  has been spent.
- `--dry-run`, which prices a plan against the true history and writes nothing. Wired but
  inert until a command spends (Phase 4); its help text says so.
- `doctor` now also checks the ledger journal's directory.

### Added — Phase 0: Skeleton and Constitution

- `g0rd0n` CLI with three commands and no others: `version`, `config`, `doctor`. Nothing
  spends anything; the Ledger arrives in Phase 1.
- `config/g0rd0n.toml` — kernel storage root, `knk` MCP server path, Obsidian vault root, the
  three budget caps, and the network allowlist. The only channel by which configuration
  enters the process. Unknown sections and keys are rejected rather than ignored, and the
  caps must nest.
- `docs/adr/0001-the-wager-is-the-primitive.md`, which also fixes the ADR format for every
  subsequent design decision.
- `tests/test_razor.py` — the two permanent structural invariants: every module declares a
  deletion criterion, and no module reads its configuration from the environment.
- CI: `ruff`, `mypy --strict`, `pytest` on `feature/claude`.
