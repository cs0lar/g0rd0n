# Contributing to g0rd0n

## Start here

**[`AGENTS.md`](AGENTS.md) is the authoritative spec.** It defines the primitive (the Wager),
the current roadmap phase, the architectural invariants, the closed predicate vocabulary, the
permanent test list, and the things this project deliberately refuses to build. Read the
"Current Roadmap" section before starting: the project does not jump ahead of the current
phase, and PRs that do will be asked to narrow scope.

## Build & test

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

Python 3.12, `ruff`, `mypy --strict`, `pytest`. Tests use temporary directories, never fixed
paths, and the kernel under test is a throwaway storage root per test.

## Workflow

1. Branch off `feature/claude` — the project's root branch — and target PRs at it, not
   `main`. Branch names are prefixed by kind: `feature/…`, `fix/…`, `tests/…`, `refactor/…`,
   `docs/…`, `chore/…`.
2. One roadmap phase per PR, sized to be understood in one sitting. If the diff outgrows
   that, split it and say so in the description; the numbering tolerates `4a`/`4b`.
3. Add or update tests for anything you change. Every semantic change has a test.
4. Add an ADR under `docs/adr/` if a design decision was made or reversed, answering the four
   questions: what is the invariant, why this design, what are the failure modes, how is it
   tested.
5. Add a `CHANGELOG.md` entry under `## [Unreleased]` for any user-facing change.
6. In the PR description, state the tradeoff you took and the thing you deliberately did not
   build.

Commit messages use a bracketed-kind prefix: `[feature]: …`, `[fix]: …`, `[docs]: …`,
`[tests]: …`.

## The Razor

Reviewers ask one question before any other: **could this be half the size?**

- **One primitive.** If a change introduces a second way to express something the Wager or
  the assertion vocabulary already expresses, the change is wrong.
- **Deletion criterion.** Every module states, in its docstring, what would stop being
  checkable if it were deleted (from Phase 7, the settled Wager that would lose its verdict).
  Enforced by `tests/test_razor.py`.
- **One page.** Every mechanism must be explainable on one page to a competent outsider. If
  it can't be, it is not understood well enough to be built yet.
- **Cleverness is leverage, not obscurity.** A clever design does more with less machinery.

Prefer dataclasses and plain functions over classes with behaviour, and data over framework:
a cell graph is a dict, not a subclass tree. No LangChain-style abstraction layers, no agent
framework.

## Load-bearing invariants

Not style preferences — see `AGENTS.md` for the rationale:

- **The kernel is the source of truth.** The vault, caches, indexes, and cockpit views are
  derived and rebuildable. Nothing is ever read back from the vault as fact.
- **Append-only epistemics.** Hypotheses are never edited, only superseded or retracted. A
  refuted candidate stays in the record with its refutation attached.
- **Priced-before-run.** A reservation exists before a call is made, never after.
- **The question is upstream.** No hypothesis without a parent question, no experiment
  without a parent hypothesis, no spend without a parent Wager.
- **Provenance or it didn't happen.** Every claim from outside carries a resolvable source
  and an extraction method, with no exemption for well-known facts.
- **Layers stay separate.** The Cortex must not know about MCP framing; the kernel bridge
  must not know what a Wager is; instruments return results, and a Cell commits them.
- **Config is injected, never discovered.** No component reads the environment.

## Scope

Before proposing something outside the current phase — a web UI, an agent framework, a query
language over the kernel, a long-running daemon, network access outside the allowlist — check
`AGENTS.md`'s "Do Not Do Yet". These are deliberate non-goals, not oversights.

Two are permanent rather than deferred: `g0rd0n` never merges its own PR, and unattended
spend above a declared cap is never allowed. Self-modifying research is fine; self-approving
research is not.
