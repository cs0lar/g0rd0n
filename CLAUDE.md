# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read AGENTS.md first

`AGENTS.md` is the project's constitution and roadmap. It is authoritative; this file only
adds orientation and does not restate it. Before any change, read at minimum: **The
Imperative**, **Architectural Principles**, the section for the **current phase**, and **Do
Not Do Yet**.

## Repository state

**Phases 0–6a are built; Phase 6b (search, and the seed audit) is next.** The package is
`src/g0rd0n/`:

- `config.py` — the only reader of the config file.
- `cli.py` — `version`, `config`, `doctor`, `cost`, `vault rebuild`, `charter show|commit`,
  and nothing else.
- `ledger/` — `cost.py` (the six-dimensional `Cost`), `journal.py` (the append-only record
  and its replay), `ledger.py` (`reserve`/`spend`/`settle` and the three caps), `report.py`
  (the derived view). Depends on `config` and nothing else in `g0rd0n`.
- `kernel/` — `vocabulary.py` (the closed twelve predicates and the kinds they join),
  `mcp.py` (JSON-RPC over a `knk` subprocess), `bridge.py` (the one write path). Depends on
  `config` and nothing else in `g0rd0n`, and does not know what a Wager is.
- `vault/` — `note.py` (the projection, a **pure** function `Snapshot -> {path: text}`),
  `projector.py` (the only impure half: read the kernel, compare, drop, write). Depends on
  `config` and `kernel`. The arrow runs one way and there is no function that reads a note
  back as fact.

- `cells/` — `playbook.py` (a prompt, versioned by the hash of its own bytes), `cell.py`
  (what a Cell is: four fields of data, no base class), `model.py` (the `Model` seam, the
  hand-rolled Anthropic provider, and the network allowlist), `runtime.py` (`run`: reserve,
  converse, check, record, settle), `human.py` (a person as an instrument: question, deadline,
  fallback), `graph.py` (composition, as a dict). Depends on `config`, `ledger`, and `kernel`.

- `cortex/` — `charter.py` (the Question Engine: what a charter must fix, how one supersedes
  another, and the definitions file it names by hash). Depends on `config`, `kernel`, and
  `cells.playbook` for `version_of`.
- `instruments/` — `fetch.py` (the only socket to anywhere but the model endpoint, and the
  owner of the network allowlist). Returns results and commits nothing. Depends on nothing
  else in `g0rd0n`.
- `evidence/` — `citation.py` (resolve: fetch, check, hash, intern), `channel.py` (commit:
  dedup, corroborate, preserve disagreement, retract). Depends on `instruments`, `kernel`,
  and `ledger`.

Phase 4 is the first phase that calls a model; Phase 6 the first that reaches the open
network. Phases 1–3 built the machine that prices work, remembers it, and shows it. Phase 5
is the first that produced a research artifact: `CHARTER.md` and
`docs/charter/definitions.md`.

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

# The kernel tests need a built knk mcp_server. They default to
# ~/development/c++/knk/build/mcp_server and skip if it is absent.
uv run pytest --knk-mcp-server=/path/to/knk/build/mcp_server
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
- **Priced-before-run.** `ledger.reserve(...)` happens before the call, never after. Enforced
  by the API's shape, not by a rule to remember: `spend` and `settle` take a `Reservation`,
  and `reserve` is the only thing that makes one. Do not add a fourth `Ledger` operation, and
  do not add a `spend` overload taking a bare wager id — `no_priced_call_without_a_reservation`
  pins that surface deliberately.

Two more things about the ledger, both load-bearing:

- **Write to the journal before believing a total.** `Ledger._append` is called before the
  in-memory accumulator moves. Durable-before-visible, applied to money.
- **Overspend is checked in every dimension**, not just `usd` — an estimate right about money
  and wrong about a person's time is still wrong. Caps, by contrast, are dollars only.

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
Instruments return results but never commit assertions — a Cell commits. `evidence/` sits
between the two: not an instrument (it commits) and not a Cell (no playbook, no model). A Cell
decides what a paper says; the Evidence Channel decides what happens to the record when it
does.

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

Three things about the bridge that are easy to get wrong:

- **Entity names carry their kind**: `hypothesis:h-001`, `source:arxiv-2401-00001`. That is
  what makes the vocabulary's edge-direction check free — `refutes` runs result → hypothesis
  and the reverse is rejected. Never intern a bare name. See ADR 0003.
- **`Bridge.hypothesise` is the only way a claim enters**, deliberately. Do not add a
  `commit`. `retract` (Phase 6) is the one other write path and the last one: knk gives a
  retraction its own `Retraction` status, so nothing there can make g0rd0n *believe*
  anything. It demands provenance for the same reason `hypothesise` does.
- **`knk`'s `find_conflicts` is `Active`-only**, so `conflicts()` returns nothing while
  everything g0rd0n writes is a `Hypothesis`. That is by design, not a bug to fix: rival
  hypotheses are not a conflict, they are the ordinary state of an open question. Phase 10
  is the method's first real caller. See `AGENTS.md` §Phase 2 and ADR 0003.

The kernel tests run against a real `mcp_server`, never a mock, and CI builds `knk` from
source to get one.

## The vault

`note.render` is pure and must stay pure — no clock, no filesystem, no subprocess. That is
what makes `rebuild_is_idempotent_byte_for_byte` checkable by calling a function twice. Three
consequences that are easy to undo by accident:

- **Never put a rebuild timestamp in a note.** It would make every rebuild differ from the
  last. The timestamps that belong there are the kernel's `observed_at`.
- **Sort anything set-derived before rendering it.** Python randomises string hashing per
  process, so a same-process test agrees with itself even when the sort is gone;
  `the_projection_does_not_depend_on_python_hash_ordering` re-renders under three
  `PYTHONHASHSEED`s because the other three determinism tests all pass with that bug present.
- **`FOLDERS` must stay total over `KINDS`.** A kind with no folder is silently dropped from
  the projection, which is the one thing an index over the kernel may never do.

`rebuild` drops a directory named by a config file, so it refuses any non-empty directory
without a `.g0rd0n-vault` marker. Do not relax that. See ADR 0004.

## The cell runtime

`runtime.run` is a function, not a framework, and AGENTS.md §Style says growth here is a
design failure upstream. Four things that look like bugs and are not:

- **Nothing is retried** — not the model call, not the tool, not a schema failure. Re-asking
  a model that returned the wrong shape is a parsed guess with a bill attached.
- **A refused tool and a bad schema both end the run.** They are never fed back to the model
  as something to work around.
- **A failed run is still recorded**: the transcript is interned and the `plays` edge
  committed on the way out, whatever happened. Settlement is in the inner `finally`, so a
  recording failure never leaves a reservation open.
- **A transcript is cited from provenance, never committed as a subject or object.** knk
  leaves `intern_document` entities unnamed, and an unnamed entity in an assertion makes
  `vault rebuild` fail permanently on an append-only store.

There is no default model price: an unpriced model refuses to run rather than guessing a
number that would sit in the ledger forever. `max_tokens` is the reservation's `tokens_out`,
so the budget bounds the call rather than describing it. See ADR 0005.

## Composition and people

A graph is a `dict[str, Node]` — no builder, no executor, nothing concurrent. Tasks use
`$name` with `string.Template`, **not** `{name}` with `str.format`, because a research task is
prose full of braces (JSON, code, set notation) that `format` would read as syntax. Ready
nodes run in name order so two identical graphs produce identical ledgers. A failed node stops
the graph; every node reserves and settles on its own.

For a `HumanQuery`, the rule that catches people out: **the fallback covers the deadline and
nothing else.** A person who answers in the wrong shape is a failed run, exactly as a model
would be — substituting the fallback there would write "nobody answered" over someone who did.
`Run.fell_back` is a field rather than a note in the transcript because a graph downstream of a
fallback is running on an assumption. See ADR 0006.

## The Charter

`CHARTER.md` is the well-posed question and supersedes AGENTS.md §The Question. Its move on
the Turing trap: two Turing-complete systems separate not on what they compute but on what
they compute inside a fixed energy budget, because a serial step costs joules. So the Charter
fixes the joules (S4) and measures the capability, rather than the seed's S3 — which is
unrunnable, because it needs the candidate to already match the control arm.

Four things about `cortex/charter.py` that look arbitrary and are not:

- **A charter's version is the hash of its canonical substance**, exactly as a playbook's is.
  It cannot be edited; an edit is a different charter. The rendering is canonical rather than
  the file's bytes so that reordering sections is not a new question.
- **The signature is the one section outside the hash, and it names the hash.** A document
  cannot contain the hash of itself-plus-its-signature. A signature naming a different version
  is a hard error — the text changed after somebody put their name to it.
- **No supersession without a criticism**, and one `refines` edge per criticism, each carrying
  its text in provenance. Same discipline as "no Wager without a kill-criterion".
- **The Charter names `docs/charter/definitions.md` by hash**, inside the substance, so
  redefining a term supersedes the Charter and costs a fresh signature. Definitions are never
  committed to the kernel: they fix what words mean, they are not claims.

`commit` refuses an unsigned charter and refuses to commit the same one twice. See ADR 0007.

## The Evidence Channel

**A fetch that succeeds is not a citation that resolves.** arXiv answers a fabricated
identifier with HTTP 200 and an empty feed, so a `Citation` declares a `must_contain` string
and `resolve` searches the bytes for it. Verified against the live service. See ADR 0008.

Four more things that look arbitrary and are not:

- **Resolve everything, then commit.** One pass would leave the kernel holding whichever
  findings came first — permanently, on an append-only store.
- **A second source corroborates by noisy-OR, capped at `CEILING = 0.95`; the same source
  twice is skipped.** The cap is load-bearing: noisy-OR assumes independence, papers citing
  one original are not independent, and no quantity of citation may reach belief. Promotion
  needs Phase 10's three keys.
- **Disagreement has no merge step.** Two sources become two hypotheses under one question.
  The conflict record *is* the rival hypotheses; `rivals()` lists them and nothing reconciles.
- **A retraction needs a source too.** A claim needs one to enter, so it needs one to leave.

The network allowlist lives in `instruments/fetch.py`, not beside the model provider, and it
is re-checked **on every redirect hop** — `doi.org` is allowlisted precisely because it
redirects.

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
