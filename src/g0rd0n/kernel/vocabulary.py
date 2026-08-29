"""The closed predicate vocabulary, and the kinds each predicate joins.

Twelve predicates, mirroring knk's closed command layer. Nothing outside this table is ever
committed — not "should not be", is not: `check` is the only way into the bridge's commit
path, and it works from this table alone. A thirteenth predicate is a change to this file,
which is a change a reviewer sees.

The table also fixes each edge's direction. `refutes` runs result → hypothesis and never the
other way, so the argument graph cannot quietly grow an edge that reads backwards — the
single most likely way for a graph like this to become subtly untrue while still typechecking.

Entity references carry their kind in their name (`hypothesis:h-001`), so the direction check
needs no registry and no extra round trip, and a human reading the kernel's entity log can
see what each name is without resolving anything. See `Ref`.

Deletion criterion: this module holds the wager that the argument graph has exactly the shape
AGENTS.md says it does. Delete it and `predicate_outside_the_closed_vocabulary_is_rejected`
loses its verdict, the vocabulary drifts one convenient predicate at a time, and `g0rd0n why`
starts walking edges nobody designed.
"""

from dataclasses import dataclass

#: Kinds that count as a claim, for `cites`, which AGENTS.md types as `claim → source`.
#: "Claim" is the supertype: anything assertable can carry a citation.
CLAIM_KINDS = frozenset({"claim", "question", "statement", "hypothesis", "observation", "result"})

#: The closed vocabulary: predicate → (allowed subject kinds, allowed object kinds).
#: Transcribed from AGENTS.md §Phase 2. Adding a row is a deliberate act, not a convenience.
VOCABULARY: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "asks": (frozenset({"question"}), frozenset({"statement"})),
    "refines": (frozenset({"question"}), frozenset({"question"})),
    "hypothesises": (frozenset({"question"}), frozenset({"hypothesis"})),
    "predicts": (frozenset({"hypothesis"}), frozenset({"observation"})),
    "kills": (frozenset({"hypothesis"}), frozenset({"observation"})),
    "tests": (frozenset({"experiment"}), frozenset({"hypothesis"})),
    "measures": (frozenset({"experiment"}), frozenset({"result"})),
    "corroborates": (frozenset({"result"}), frozenset({"hypothesis"})),
    "refutes": (frozenset({"result"}), frozenset({"hypothesis"})),
    "costs": (frozenset({"wager"}), frozenset({"cost"})),
    "cites": (CLAIM_KINDS, frozenset({"source"})),
    "plays": (frozenset({"run"}), frozenset({"playbook_version"})),
}

#: Every kind any predicate names, plus `source`. Used to reject a typo'd kind on the way in.
KINDS: frozenset[str] = frozenset().union(
    CLAIM_KINDS,
    *(subjects | objects for subjects, objects in VOCABULARY.values()),
)


class VocabularyError(Exception):
    """A claim used a predicate, or an edge direction, that the vocabulary does not have."""


@dataclass(frozen=True)
class Ref:
    """A reference to an entity in the kernel: a kind and a name, rendered `kind:name`.

    The kind travels with the name because the kernel stores entities as opaque strings. This
    keeps the vocabulary's direction check free — no registry, no lookup — and makes the
    kernel's entity log readable without one.
    """

    kind: str
    name: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise VocabularyError(f"not a kind this vocabulary has: {self.kind!r}")
        if not self.name or ":" in self.name:
            raise VocabularyError(f"not a usable entity name: {self.name!r}")

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"

    @classmethod
    def parse(cls, text: str) -> "Ref":
        """Rebuild a `Ref` from its rendered form."""
        kind, separator, name = text.partition(":")
        if not separator:
            raise VocabularyError(f"not a kind:name reference: {text!r}")
        return cls(kind, name)


@dataclass(frozen=True)
class Claim:
    """One edge of the argument graph, as a caller states it.

    Plain data, deliberately unvalidated on construction: the rejection has to happen at the
    bridge, where a test can watch it happen, rather than wherever a caller happened to build
    the object.
    """

    subject: Ref
    predicate: str
    object: Ref
    confidence: float


def check(claim: Claim) -> None:
    """Raise `VocabularyError` unless this claim is one the vocabulary can express."""
    allowed = VOCABULARY.get(claim.predicate)
    if allowed is None:
        raise VocabularyError(
            f"{claim.predicate!r} is not in the closed vocabulary; "
            f"it has {', '.join(sorted(VOCABULARY))}"
        )
    subjects, objects = allowed
    if claim.subject.kind not in subjects:
        raise VocabularyError(
            f"{claim.predicate} takes a subject of kind {_or(subjects)}, not {claim.subject.kind!r}"
        )
    if claim.object.kind not in objects:
        raise VocabularyError(
            f"{claim.predicate} takes an object of kind {_or(objects)}, not {claim.object.kind!r}"
        )
    if not 0.0 <= claim.confidence <= 1.0:
        raise VocabularyError(f"confidence must be in [0, 1], got {claim.confidence}")


def _or(kinds: frozenset[str]) -> str:
    return " or ".join(repr(kind) for kind in sorted(kinds))
