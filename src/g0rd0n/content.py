"""Content addressing: the version of a thing is the hash of what the thing is.

One function, and it is here rather than in `cells/playbook.py` because it now has callers in
four layers. A `Playbook`, a `HumanQuery`, a `Charter`, a `Wager` and a task family are all
versioned the same way, for the same reason: a version number somebody remembers to bump can
be stale, and a stale version attributes a result to text that never produced it. There is no
test that could catch that — the record would be internally consistent and wrong.

It moved in Phase 8 because `instruments/` must not import `cells/`: the layering runs Cortex
above Cells above Instruments, and an instrument reaching upwards for a hash function would
invert it for the sake of two lines. The alternative was a second hash rule beside the first,
which The Imperative (1) forbids — one primitive, and no second way to express something
already expressed.

Depends on nothing, in `g0rd0n` or out of it beyond `hashlib`, so every layer can reach it.

Deletion criterion: this module holds the wager that anything a result can be attributed to
can be named by its content. Delete it and `a_playbooks_version_is_the_hash_of_its_bytes`,
`the_version_does_not_depend_on_the_order_of_the_sections` and
`a_task_familys_version_covers_the_source_of_its_checker` lose the one mechanism they share,
and "which exact text produced this?" stops having a single answer.
"""

import hashlib

#: How much of the digest goes into a version. Twelve hex characters is 48 bits, far past
#: collision risk for a repository of prompts, charters, wagers and task families, and short
#: enough to read aloud.
DIGEST_LENGTH = 12


def version_of(content: bytes) -> str:
    """The version of something: the hash of the exact bytes that make it what it is.

    Whitespace and comments are inside the hash wherever the bytes are what is being
    versioned, because whitespace changes prompts and a comment changes what a checker means
    to the person maintaining it. Callers that want a looser identity — a charter whose
    sections may be reordered, a wager whose prose may be reflowed — canonicalise first and
    hash the canonical form, which is a decision each of them states.
    """
    return hashlib.sha256(content).hexdigest()[:DIGEST_LENGTH]
