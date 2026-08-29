# ADR 0004 — The vault is a pure function of the kernel, and dropping it is guarded

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 3 (The Vault)

## Context

AGENTS.md §Phase 3 asks for an Obsidian vault that is a one-way, derived projection of the
kernel, rebuildable from scratch, with `vault_rebuilds_deterministically_from_an_empty_
directory` and `rebuild_is_idempotent_byte_for_byte` as permanent CI invariants.

"Deterministic" is easy to claim and easy to lose. A projector that is a procedure — walk the
kernel, open files, write as you go — has a dozen places to pick up an ordering from a dict,
a timestamp from a clock, or a path separator from a platform, and none of those show up as a
test failure until someone happens to rebuild twice and diff the result. By then the vault has
been the thing people read for a month.

There is also a hazard the spec does not name. "`g0rd0n vault rebuild` drops and regenerates
the whole vault" means `rm -rf` on a path that arrives from a config file. `vault.root` is a
string a human typed.

## Decision

**The projection is a pure function, and writing it is a separate, dumb step.**

`note.render(Snapshot) -> dict[str, str]` maps a snapshot of the kernel to
`{relative path: file content}`. It reads no clock, opens no file, and starts no subprocess.
`projector` does the three impure things — read the kernel into a `Snapshot`, compare the
result against what is on disk, drop and write — and nothing else.

### The invariant

*The same kernel projects the same bytes, on any machine, in any process, at any time.*

Three consequences follow immediately, and are the reason for the split:

- **Determinism is testable by calling a function twice**, with no filesystem and no kernel.
- **No note records when it was generated.** A rebuild timestamp would make every rebuild
  differ from the last, which is precisely the drift the vault exists to make impossible. The
  timestamps in a note are the kernel's `observed_at`: facts about the assertion, not the run.
- **The projection is its own checksum.** Detecting hand-edits needs no manifest and no stored
  hashes — render, compare to disk, and anything that differs is a hand-edit by definition.
  A stored manifest would be a second piece of state that could itself go stale.

### Dropping is guarded by a marker

A rebuild writes `.g0rd0n-vault` at the vault root. It will drop a directory that is absent,
empty, or carries that marker, and refuses anything else with an error naming the fix. A
`vault.root` typo then costs a message rather than somebody's home directory.

### Notes are per entity

AGENTS.md lists `assertion_id`, `status`, `confidence`, `provenance`, and `superseded_by` as
frontmatter, which reads like one note per assertion. It cannot be: the folders it names are
entity kinds, and it asks that the graph view *be* the argument structure — a graph of
assertions linked to assertions is not that. So a note is an entity, and the four
per-assertion fields live in frontmatter under `claims`, one entry per assertion touching the
entity. All five fields are present and machine-readable, and no entity is given a single
`confidence` it does not have.

`superseded_by` is read off incoming `refines` edges, which is how AGENTS.md §Phase 5
supersedes a Charter. It is a list: the record is append-only, and nothing stops two
successors from refining the same question.

## Why this design

- **Against a procedural projector that writes as it walks:** every ordering and every clock
  becomes a place determinism can be lost silently, and the only test is to build twice and
  diff — which catches it after the fact rather than in the function that caused it.
- **Against storing a manifest of hashes to detect edits:** a second source of truth about
  what the vault should contain, which can disagree with the projection. The projection
  already answers the question.
- **Against incremental updates:** a projector that patches notes in place is a projector
  whose output depends on the vault's history, and the invariant is that it does not. Full
  rebuild is cheap and is the only mode.
- **Against dropping unconditionally:** a config value that can be wrong, times `rm -rf`.
- **Against slugifying unsafe entity names at projection time:** two names could slug to one
  file, and a name that cannot be projected is permanent, because the kernel is append-only.
  Rejected upstream instead — `Ref` refuses a name that could not be a note (ADR 0003 already
  refused `:`; this adds `..`, path separators, leading dots, and control characters). The
  fix belongs at the only place a name is ever constructed.

The cost is that a large kernel rebuilds in full every time. That is the right trade today
and probably for a long time: the kernel is an argument, not a dataset, and a project whose
vault is too big to rebuild has a bigger problem than its vault.

## Failure modes

- **Set iteration order leaking into a note.** Python randomises string hashing per process,
  so two `render` calls in one test agree even when the sort that makes them agree has been
  deleted — both same-process determinism tests pass with the bug present. Caught by
  `the_projection_does_not_depend_on_python_hash_ordering`, which renders in subprocesses
  under three different `PYTHONHASHSEED` values.
- **A kind with no folder.** Would be dropped from the projection without a word, which is
  the one thing an index over the kernel may never do. `FOLDERS` is total over `KINDS` and
  `every_kind_has_a_folder` fails when a thirteenth kind arrives without one.
- **Free text breaking the frontmatter.** `method` is written by a cell and lands in YAML.
  Emitted as a double-quoted scalar with escaping, tested against quotes, backslashes, and
  newlines.
- **Someone reading a note back as fact.** Not preventable by types, only by there being no
  function that does it. `differences` is the only read, and it discards what it reads.
- **A vault that stops matching the kernel because a rebuild was never run.** Real, and not
  addressed here: nothing yet rebuilds automatically. Phase 11's cockpit is the natural place
  for it, and until then the vault is as fresh as the last `g0rd0n vault rebuild`.

## How it is tested

The rendering tests build a `Snapshot` by hand and need no kernel — the payoff of purity.
The two minimum determinism tests run against a real `mcp_server` with a throwaway storage
root, because determinism against a fake kernel is determinism of the fake.
`vault_rebuilds_deterministically_from_an_empty_directory` builds into two *different* empty
directories and compares the trees, so a projector that left the previous build in place
could not pass it.

Each new invariant was checked by breaking it deliberately and confirming the failure:
unsorted successors, a rebuild timestamp in the README, a kind removed from `FOLDERS`, the
drop guard removed, and the name check removed. The first of those is the one that exposed
the hash-ordering gap — it passed all three original determinism tests.
