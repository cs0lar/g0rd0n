"""The Cortex: question framing, the Wager, and later allocation and the meta-loop.

Two modules. `charter` is the Question Engine of AGENTS.md §Phase 5: it decides whether a
document is a well-posed version of the task, versions it by its own substance, and puts it
into the kernel as a question. `wager` is AGENTS.md §Phase 7's half of the same chain: it
decides whether a candidate is something that can be spent against, versions it the same way,
and refuses to let money move until the kernel has been told in advance how the spend could
lose. Nothing here knows about MCP framing, and nothing below here knows what a Charter is.

Deletion criterion: this package holds the wager that the question g0rd0n is working on is a
named, versioned, signed artifact, and that everything spent descends from it through
something that stated how it could lose. Delete it and
`charter_revision_supersedes_and_never_overwrites`,
`charter_without_a_named_fixed_resource_is_rejected`,
`wager_without_a_kill_criterion_is_rejected` and
`experiment_result_committed_before_preregistration_is_rejected` lose their verdicts, and
AGENTS.md §4 — no spend without a Wager, no Wager without a Question — has nothing at either
end of the chain for `g0rd0n why` to walk.
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
from g0rd0n.cortex.wager import (
    GATE,
    NotPreregistered,
    Outcome,
    Recorded,
    Registration,
    Unfalsifiable,
    Verdict,
    Wager,
    WagerError,
    check,
    record,
    register,
    reserve,
)

__all__ = [
    "ELEMENTS",
    "GATE",
    "SECTIONS",
    "Charter",
    "CharterError",
    "Definition",
    "NotPreregistered",
    "Outcome",
    "Recorded",
    "Registration",
    "Unfalsifiable",
    "Verdict",
    "Wager",
    "WagerError",
    "check",
    "commit",
    "definitions",
    "load",
    "parse",
    "record",
    "register",
    "reserve",
]
