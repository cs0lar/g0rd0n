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

**Phase 8c — The arms and the protocol.** `g0rd0n` can price work, remember it with a source
attached, show it to a human as a navigable argument, run an agent, compose several into a
graph, put a question to a person on the same budget, go and get evidence, open a Wager on
what it finds, decide which Wager is worth running next, generate the questions that would
settle one, say what a score on them means, say what a joule figure is allowed to be quoted as
— and now run two arms against one pre-registered instance set and record what, if anything,
was shown.

**Nothing spends without a registration, all the way down.** `attempt` takes a `Reservation`
and `evaluate` takes a `Registration`, so the chain from a model call back to a wager that
passed the falsifiability gate has no string in it anybody could have typed. That closes the
gap ADR 0010 recorded at the end of Phase 7: a result cannot physically be produced before the
wager that priced it. An arm is the *subject* of the experiment rather than a cell doing
g0rd0n's work, so it commits nothing — the per-instance records live in the result, and the
argument graph gets one `measures` carrying both arms' config hashes.

**There is no evaluation with one arm**, and the baseline has to be a transformer. A candidate
tuned harder than the control arm is refused, on the figures each arm declares inside its own
version hash — so the way to pass that check is to tune the control arm, not to edit a number
after the run. A separation may be claimed only when the 95% interval on the `cap` margin
excludes zero *and* both arms stayed inside their budget; anything else is `inconclusive`,
which is a verdict and is recorded as one.

**A joule figure carries its error bar and its basis, or it does not exist.** A measurement
comes out of a calibrated session and nothing else: a session with no calibration record
produces no energy result — a refusal, not a result with a wide bar, because a wide bar is a
number somebody can still quote. Anything a model produced instead of a meter is labelled
`estimated` at the type level, and the only expression in which two instruments' numbers meet
is a `Comparison`, which derives its mixed flag from the two bases and prints it. On-die
counters are refused as a run's primary figure, because the fans, the PSU losses, the host and
the network they cannot see are exactly where a comparison against 20 W is settled.

`g0rd0n bench meters` says what this machine could read a joule with. On the machine this was
built on the answer is nothing: there is no wall-plug meter, and RAPL has been root-only since
CVE-2020-8694 — so every energy figure it can produce today is an analytic estimate, and every
comparison it appears in is flagged. That is the correct answer rather than a gap, and it costs
one command instead of one run to find out.

**A `cap` and the budget it was measured at are one object or neither is a result.** `Result`
carries the curve, `B`, `P`, `N`, the instrument and the config hash, all required, and there
is no rendering that prints the headline without them. A run that overspent its budget has no
`cap` at all rather than a `cap` with a caveat, because the caveat is the part that gets
dropped when the number is quoted somewhere else. The budget test divides by instances
*attempted* so an arm cannot come in under `B` by declining what it expects to fail;
`J_solved` divides by instances *solved* so an arm that answers fast and wrong is charged for
it.

**A capability is an ordinal with an interval under it, never an accuracy.** The three
chartered families each ship an instance generator, a size parameter and a machine-executable
checker, versioned together by content hash; a curve of one size is refused, because a system
that solves everything to size 5 and one that solves everything to size 50 report the same
accuracy on a mixed set if the mixture is chosen right. `cap` is the largest size whose mean
*and* whose 95% bootstrap lower bound clear the family's threshold, **and below which every
measured size clears too** — a capability that moves when somebody reruns the same instances
is not measuring the system, and a lone high point standing above a size that failed is
evidence about the instance set rather than about the system. Every checker is total:
prose scores zero rather than raising, and so does a right answer with an explanation appended,
because a checker that skipped what it did not understand would let an arm hedge. And what is
computed here is the score half only: a `cap` with no budget beside it is not a result under
the Charter.

`g0rd0n bench sample --family T1 --size 4 --seed 3 --answer "5 1 4 2 3"` prints one instance
exactly as an arm would see it and grades an answer typed by hand, because AGENTS.md asks for
a bench "small enough that one person can verify it is not lying" and that is the cheapest way
to check one.

**Cheapest falsifier first.** Open wagers are ranked by
`P(verdict flips the leading candidate) × value(flip) / price`: the wager worth running is not
the one likeliest to succeed, it is the one that could kill what the programme currently
believes for the least money. A wager that cannot flip anything scores exactly zero, so
cheapness is a divisor and never a reason. Pointed at the shipped portfolio, the first thing
it recommends is **an attempt to kill the control arm** — the highest-prior family, and the one
whose success would answer the question in the boring direction. And when nothing left could
change what we believe, it does not return a cheaper wager: it returns `Exhausted`, with the
criticisms a superseding Charter would have to answer.

**A wager is the hash of what it pre-registered.** Claim, test, price and kill-criterion go
into the kernel *before* anything runs, and the wager's identity is a hash of exactly those
things — so softening a kill criterion after seeing the result does not amend a wager, it
produces a different one the kernel has never heard of. Post-hoc criteria are not forbidden,
they are unrepresentable. Money moves through one function that takes proof of registration
and takes no estimate, because the price you are held to is the one you named first. And
`Verdict` is closed at four: running out of money is not one of them, and never will be.

The first thing it audited was itself. Of the five unsourced numbers in `AGENTS.md`, two are
corroborated by primary sources and three could not be verified at all — including the ~20 W
brain figure the whole question is denominated against, whose primary literature lives on hosts
nobody allowlisted. Nothing was retracted, because **failing to find a source is not finding
one that disagrees**. See [`docs/seed-audit.md`](docs/seed-audit.md).

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

That machinery has now been used in anger. Building the task suite found that the definitions
file's one worked example of what a task family *is* did not compute — it gave the composition
with a step dropped — and that it left the composition convention unstated, which is why the
error had survived. **`charter-8fb7f2095506` supersedes `charter-329c9f00e917`** with four
criticisms, including a `cap` that took a maximum where it wanted a prefix. The question
changed because implementing it was how anyone found out, which is the only reason a question
ever should.

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

uv run g0rd0n evidence search "log-precision transformers"   # primary literature
uv run g0rd0n evidence seed              # g0rd0n's own unsourced numbers, as hypotheses
uv run g0rd0n evidence audit             # ...and what a primary source says about each

uv run g0rd0n portfolio seed             # the nine candidate families and their kill criteria
uv run g0rd0n portfolio status           # where each stands, and which nothing has attacked
uv run g0rd0n portfolio next             # what is worth running next, and the arithmetic

uv run g0rd0n bench families             # the three chartered task families, and their versions
uv run g0rd0n bench sample --family T2   # one instance as an arm sees it, and what it is checked against
uv run g0rd0n bench sample --answer "5 1 4 2 3"   # ...graded by the family's own checker
uv run g0rd0n bench meters               # what this machine could read a joule with, if anything
uv run g0rd0n bench baselines            # the control arm's versioned config, and its hash
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
