# Signing and committing a charter

`g0rd0n charter commit` refuses an unsigned charter. That refusal is the Phase 5 gate: a
charter can be read, printed, reviewed and argued with unsigned, but it never becomes the
question a Wager descends from until a human puts their name to a specific version.
`g0rd0n` does not sign its own charter, and no automation in this repository may add a
`## Signed-off-by` section.

## Signing one

Append the section, naming yourself, the date, and **the version you are signing**:

```markdown
## Signed-off-by

Your Name <handle>, 2026-09-01, charter-8fb7f2095506
```

The signature is the one section outside the version hash — a document cannot contain the
hash of itself-including-its-signature — so it names the version instead. Adding it therefore
does **not** change the charter's version. A signature naming a different version is a hard
error rather than a charter treated as unsigned: the text changed after somebody signed it,
and silently downgrading would lose the fact that they had.

`g0rd0n charter show` prints the current version. `g0rd0n --dry-run charter commit` says what
would be written without a kernel.

## Committing a supersession: the predecessor goes first

**A `refines` edge is only worth having if both ends are in the kernel.** `charter commit`
will happily supersede a question the kernel has never held — it interns the name and writes
the edge — and the result is a chain that starts in mid-air: `g0rd0n why` walks from the
operative question to an entity nothing else says anything about, and the criticisms that
retired *that* question were never recorded at all.

So a supersession is committed oldest first. Today that means:

```
charter-8fb7f2095506  --refines(x4)-->  charter-329c9f00e917  --refines(x6)-->  agents-md-seed-framing
```

Committing only the newest charter puts the four edges on the left in the kernel and loses the
six on the right — the entire argument for why the seed framing stopped being the question.

This means signing a charter you have already written down four faults with. That is not a
contradiction; it is what append-only epistemics looks like. You sign what was actually asked,
and then you supersede it with the reasons attached. A record that only ever holds the current
answer is a record that cannot show anybody changing their mind.

### The procedure

A superseded charter's text is not in the working tree — this repository keeps exactly one
`CHARTER.md`, and git is the archive. A second copy checked in beside it would be a second
thing to disagree with (ADR 0002). Recover it, and the definitions file it named:

```bash
mkdir -p /tmp/charters
git show <commit-before-the-supersession>:CHARTER.md              > /tmp/charters/old.md
git show <commit-before-the-supersession>:docs/charter/definitions.md > /tmp/charters/old-definitions.md
```

`charter.path` and `charter.definitions` are config settings precisely so they can point
somewhere else, so no flag is needed. Copy your config, point it at the recovered pair, sign
the recovered charter, and commit it:

```bash
sed -e 's|^path = .*|path = "/tmp/charters/old.md"|' \
    -e 's|^definitions = .*|definitions = "/tmp/charters/old-definitions.md"|' \
    config/g0rd0n.toml > /tmp/charters/old.toml

uv run g0rd0n --config /tmp/charters/old.toml charter show      # confirm the version
# ...add the '## Signed-off-by' section naming that version...
uv run g0rd0n --config /tmp/charters/old.toml charter commit
```

Then sign `CHARTER.md` itself and commit it normally:

```bash
uv run g0rd0n charter commit
uv run g0rd0n vault rebuild
```

Order matters and nothing enforces it — see the note below.

### What it should print

Rehearsed end to end against a throwaway kernel on 2026-09-01, with scratch signatures that
were never committed:

```
committed charter-329c9f00e917 as 14 assertions     # 8 `asks` + 6 `refines`
committed charter-8fb7f2095506 as 12 assertions     # 8 `asks` + 4 `refines`
```

and the chain walks three deep from the operative question:

```
question:charter-8fb7f2095506     (4 criticisms)
question:charter-329c9f00e917     (6 criticisms)
question:agents-md-seed-framing   (the seed framing)
```

Each `refines` edge carries its criticism's full text in provenance, so "why did we stop
asking it that way" is answerable out of the kernel rather than out of a commit message.

## A known gap

`cortex.charter.commit` does **not** check that the question it supersedes is already in the
kernel. `cortex.wager.register` does exactly that check one layer down — it refuses a wager
whose parent question the kernel does not hypothesise, because stating a parent is not the
same as having one — and the asymmetry is not principled.

It is left alone for now because the fix has a bootstrap problem that deserves its own
decision: the first charter supersedes `agents-md-seed-framing`, which is prose in `AGENTS.md`
and has never been an entity in the kernel, so a strict check would refuse the first charter
in any fresh kernel. Committing the seed framing as a question first, or exempting a charter
with no predecessor, are both defensible and neither is obviously right.

Until that is decided, **the ordering above is a convention rather than an invariant**, and
this file is where it is written down.
