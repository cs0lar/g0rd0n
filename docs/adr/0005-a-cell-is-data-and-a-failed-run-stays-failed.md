# ADR 0005 — A cell is data, a failed run stays failed, and the egress point is ours

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 4a (The Cell Runtime)

## Context

AGENTS.md §Phase 4 asks for the ability to run an agent at all, with five constraints: a
versioned playbook, a tool allowlist, a budget reservation, a typed output schema, and a
transcript linked by `plays` to the playbook version. §Style adds the constraint that matters
most: no agent framework, no abstraction layers, a few hundred lines, and growth is a design
failure somewhere upstream.

Every one of those constraints is a place where the convenient thing and the auditable thing
differ, and the convenient thing is what every agent library ships by default: retry the
model when the output does not parse, feed a refused tool back as an error message so the
model can try something else, let the SDK own the socket.

## Decision

### A Cell is data

Four fields — playbook, tools, schema, estimate — and one derived `role`. No base class, no
registry, no lifecycle. `runtime.run` is a function that plays one. AGENTS.md §Style says a
cell graph is a dict, not a subclass tree; the same applies to a cell.

### Three failures that stay failures

**A tool outside the allowlist ends the run.** Not answered with an error the model can work
around. A cell reaching past its allowlist is either a design mistake or an instruction that
arrived with the data, and giving either one another turn spends money to find out which.

**Output that does not match the schema ends the run.** Never coerced, repaired, or re-asked.
Schemas are closed, so an extra field fails as hard as a missing one — a model volunteering a
field is telling you something you did not ask for, and dropping it quietly is how a cell's
contract rots. `bool` is refused where `int` is wanted, because `True == 1` in Python and a
schema that cannot separate a flag from a count is not typing anything.

**Nothing is retried, anywhere.** Not the model call, not the tool, not the schema. AGENTS.md
§Budget Discipline: a retry storm is a spending decision made by nobody. Re-asking a model
that returned the wrong shape is a parsed guess with extra steps and a bill attached.

### The output comes back through a tool, not out of prose

Every cell is offered one reserved tool, `answer`, whose parameters are its schema. A cell
finishes by calling it. The alternative — find JSON somewhere in the reply and parse it — is
the exact mechanism by which "a failed run" becomes "a parsed guess", which is the failure
§Phase 4 names. The runtime still validates what comes back: being told a shape is not being
bound to one.

### The provider is hand-rolled, and the allowlist sits on the socket

No SDK. Phase 2 made the same call for MCP and for one of the same reasons — a dependency is
a thing that changes underneath a record meant to be reproducible — but the deciding reason
here is different. §Phase 4 requires every call to pass the network allowlist. An allowlist
checked above an SDK is decoration: the SDK opens the socket, so the SDK decides where the
bytes go. `check_host` runs immediately before `urlopen`, on the URL actually used, and
`the_provider_refuses_to_send_before_it_opens_a_socket` would need a network to fail if that
ordering were ever reversed.

Matching is exact hostnames, no wildcards. A rule permitting `*.example.com` permits a host
nobody listed, and this is the boundary where "nobody decided that" costs the most.

### Prices are configuration, not constants

A model with no declared price cannot be run. There is no default and no fallback, because a
guessed price is a number nobody chose sitting in the ledger forever, corrupting every total
derived from it in a way no test can see. `model.prices` is a list of tables in the config
file, checked key by key like every other section.

`max_tokens` for each call is the reservation's `tokens_out`. The budget is not a report
about the run; it is the bound on it.

### A playbook's version is the hash of its bytes

Not a field someone bumps. An edited prompt with a stale version number attributes a run to
text that never produced it, and the record would be internally consistent and wrong — the
worst kind of error this project can make. Whitespace counts, because whitespace changes
prompts.

### The transcript is cited, not committed

`intern_document` returns an entity that knk leaves **unnamed** — `entity_name` answers
`null`. ADR 0003 requires every entity in an assertion to carry its kind, and the vault
projects notes by name, so committing an assertion against a document entity would make
`vault rebuild` fail permanently on an append-only store. The transcript is therefore
referenced from the `plays` edge's provenance (`method: knk document 47`), never as a subject
or object. `Bridge.name_of` now raises a `ToolError` naming this rule, so the mistake is a
message rather than a broken vault.

### A failed run is still recorded

The transcript is interned and the `plays` edge committed on the way out however the
conversation ended. Append-only epistemics apply to g0rd0n's own behaviour: the run that went
wrong is the one worth reading, and a runtime that records only its successes lies by
omission. Settlement sits in the inner `finally`, so a kernel that dies between the last model
call and the commit costs a transcript, never an unsettled reservation quietly shrinking every
later budget.

## Why the tests stub the model

The kernel tests run against a real `knk` because knk's behaviour is a fact g0rd0n can be
wrong about, and Phase 2 found three wrong assumptions that way. A model's output is not such
a fact. A test asserting on what a model says is a test of the model: it costs money, it is
not reproducible, and it fails on Tuesdays. What is tested here is everything around the call.

The gap that leaves is the wire format, which a stub cannot check.
`the_request_matches_the_messages_api` and `a_reply_is_read_the_way_the_api_sends_one` pin the
block structure against the documented API instead. **This is the one thing in g0rd0n not yet
verified against the real thing** — `playbooks/smoke.toml` exists to close it for a fraction
of a cent, on a machine with a key.

## Failure modes

- **A prompt edited without a new version.** Impossible: the version is the hash.
- **A price silently wrong.** Not preventable here — the config says what the operator says.
  Mitigated by there being no default to fall back to, so a *missing* price is loud.
- **A schema too weak to catch anything.** `Schema` is a flat `{name: type}` map, so a cell
  wanting nested output has no way to demand it and will reach for `dict`. Deliberate: nested
  JSON Schema is a language, and Phase 4 is not the place to grow one. Revisit if Phase 6's
  extractors need it.
- **`max_tokens` from the estimate, per call rather than per run.** A multi-turn cell can ask
  for the full output budget on each turn; the ledger's per-dimension overspend check is what
  actually stops it, one turn later than a stricter bound would.
- **A tool that spends money.** Instruments are Phase 6. When they arrive, `Tool.run` returning
  a bare string will not be enough — a tool with a cost needs a reservation of its own, and
  this ADR will need revisiting rather than the runtime quietly growing a second spend path.

## How it is tested

Each invariant was checked by breaking it and confirming the failure: the allowlist check
removed, `check_output` made permissive, `_record` skipped, the reservation settled before the
model was called, and `check_host` deleted from the provider. All five failed, and the first
attempt at the fourth was a bad break — the reserve was moved to a line that was still before
the call — which is why the test now asserts on how many reservations were *open at the moment
the model was invoked* rather than on ordering in the source.
