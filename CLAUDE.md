# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read AGENTS.md first

`AGENTS.md` is the project's constitution and roadmap. It is authoritative; this file only
adds orientation and does not restate it. Before any change, read at minimum: **The
Imperative**, **Architectural Principles**, the section for the **current phase**, and **Do
Not Do Yet**.

## Repository state

**Phases 0–8b are built; Phase 8c (the arms and the run loop) is next.** The package is
`src/g0rd0n/`:

- `config.py` — the only reader of the config file.
- `content.py` — `version_of`: a thing's version is the hash of what it is. Depends on
  nothing, so every layer can reach it.
- `cli.py` — `version`, `config`, `doctor`, `cost`, `vault rebuild`, `charter show|commit`,
  `evidence search|seed|audit`, `portfolio seed|status|next`, `bench families|sample|meters`,
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
  another, and the definitions file it names by hash), `wager.py` (the Wager, the
  falsifiability gate, and pre-registration), `portfolio.py` (the nine candidate families,
  their priors, and what would kill each), `allocator.py` (cheapest falsifier first, and the
  stopping rules). Depends on `config`, `kernel`, `ledger`, `evidence.channel` for `rivals`,
  `combine` and `sources_for`, and `cells.playbook` for `version_of`.
- `instruments/` — `fetch.py` (the only socket to anywhere but the model endpoint, and the
  owner of the network allowlist), `search.py` (arXiv, returning citable identifiers and never
  prose), `tasks.py` (the three chartered task families: a generator, a size and a checker,
  hashed together), `capability.py` (the score curve, its bootstrap interval, and `cap`),
  `meter.py` (what read a joule, its calibration, and its error bar), `bench.py` (what a joule
  figure and a `cap` are allowed to be reported as). Returns results and commits nothing.
  Depends on `config` and `content` and nothing else in `g0rd0n`.
- `evidence/` — `citation.py` (resolve: fetch, check, hash, intern), `channel.py` (commit:
  dedup, corroborate, preserve disagreement, retract), `seeds.py` (the five unsourced numbers
  in AGENTS.md §The Question, and the audit of them). Depends on `instruments`, `kernel`, and
  `ledger`.

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

**The chain of `refines` edges only exists for charters that were committed**, and today none
were. `charter-8fb7f2095506` supersedes `charter-329c9f00e917`, which supersedes
`agents-md-seed-framing`, and both charters are unsigned — so if only the current one is ever
signed, its `refines` edges point at a question the kernel holds nothing else about, and the
six criticisms that retired the seed framing never become edges at all. **A supersession is
committed oldest first**, and the procedure is in
[`docs/charter/signing.md`](docs/charter/signing.md), rehearsed against a throwaway kernel.

Two things about that which are easy to get wrong. Signing does **not** change a charter's
version — the signature is the one section outside the hash — so a superseded charter
recovered from git can be signed today and still be the charter it was. And `charter.commit`
does not check that the question it supersedes is in the kernel, though `wager.register` makes
exactly that check one layer down; the ordering is therefore a convention, not an invariant,
and the reason the asymmetry is still there is a bootstrap problem written down in that file.
`g0rd0n` never signs a charter, its own or any other.

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

Two more from 6b, both the same lesson in different costumes:

- **A document that parses is not a result list that arrived.** An HTML error page is
  well-formed XML, so without a check on the root element a 503 comes back as "nothing
  matched". `parse` requires an Atom `feed`.
- **A missing source is not a refutation.** Retraction needs a source that *disagrees*.
  "I looked and found nothing" leaves the claim standing at its low confidence, with the
  reason written down in `UNVERIFIED`. See `docs/seed-audit.md` and ADR 0009.

The seed audit's result is worth knowing before touching the Charter: **the ~20 W brain figure
is the least supported claim in the kernel** (0.30, sourced only to AGENTS.md), because its
primary literature is journal work on hosts nobody allowlisted.

## The Wager

`cortex/wager.py` is where "no spend without a Wager, no Wager without a Question, no Wager
without a stated way to lose" stops being prose. Five things that look arbitrary and are not:

- **A wager's id is `f"{label}-{version}"`, and the version is the hash of its substance** —
  every field it pre-registers. So **there is no edit that keeps the id.** Soften the kill
  criterion after seeing the result and you have a different wager the kernel never heard of.
  That is what "post-hoc criteria are structurally impossible" means here. The label is
  *inside* the hash because it is what `cost --by wager` prints.
- **A wager mints two entities under one name**: `wager:<id>` carries the price, and
  `experiment:<id>` carries `tests` and later `measures`. The closed vocabulary has no
  predicate joining them — `wager` appears only as the subject of `costs` — so the shared
  name is the join. Do not add a thirteenth predicate for it. See ADR 0010.
- **The estimate goes into the kernel; the actual does not.** `wager costs cost:<id>-price`
  is a commitment you can be held to. What it really cost is the journal's, and a second copy
  is a second thing to disagree with (ADR 0002).
- **`cortex.wager.reserve` takes a `Registration` and no estimate.** Only `register` makes a
  `Registration`, so that is the one place a bare `wager_id` string becomes a claim somebody
  committed to first. Taking no estimate is half the point: re-pricing a wager at the moment
  you run it is the post-hoc move wearing a different hat.
- **`inconclusive` and `abandoned` commit `measures` and nothing else.** `ARGUES` maps them
  to `None` explicitly, so turning a null result into weak corroboration is a visible change
  to a table. `abandoned` needs a reason; `BudgetExhausted` is not a verdict and never will be.

"No Wager without a parent Question" is checked against the kernel (`rivals`), not taken on
the wager's word. Known gap, written down in ADR 0010: nothing yet proves a wager was
registered *before the experiment physically ran* — Phase 8's Bench closes that by taking the
`Registration` as an argument.

## The portfolio and the allocator

`portfolio.py` is the field (nine families from AGENTS.md, priors and kill criteria);
`allocator.py` decides what to spend on next. Five things that catch people out:

- **`read` is the only impure part.** One pass over `changes_since(0)` builds a `Board`;
  `rank`, `score`, `allocate` and `criticisms` are pure functions of it. Keep it that way —
  most of `test_allocator.py` runs without `knk` because of it. And `read` scans the *whole
  kernel* rather than the wagers in hand, because `untested` has to mean "nothing tried", not
  "nothing on this list tried".
- **`P(flip)` is zero for a challenger that cannot overtake**, and that zero is the defence
  against wager inflation (ADR 0001). Cheapness is a divisor, never a reason.
- **A wager on the leader flips by *losing*** — `P(flip) = 1 - prior`. The best wager is not
  the one likeliest to succeed. Today that makes the allocator's first pick "try to kill the
  control arm", which is correct and looks wrong.
- **`HUMAN_USD_PER_HOUR` is a ranking weight, not a price.** It never enters a `Cost`, the
  journal, or a reservation. A wager priced in neither dollars nor attention is *refused*,
  not guessed at — same rule as `Config.price_of`.
- **`Exhausted` deliberately has no wager to run**, and carries `criticisms` a superseding
  Charter can use verbatim. Exhaustion is "nothing we could run could change what we
  believe", never "we ran out of money" — `BudgetExhausted` is a different thing entirely.

The per-Wager price cap is not built here and must not be: it already *is* the pre-registered
price, enforced by `Overspend`. See ADR 0012.

## The Bench

`instruments/tasks.py` is the three chartered families; `instruments/capability.py` turns
their scores into the Charter's `cap`. Six things that catch people out:

- **A family's version covers its two functions *and* the whole file.** Hashing the `def`s
  alone misses the helper `t3_check` calls; hashing the file alone misses which callables a
  `Family` value names, and the first draft did exactly that and versioned a stub checker
  identically to the real one. Both, therefore — and the cost is that editing T3 re-versions
  T1, which is conservative in the only safe direction.
- **An `InstanceSet` is versioned by its instances, never by `(sizes, count, seed)`.** The
  recipe is stable across a generator rewrite, and a generator rewrite is exactly when two
  runs quoting "seed 11" saw different questions.
- **`curve` refuses one size, and `MINIMUM = 40` is derived, not chosen.** One size is an
  accuracy wearing a curve's name, and by the time a number reaches a report the shape is
  gone. Forty is `1 / 0.025`: below it the 95% interval's tail is under one instance wide, so
  the endpoint is the most extreme instance rather than a quantile.
- **`cap` needs the interval to clear, not just the mean, and it is a prefix.** The largest
  measured size such that it *and every measured size below it* clears — so the walk up the
  curve stops at the first failure and a lone high point above it is not reported. The
  bootstrap is seeded from a content hash of the scores, never `hash()`, which is randomised
  per process. Same trap the vault projection has a test for.
- **A checker is total and its contract is strict.** Prose scores 0.0 and never raises; a
  *correct* answer with an explanation appended also scores 0.0, because a checker that
  skipped tokens it did not understand would let an arm hedge.
- **8a is `cap` without its budget, which is not yet a result.** Nothing in `tasks.py` or
  `capability.py` measures a joule or a second. §Capability metric says a `cap` without the
  budget it was measured at is not a result; `bench.Result` is the type that pairs them.

## The meter

`instruments/meter.py` is what read a joule; `instruments/bench.py` is what a joule figure and
a `cap` are allowed to be reported as. Both are pure functions of values — no arm, no model,
no network, no kernel, and on this machine no meter either. Seven things that catch people out:

- **There is no way to hold energy that is not a `Joules`**, and a `Joules` carries its error
  bar, its instrument, and its basis. `Basis` is derived from the instrument's `Role` through
  a table, never set by a caller — a default for "was this measured?" is a lie that is true
  most of the time.
- **No calibration, no result — a refusal, not a wide bar.** `Session` has a `Calibration`
  field with no default, so the type already makes it unconstructible; `meter.session` takes
  `Calibration | None` anyway, because that is the shape the failure arrives in.
- **The error bar floors at the meter's least count.** Taken literally, the Charter's "the
  deviation is the error bar" gives `0 ± 0 J` for a meter that agrees with its load exactly —
  a claim of a perfect instrument, arrived at by the meter being good.
- **`minus` refuses two instruments; `compare` is the only place two meet.** That confines the
  scale-error assumption (a relative error passes through an idle subtraction unchanged, and
  a ratio across two instruments adds them in quadrature) and makes the mixed flag unloseable.
  A mixed comparison is **flagged, never refused** — refusing it would make the only available
  evidence about neuromorphic substrates unreportable.
- **A secondary instrument cannot carry a run.** Counters are what every machine has and a
  wall meter is what it usually does not, so quoting RAPL as the run's energy is every bench's
  path of least resistance and reports the joules of the easiest part to instrument.
- **Two denominators, and neither may do the other's job.** `per_attempted` for the budget
  test, so an arm cannot come in under `B` by declining what it expects to fail; `j_solved`
  for efficiency, so an arm that answers fast and wrong is charged. `k = 0` gives `None`.
- **A run outside its budget has no `cap` at all**, not a `cap` with a caveat — the caveat is
  the part that gets dropped when the number is quoted elsewhere. And `W` is deliberately not
  a `Budget` field: it is already inside `Family.spec`'s hash.

`g0rd0n bench meters` reports that this machine has no primary instrument and cannot read RAPL
either (root-only since CVE-2020-8694), so every energy figure it can produce today is an
`estimated` one. That is the correct answer, not a gap. See ADR 0014.

Building the bench found two defects in the Charter itself, and both were fixed the only way
they can be — by superseding it. **`charter-8fb7f2095506` supersedes `charter-329c9f00e917`**
with four criticisms: the T1 worked example gave the composition with one step dropped, it
left the composition convention unstated (which is why the error survived), its §Task family
prose described a generator nobody could write, and `cap` took a maximum where it wanted a
prefix. ADR 0013 carries the amendments. Neither charter is signed, so neither is in the
kernel — see the note under *The Charter* about what that costs.

## Working rules that differ from ordinary repos

- **One phase per PR, in order.** Do not jump ahead or fold the next phase's work in "while
  we're here". Splitting into `4a`/`4b` is allowed and should be said out loud in the PR.
- **Every module's docstring carries a `Deletion criterion:` line** that **names at least one
  test that exists**, in backticks, with or without its `test_` prefix. Enforced by
  `tests/test_razor.py`. Renaming a test means grepping docstrings for its name — that is the
  cost of the identifier resolving at all. It resolves against the test suite rather than
  against a `WagerId` in the kernel, which is what ADR 0001 originally promised; ADR 0011
  records why, the short version being that a kernel lookup would make the Razor skip on any
  machine without a built `knk`.
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

Two more structural ones live in `tests/test_razor.py` and parse source rather than running it,
so they cannot be skipped by a machine without `knk`: the bridge has exactly the write paths
`WRITE_PATHS` declares (`hypothesise` and `retract`, and a third needs an ADR), and no module
above `kernel/` touches the MCP client directly.

Tests use `pytest` with temporary directories and a throwaway kernel storage root per test —
never a fixed path.
