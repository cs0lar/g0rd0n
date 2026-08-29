"""The bridge: the only way a claim gets into the kernel, and the only place one is refused.

Two rules are enforced here and nowhere else, because a rule enforced in two places is a rule
that will eventually be enforced in one:

- **Provenance or it didn't happen.** Every claim names a resolvable source entity and the
  method that extracted it. There is no exemption for well-known facts, and no default. The
  kernel's own `commit_hypothesis` demands a source too, but it will accept an empty method
  string; the bridge will not.
- **Machine-suggested claims land as `Hypothesis`.** `commit_hypothesis` is the only write
  path this module has. There is no way to commit an `Active` assertion through it, because
  promotion needs three keys and Phase 10's referee holds them. A `commit` method here would
  be a hole with a comment next to it.

`find_conflicts` is offered and never acted on. Conflicting claims are surfaced to a human or
to the referee; averaging them, preferring the newer one, or dropping the older one are all
ways of destroying the most interesting thing in the record.

This module does not know what a Wager is. It moves claims, provenance, and assertions.

Deletion criterion: this module holds the wager that no belief enters g0rd0n's memory without
a source and a status. Delete it and `unsourced_claim_is_rejected_at_the_bridge` and
`machine_suggested_claims_land_as_hypothesis_status` both lose their verdicts, and the
kernel's log stops being evidence and becomes a pile of assertions of unknown origin.
"""

import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from g0rd0n.config import Config
from g0rd0n.kernel import mcp
from g0rd0n.kernel.mcp import Client, KernelError, ToolError
from g0rd0n.kernel.vocabulary import Claim, Ref, check

AssertionId = int
EntityId = int

#: knk's open-ended valid_to.
OPEN_ENDED = 0


class ProvenanceError(KernelError):
    """A claim arrived without a resolvable source, or without saying how it was extracted."""


@dataclass(frozen=True)
class Provenance:
    """Where a claim came from, and how it was got out of there.

    `method` is free text and is meant to be specific enough to repeat: "abstract, regex on
    'we show that'" is provenance, "LLM" is not.
    """

    source: Ref
    method: str


@dataclass(frozen=True)
class Assertion:
    """One assertion as the kernel returns it. Ids, not names: resolution is a separate step."""

    id: AssertionId
    subject: EntityId
    predicate: int
    object: EntityId
    status: str
    confidence: float
    valid_from: int
    valid_to: int
    observed_at: int
    supersedes_id: int
    retracts_id: int

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Assertion":
        return cls(
            id=int(raw["id"]),
            subject=int(raw["subject"]),
            predicate=int(raw["predicate"]),
            object=int(raw["object"]),
            status=str(raw["status"]),
            confidence=float(raw["confidence"]),
            valid_from=int(raw["valid_from"]),
            valid_to=int(raw["valid_to"]),
            observed_at=int(raw["observed_at"]),
            supersedes_id=int(raw.get("supersedes_id", 0)),
            retracts_id=int(raw.get("retracts_id", 0)),
        )


class Bridge:
    """g0rd0n's side of the kernel boundary. One write path, several read paths."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def hypothesise(self, claim: Claim, provenance: Provenance) -> AssertionId:
        """Commit a machine-suggested claim, as `Hypothesis`, with its provenance attached.

        The only write path. Rejects, before anything reaches the kernel, a claim the closed
        vocabulary cannot express and a provenance that names no source or no method.
        """
        check(claim)
        _check_provenance(provenance)

        at = now()
        assertion_id = int(
            self._client.call(
                "commit_hypothesis",
                {
                    "subject": self.intern(claim.subject),
                    "predicate": self._intern_predicate(claim.predicate),
                    "object": self.intern(claim.object),
                    "valid_from": at,
                    "valid_to": OPEN_ENDED,
                    "observed_at": at,
                    "confidence": claim.confidence,
                    "source": self.intern(provenance.source),
                    "recorded_at": at,
                    "method": provenance.method,
                },
            )
        )
        return assertion_id

    def intern(self, ref: Ref) -> EntityId:
        """Get the kernel's id for an entity, creating it if this is the first mention."""
        return int(self._client.call("intern_entity", {"name": str(ref)}))

    def intern_document(self, content: bytes) -> EntityId:
        """Store raw bytes — a fetched paper, a transcript — and get an entity to cite."""
        encoded = base64.b64encode(content).decode("ascii")
        return int(self._client.call("intern_document", {"content": encoded}))

    def name_of(self, entity_id: EntityId) -> Ref:
        """Resolve an entity id back to its `kind:name`. The inverse of `intern`.

        Assertions come back carrying ids, so anything that renders them — the vault, and
        Phase 11's cockpit after it — needs this to say what an assertion is *about*.
        """
        return Ref.parse(str(json.loads(self._client.call("entity_name", {"id": entity_id}))))

    def predicate_of(self, predicate_id: int) -> str:
        """Resolve a predicate id back to its name. The inverse of `_intern_predicate`."""
        return str(json.loads(self._client.call("predicate_name", {"id": predicate_id})))

    def get(self, assertion_id: AssertionId) -> Assertion:
        """Fetch one assertion by id.

        knk answers a missing id with a JSON `null` rather than an error. An assertion that
        is not there is turned into a raised `ToolError` here, because a caller that gets
        `None` back will eventually forget to check for it.
        """
        raw = json.loads(self._client.call("get", {"id": assertion_id}))
        if raw is None:
            raise ToolError(f"get: no assertion {assertion_id}")
        return Assertion.from_json(raw)

    def current(self, subject: Ref) -> list[Assertion]:
        """Every currently *active*, open-ended assertion about a subject.

        Empty for everything g0rd0n commits today: the bridge only writes hypotheses, and
        nothing is promoted to `Active` until Phase 10's referee. Use `hypotheses`.
        """
        return _assertions(self._client.call("current_by_name", {"subject_name": str(subject)}))

    def hypotheses(self, subject: Ref) -> list[Assertion]:
        """Every open, `Hypothesis`-status claim about a subject. The read path that matters now."""
        return _assertions(self._client.call("hypotheses_for", {"subject": self.intern(subject)}))

    def assertions_for(self, subject: Ref) -> list[Assertion]:
        """Everything ever recorded about a subject, any status, in commit order.

        The append-only view: a refuted or superseded claim is still here, which is the point.
        """
        return _assertions(
            self._client.call("assertions_for_subject", {"subject": self.intern(subject)})
        )

    def conflicts(self, subject: Ref, predicate: str) -> list[Assertion]:
        """Overlapping assertions for a subject and predicate with different objects.

        Surfaced, never resolved. Averaging two disagreeing sources, preferring the newer, or
        dropping the older all destroy the most interesting thing in the record.

        A faithful pass-through to knk's `find_conflicts`, which considers **`Active`
        assertions only**. Since every claim g0rd0n writes is a `Hypothesis`, this returns
        nothing until Phase 10 promotes something, and that is by design rather than a gap:
        rival hypotheses are not a conflict, they are the ordinary state of an open question.
        A conflict is two things *believed* that cannot both be true, so Phase 10 is this
        method's first real caller. See AGENTS.md §Phase 2 and ADR 0003.
        """
        return _assertions(
            self._client.call(
                "find_conflicts",
                {
                    "subject": self.intern(subject),
                    "predicate": self._intern_predicate(predicate),
                },
            )
        )

    def explain(self, assertion_id: AssertionId) -> list[Assertion]:
        """Walk an assertion's supersession and retraction chain back to its root."""
        return _assertions(self._client.call("explain", {"id": assertion_id}))

    def provenance_for(self, assertion_id: AssertionId) -> Provenance | None:
        """What was recorded about where an assertion came from, if anything was."""
        record = json.loads(self._client.call("provenance_for", {"assertion_id": assertion_id}))
        if not record:
            return None
        name = json.loads(self._client.call("entity_name", {"id": int(record["source"])}))
        return Provenance(source=Ref.parse(str(name)), method=str(record["method"]))

    def changes_since(self, observed_since: int, limit: int = 0) -> list[Assertion]:
        """Everything the kernel learned at or after a cutoff. Phase 11's `diff` reads this."""
        return _assertions(
            self._client.call("changes_since", {"observed_since": observed_since, "limit": limit})
        )

    def _intern_predicate(self, predicate: str) -> int:
        return int(self._client.call("intern_predicate", {"name": predicate}))


def now() -> int:
    """The kernel's clock: Unix seconds, UTC.

    The ledger has its own. The two are deliberately not shared: the Ledger cuts across every
    layer and is owned by none, so a kernel that imported it would invert the layering to save
    two lines.
    """
    return int(datetime.now(UTC).timestamp())


@contextmanager
def connect(config: Config) -> Iterator[Bridge]:
    """Open a bridge to the kernel named in the config, and close the subprocess after."""
    with mcp.connect(config.kernel_mcp_server, config.kernel_storage_root) as client:
        yield Bridge(client)


def _check_provenance(provenance: Provenance) -> None:
    if provenance.source.kind != "source":
        raise ProvenanceError(
            f"provenance must name a source entity, not a {provenance.source.kind!r}"
        )
    if not provenance.method.strip():
        raise ProvenanceError(
            "provenance must say how the claim was extracted; there is no exemption for "
            "well-known facts"
        )


def _assertions(payload: str) -> list[Assertion]:
    raw = json.loads(payload)
    return [Assertion.from_json(item) for item in raw]
