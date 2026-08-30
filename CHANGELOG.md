# Changelog

All notable changes to this project are recorded here. Phases refer to the roadmap in
[`AGENTS.md`](AGENTS.md).

## [Unreleased]

### Added — Phase 6a: The Evidence Channel (resolution and ingestion)

- `instruments/` — the layer that returns results and never commits. `fetch.py` is the only
  socket to anywhere but the model endpoint, and it now owns the **network allowlist**, moved
  down from `cells/model.py` so a Cell reaching a paper and a Cell reaching Anthropic go out
  through one rule rather than two copies of one.
- The allowlist is re-checked **on every redirect hop**. `urlopen` follows redirects silently,
  and `doi.org` is on the shipped allowlist precisely because it redirects.
- `evidence/citation.py` — resolve, fetch, hash, intern. **A fetch that succeeds is not a
  citation that resolves:** arXiv answers a fabricated identifier with HTTP 200 and an empty
  feed, so a `Citation` declares a `must_contain` string and the retrieved bytes are searched
  for it. Verified against the live service.
- `evidence/channel.py` — ingestion. Every citation resolves before anything is committed, so
  an unresolvable one fails the run without leaving half of it in an append-only store.
- Corroboration by noisy-OR, capped at 0.95: a second distinct source raises confidence and
  both sources are kept; the same source cited twice raises nothing. No quantity of citation
  reaches belief — promotion still needs Phase 10's three keys.
- Disagreement is preserved with no merge step. Two sources become two hypotheses under one
  question, each with its own confidence and provenance; `rivals()` lists them.
- `Bridge.retract` — the second write path and the last one. knk gives a retraction its own
  `Retraction` status and marks the original `Retracted`, so nothing here can make g0rd0n
  believe anything. It requires provenance: a claim needs a source to enter, so it needs one
  to leave.
- The bridge's write surface is now **pinned structurally** in `tests/test_razor.py`: a table
  naming each method and the knk tools it may reach, checked by an AST pass. Going from one
  write path to two turned a bright line into a judgement call, and this puts the argument for
  a third in a diff rather than in a docstring. A companion test forbids any module above
  `kernel/` from touching the MCP client directly.
- See `docs/adr/0008-a-fetch-that-succeeds-is-not-a-citation-that-resolves.md`.

### Added — Phase 5: The Question Engine

- `CHARTER.md` — the well-posed version of the task, superseding the seed framing in
  `AGENTS.md` §The Question with six criticisms attached. It fixes the separation shape (S4,
  a defended fourth: capability at a matched energy budget), the resource held fixed (joules
  at the wall, split into an inference budget `B` and a preparation budget `P` amortised over
  a declared deployment population `N`), three task families, the capability metric, the
  energy metric, the energy instrument, and the matched-capability protocol.
- `docs/charter/definitions.md` — ten formal definitions, each with a worked example. A
  definition that cannot be applied to one is rejected on the way in.
- `src/g0rd0n/cortex/charter.py` — the engine. A charter is versioned by the hash of its own
  canonical substance, so it cannot be edited: an edit is a different charter. Sections are a
  closed vocabulary, prose outside them is refused, and every required section must say
  something.
- Supersession: `Supersedes` and `Criticisms` travel together in both directions, and each
  criticism becomes its own `refines` edge carrying its text in provenance. There is no way to
  stop asking the question a given way without writing down why.
- The signature is the one section outside the version hash and names the version it signed.
  A signature naming a different one is a hard error, not a charter quietly treated as
  unsigned. `commit` refuses an unsigned charter, and refuses to commit the same one twice.
- The Charter names its definitions file by hash, so redefining a term supersedes the Charter
  and costs it a fresh signature.
- `g0rd0n charter show|commit`, a `[charter]` config section, and a `doctor` check that reports
  an unsigned charter as a failing check — it is a gate, and a gate that reports itself as fine
  when it is shut is not a gate.
- See `docs/adr/0007-the-charter-is-hashed-substance-with-a-signature-outside-it.md`.

### Added — Phase 4: The Cell Runtime (4a and 4b)

- `Cell` as data — a versioned `Playbook`, a tool allowlist, a typed output schema, and a
  budget reservation, with no base class. `runtime.run` is a function: reserve, converse,
  check, record, settle.
- A tool outside the allowlist and output failing the schema both end the run. Nothing is
  retried, and a failed run is still recorded — the transcript is interned and the `plays`
  edge committed on the way out, with settlement in the inner `finally`.
- `model.py` — the `Model` seam, a hand-rolled Anthropic Messages provider, and the network
  allowlist checked immediately before the socket opens. No default model price: an unpriced
  model refuses to run.
- `graph.py` — composition as a `dict[str, Node]`, with `$name` substitution via
  `string.Template`. Ready nodes run in name order, so two identical graphs produce identical
  ledgers.
- `human.py` — a person as an instrument: a question, a deadline, a declared fallback, and a
  `FileDrop` asker. The fallback covers the deadline and nothing else; `Run.fell_back` says
  which happened.
- See `docs/adr/0005-a-cell-is-data-and-a-failed-run-stays-failed.md` and
  `docs/adr/0006-composition-is-a-dict-and-a-person-is-a-cell.md`.

### Added — Phase 3: The Vault

- `vault/note.py` — the projection as a **pure** function `Snapshot -> {path: text}`, so
  determinism is checkable by calling a function twice. No rebuild timestamp anywhere; set
  derived content is sorted before rendering.
- `vault/projector.py` — the impure half: read the kernel, compare, drop, write. `g0rd0n vault
  rebuild` refuses any non-empty directory without a `.g0rd0n-vault` marker, and `--dry-run`
  says what it would overwrite without paying for it.
- See `docs/adr/0004-the-vault-is-a-pure-function-of-the-kernel.md`.

### Added — Phase 2: The Kernel Bridge

- An MCP stdio client speaking JSON-RPC 2.0 to `knk`'s `mcp_server` as a subprocess. g0rd0n
  never links, vendors, or forks the C++ kernel. The client restarts a dead subprocess on
  demand — the kernel replays its log, so a restart costs a replay and nothing else.
- The closed predicate vocabulary: the twelve predicates from `AGENTS.md` §Phase 2 and the
  kinds each joins. Nothing outside the table is committed, and an edge written backwards
  (`refutes` running hypothesis → result) is rejected.
- Entity references carry their kind (`hypothesis:h-001`), so direction checking needs no
  registry and knk's entity log is readable on its own. See
  `docs/adr/0003-entity-references-carry-their-kind.md`.
- `Bridge.hypothesise` — the only write path. Machine-suggested claims land as `Hypothesis`;
  there is no way to commit an `Active` assertion, because promotion needs Phase 10's three
  keys.
- Provenance is required and checked at the bridge: a source entity of kind `source` and a
  non-empty extraction method, with no exemption for well-known facts.
- Read paths: `get`, `hypotheses`, `assertions_for`, `current`, `explain`, `provenance_for`,
  `changes_since`, `conflicts`. `conflicts` surfaces and never resolves.
- CI now checks out and builds `knk` from source; the kernel tests run against a real
  `mcp_server`, never a fake.

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
