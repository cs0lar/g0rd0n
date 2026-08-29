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

**Phase 2 — The Kernel Bridge.** `g0rd0n` can price work it has not learned to do, and
remember what it is told with a source attached. It still calls no model: the cell runtime is
Phase 4.

Every dollar is reserved against exactly one claim *before* the work starts, spent against
that reservation or not at all, and settled into an append-only journal that every total is
derived from. Three caps — session, campaign, standing — stop a run where it said it would
stop, settling cleanly rather than crashing.

Every claim entering memory carries a resolvable source and the method that extracted it, uses
one of twelve predicates and no others, and lands as a `Hypothesis` — there is no way to
commit a believed assertion, because promotion needs a settled Wager, a survived attack, and a
human key, and none of those exist yet.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run g0rd0n version
uv run g0rd0n config     # what was loaded, after path expansion
uv run g0rd0n doctor     # what is missing, and what to do about it
uv run g0rd0n cost       # what was spent, and on which claim
```

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
