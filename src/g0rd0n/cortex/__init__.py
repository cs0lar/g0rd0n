"""The Cortex: question framing, the Wager, allocation, and later the meta-loop.

Four modules. `charter` is the Question Engine of AGENTS.md §Phase 5: it decides whether a
document is a well-posed version of the task, versions it by its own substance, and puts it
into the kernel as a question. `wager` is AGENTS.md §Phase 7's half of the same chain: it
decides whether a candidate is something that can be spent against, versions it the same way,
and refuses to let money move until the kernel has been told in advance how the spend could
lose. `portfolio` is the field being bet on — nine candidate families, their priors, and what
would make us stop funding each. `allocator` decides what to spend on next, and when to stop
and hand the question back to `charter`. Nothing here knows about MCP framing, and nothing
below here knows what a Charter is.

Deletion criterion: this package holds the wager that the question g0rd0n is working on is a
named, versioned, signed artifact, and that everything spent descends from it through
something that stated how it could lose. Delete it and
`charter_revision_supersedes_and_never_overwrites`,
`charter_without_a_named_fixed_resource_is_rejected`,
`wager_without_a_kill_criterion_is_rejected`,
`experiment_result_committed_before_preregistration_is_rejected`,
`allocator_prefers_the_cheaper_of_two_equally_informative_wagers` and
`exhausted_question_triggers_reformulation_not_more_spending` lose their verdicts, and
AGENTS.md §4 — no spend without a Wager, no Wager without a Question — has nothing at either
end of the chain for `g0rd0n why` to walk.
"""

from g0rd0n.cortex.allocator import (
    PATIENCE,
    AllocationError,
    Board,
    Exhausted,
    Next,
    Ranked,
    Standing,
    allocate,
    rank,
    read,
)
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
from g0rd0n.cortex.portfolio import CONTROL_ARM, FAMILIES, Family, surveys
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
    "CONTROL_ARM",
    "ELEMENTS",
    "FAMILIES",
    "GATE",
    "PATIENCE",
    "SECTIONS",
    "AllocationError",
    "Board",
    "Charter",
    "CharterError",
    "Definition",
    "Exhausted",
    "Family",
    "Next",
    "NotPreregistered",
    "Outcome",
    "Ranked",
    "Recorded",
    "Registration",
    "Standing",
    "Unfalsifiable",
    "Verdict",
    "Wager",
    "WagerError",
    "allocate",
    "check",
    "commit",
    "definitions",
    "load",
    "parse",
    "rank",
    "read",
    "record",
    "register",
    "reserve",
    "surveys",
]
