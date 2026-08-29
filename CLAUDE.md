# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read AGENTS.md first

`AGENTS.md` is the project's constitution and roadmap. It is authoritative; this file only
adds orientation and does not restate it. Before any change, read at minimum: **The
Imperative**, **Architectural Principles**, the section for the **current phase**, and **Do
Not Do Yet**.

## Repository state

**Phase 0 (Skeleton and Constitution) is built; Phase 1 (the Ledger) is next.** The package
is `src/g0rd0n/` with two modules — `config.py` (the only reader of the config file) and
`cli.py` (`version`, `config`, `doctor`, and nothing else). Nothing spends anything yet,
because the Ledger does not exist, and no model is called until spending it can be priced.

Branches: `feature/claude` is this project's root branch and **every PR targets it**, not
`main`. (`feature/gpt` is a parallel implementation of the same AGENTS.md; do not merge
across.)

## Commands

Python 3.12 managed with `uv`.

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy                      # config in pyproject.toml: strict, over src and tests
uv run pytest
uv run pytest tests/test_razor.py -k deletion_criterion   # one test
uv run g0rd0n doctor             # what is missing on this machine
```

`ruff` is configured with `extend-exclude = ["*.md"]` because it otherwise reformats the
illustrative Python inside `AGENTS.md` — do not remove that exclusion.

Do not invent additional tooling (task runners, Makefiles, frameworks) without a stated
reason — the Razor applies to build configuration too.

## The one idea to hold onto

Everything is a **Wager**: `claim + test + price + kill-criterion → verdict`. No spend without
a parent Wager, no Wager without a parent Question, no Wager without a stated way to lose.
The chain from any dollar back to a question must stay unbroken, because `g0rd0n why` walks it.

Two consequences that catch people out:

- **`operating_cost` vs `target_energy`** are both joules and are never the same thing. The
  first is what g0rd0n spends; the second is a measured property of a candidate paradigm under
  evaluation. Never budget against `target_energy`; never report `operating_cost` as a result.
- **Priced-before-run.** `ledger.reserve(...)` happens before the call, never after. This is
  an invariant with a test, not a convention.

## Layering

```
Cortex        question framing, allocation, meta-loop
Cells         agents and humans, with playbooks and schemas
Instruments   tools: search, fetch, bench, prover, sandbox
Kernel        knk, via MCP
Vault         Obsidian, derived projection
Ledger        cuts across all of them and is owned by none
```

The Cortex must not know about MCP framing; the Kernel bridge must not know what a Wager is;
Instruments return results but never commit assertions — a Cell commits.

## The knk dependency

`knk` is a separate C++20 bitemporal assertion store, checked out at `~/development/c++/knk`
(docs in `docs/mcp_server.md`, server binary built at `build/mcp_server`). `g0rd0n` talks to it
**only** as an MCP stdio subprocess. Never link the C++ API, vendor it, or fork it — a missing
operation is an issue filed against `knk`, not a workaround here.

The kernel is the source of truth; the Obsidian vault is a one-way derived projection that must
rebuild byte-for-byte identically from empty. Nothing is ever read back from the vault as fact.

Commits into the kernel are constrained twice over: the closed predicate vocabulary in
`AGENTS.md` §Phase 2 (nothing outside that list, ever), and provenance (an unsourced claim is
rejected at the bridge, with no exemption for well-known facts). Machine-suggested claims land
as `Hypothesis` status and are only promoted by the Phase 10 referee.

## Working rules that differ from ordinary repos

- **One phase per PR, in order.** Do not jump ahead or fold the next phase's work in "while
  we're here". Splitting into `4a`/`4b` is allowed and should be said out loud in the PR.
- **Every module's docstring carries a `Deletion criterion:` line** naming what stops being
  checkable if the module is deleted. Enforced by `tests/test_razor.py`. Until Phase 7 gives
  us `WagerId`s to point at, it is prose; see `docs/adr/0001-the-wager-is-the-primitive.md`
  for why that compromise is dated and temporary.
- **Append-only epistemics.** Hypotheses are superseded or retracted, never edited. Refuted
  candidates stay in the record with their refutation attached.
- **Design decisions go in `docs/adr/`**, answering: what is the invariant, why this design,
  what are the failure modes, how is it tested.
- **`g0rd0n` never merges its own PR**, permanently. Self-modifying research is fine;
  self-approving research is not.
- Finish a change by answering the Razor out loud: *could this be half the size?*, and by
  stating the tradeoff taken and the thing deliberately not built.

## Permanent CI invariants

These are checked forever, not just in the phase that introduces them (full list in
`AGENTS.md` §Testing Requirements): no priced call without a reservation; costs per wager sum
to the session total; unsourced claims rejected at the bridge; wagers without a kill-criterion
rejected; results committed before pre-registration rejected; vault rebuilds deterministically;
promotion requires all three keys; every module declares a deletion criterion.

Tests use `pytest` with temporary directories and a throwaway kernel storage root per test —
never a fixed path.
