"""The Cortex: question framing, and later allocation and the meta-loop.

One module so far. `charter` is the Question Engine of AGENTS.md §Phase 5: it decides whether
a document is a well-posed version of the task, versions it by its own substance, and puts it
into the kernel as a question that later Wagers descend from. Phase 7 adds the Wager and the
allocator beside it; nothing here knows about MCP framing, and nothing below here knows what
a Charter is.

Deletion criterion: this package holds the wager that the question g0rd0n is working on is a
named, versioned, signed artifact rather than a paragraph in a README. Delete it and all three
Phase 5 minimum tests lose their verdicts, and AGENTS.md §4 — no spend without a Wager, no
Wager without a Question — has nothing at the top of the chain for `g0rd0n why` to walk to.
"""

from g0rd0n.cortex.charter import (
    ELEMENTS,
    SECTIONS,
    Charter,
    CharterError,
    Definition,
    commit,
    definitions,
    load,
    parse,
)

__all__ = [
    "ELEMENTS",
    "SECTIONS",
    "Charter",
    "CharterError",
    "Definition",
    "commit",
    "definitions",
    "load",
    "parse",
]
