# g0rd0n

A research instrument with a single task:

> Find a computable AGI paradigm that is provably more powerful than deep neural networks /
> transformers, and that supports energy profiles approximating or improving on a brain's
> (~20 W, continuous).

`g0rd0n` is not a chatbot, an autonomous researcher, or a model-training pipeline. It is a
**bookkeeping machine for a research programme**: it records what is claimed, who claimed it,
what would refute it, what it cost to find out, and what happened when someone tried.

## The primitive

Not a task, a prompt, a plan, or an agent. A **Wager**:

```
claim  +  test  +  price  +  kill-criterion  →  verdict
```

A falsifiable claim with money attached and a stated way to lose. Nothing spends a token
except in service of settling a Wager, and no Wager is opened without a parent Question.
This collapses the scientific method, budget control, and self-improvement into one record:
a claim with no kill-criterion is not a hypothesis; a price reserved before work starts makes
"what did this session buy?" a `GROUP BY`; and a settled Wager is a labelled example of what
a given approach cost to reach a given verdict.

See [`AGENTS.md`](AGENTS.md) for the full constitution and roadmap, and
[`docs/adr/`](docs/adr/) for the design decisions.

## Status

**Phase 6a — The Evidence Channel.** `g0rd0n` can price work, remember it with a source
attached, show it to a human as a navigable argument, run an agent, compose several into a
graph, put a question to a person on the same budget, and now go and get evidence — refusing
any citation it cannot retrieve. Search and the seed audit are Phase 6b.

**A fetch that succeeds is not a citation that resolves.** arXiv answers a fabricated
identifier with HTTP 200 and an empty feed, so a citation declares what its own record must
contain and the bytes are searched for it; anything else fails the whole ingestion run rather
than becoming a weak claim. A second source raises confidence and both sources stay; the same
source twice raises nothing. Two sources that disagree stay two hypotheses, because averaging
them destroys the most interesting thing in the record. And a claim can be retracted — with a
source of its own, because a claim needs one to enter and so needs one to leave.

[`CHARTER.md`](CHARTER.md) is the well-posed version of the task, and it supersedes the seed
framing in `AGENTS.md` with six criticisms attached. Its central move: *"provably more
powerful than transformers"* cannot be settled, because two Turing-complete systems do not
separate on what they compute — but they do separate on what they compute inside a fixed
energy budget, because a serial step of chain-of-thought costs joules. **The Turing trap
closes when you charge for the tape.** So the Charter fixes the joules and measures the
capability, and every term it uses is defined with a worked example in
[`docs/charter/definitions.md`](docs/charter/definitions.md).

A charter is versioned by the hash of its own substance, so it cannot be edited — an edit is a
different charter. Replacing one commits a `refines` edge per criticism, and there is no way
to stop asking the question a given way without writing down why. A human reviewer signs it,
naming the version they signed, and `g0rd0n charter commit` refuses an unsigned one. That is a
gate, not a notification.

Every dollar is reserved against exactly one claim *before* the work starts, spent against
that reservation or not at all, and settled into an append-only journal that every total is
derived from. Three caps — session, campaign, standing — stop a run where it said it would
stop, settling cleanly rather than crashing.

Every claim entering memory carries a resolvable source and the method that extracted it, uses
one of twelve predicates and no others, and lands as a `Hypothesis` — there is no way to
commit a believed assertion, because promotion needs a settled Wager, a survived attack, and a
human key, and none of those exist yet.

The Obsidian vault is a **derived projection** and never a source of truth. `g0rd0n vault
rebuild` drops it and regenerates it from the kernel, byte for byte identically every time,
so the prose a human reads and the record the machine keeps cannot drift apart. Refuted
claims stay, with their refutation on the note. Hand-edits are welcome and do not survive a
rebuild — it says which files it is about to overwrite before it does, and `--dry-run` asks
without paying.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run g0rd0n version
uv run g0rd0n config     # what was loaded, after path expansion
uv run g0rd0n doctor     # what is missing, and what to do about it
uv run g0rd0n cost       # what was spent, and on which claim

uv run g0rd0n vault rebuild              # project the kernel into Obsidian
uv run g0rd0n --dry-run vault rebuild    # ...and what that would overwrite

uv run g0rd0n charter show               # the current question, and what it fixes
uv run g0rd0n charter commit             # ...into the kernel, once a human has signed it
```

A cell is data, not a class: a versioned playbook, a tool allowlist, a typed output schema,
and a budget reservation. Running one reserves before it calls, refuses any tool outside its
allowlist, refuses output its schema does not admit, and interns the transcript linked to the
exact prompt that produced it — including when the run fails, because that is the run worth
reading. A playbook's version is the hash of its own bytes, so a run can never be attributed
to text that did not produce it.

Nothing is retried: not the model call, not the tool, not a bad schema. A retry storm is a
spending decision made by nobody.

Cells compose as a plain dict — no scheduler, no node classes — where each entry names what it
needs from the ones before it. A person is one of the things a graph can call: a `HumanQuery`
has a question, a deadline, and a fallback if nobody answers, is priced in wall-clock, and is
recorded exactly as a model run is. If the deadline passes, the run says so, because a graph
running on a fallback is running on an assumption rather than an answer.

`cost` answers before anything has been spent, which is the point:

```
$ g0rd0n cost --by wager
wager                   n    reserved       spent           tokens
w-001-tc0-depth         2      $3.500      $2.370       50200→6300
w-002-landauer-check    1      $1.000      $0.310         8800→900
------------------------------------------------------------------
TOTAL                   3      $4.500      $2.680       59000→7200
```

Group by `wager`, `phase`, `agent`, or `day`. Every number is recomputed from the journal, so
the report cannot drift from the record — there is no stored total for it to disagree with.

`doctor` exits non-zero on a machine where the kernel or the vault is not set up — which is
every machine, until you edit [`config/g0rd0n.toml`](config/g0rd0n.toml) and create them.
That file is the only channel by which a path, a budget cap, or a reachable host reaches the
process; nothing below the CLI reads the environment.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest tests/test_razor.py -k deletion_criterion    # one test
```

Two of those tests are structural and permanent: every module must declare, in its docstring,
what would stop being checkable if it were deleted, and no module may read its configuration
from the environment.

## Dependencies

The knowledge kernel is [`knk`](https://github.com/cs0lar/knk), a separate C++20 bitemporal
assertion store. `g0rd0n` speaks to it as an MCP subprocess over stdio, and never links,
vendors, or forks it — a missing kernel operation is an issue filed against `knk`, not a
workaround here.

The kernel tests need a built `mcp_server` and are never run against a fake. They look for one
at `~/development/c++/knk/build/mcp_server`, skip if it is not there, and take
`--knk-mcp-server=PATH` to point elsewhere:

```bash
uv run pytest --knk-mcp-server=/path/to/knk/build/mcp_server
```

## Licence

MIT. See [`LICENSE`](LICENSE).
