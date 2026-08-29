# Changelog

All notable changes to this project are recorded here. Phases refer to the roadmap in
[`AGENTS.md`](AGENTS.md).

## [Unreleased]

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
