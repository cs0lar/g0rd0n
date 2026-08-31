"""The Wager: claim, test, price, kill-criterion — and the gate that refuses one without them.

AGENTS.md §Phase 7, and the one idea the whole system is built around: *everything is a
Wager*. No spend without a parent Wager, no Wager without a parent Question, no Wager without
a stated way to lose. This module is where those three sentences stop being prose.

Four mechanisms, and the module is those four:

- **The falsifiability gate is code.** AGENTS.md §Falsifiability gate lists what a candidate
  must state before any spend: the resource held fixed, the task family, the measurement
  procedure and its instrument, and the observation that would kill it, with its price. `GATE`
  is that list, transcribed, and `check` is the refusal. "No item 4, no Wager" is a raised
  exception, not a norm somebody remembers.
- **A Wager's identity is the hash of what it pre-registered**, exactly as a `Playbook`'s and
  a `Charter`'s are. This is what makes post-hoc criteria *structurally* impossible rather
  than merely forbidden: change the kill criterion and you do not have an amended wager, you
  have a different one, with a different id, that the kernel has never heard of. There is no
  edit that keeps the id.
- **No Wager without a parent Question, checked against the kernel.** `register` refuses a
  wager whose hypothesis the question does not actually hypothesise. Stating a parent is not
  the same as having one, and the difference is one lookup.
- **No spend without a registration.** `reserve` takes a `Registration`, and the only thing
  that makes one is `register`. Same trick as the Ledger's `Reservation`, one level up: the
  Ledger will price any string you hand it, and this is the function that makes the string a
  wager somebody committed to first. It reserves the *pre-registered* price and takes no
  estimate argument, because re-pricing a wager at the moment you run it is the post-hoc move
  wearing a different hat.

**What goes into the kernel, and what does not.** Registration commits three edges: the test
(`experiment tests hypothesis`), the kill criterion (`hypothesis kills observation`), and the
price (`wager costs cost`). The *estimate* is a commitment and belongs in the record; the
*actual* is the journal's business and is not committed here. The kernel holds what you said
it would cost; the ledger holds what it did. See ADR 0002.

**Two entities, one act.** A wager mints `wager:<id>` and `experiment:<id>` under the same
name. The closed vocabulary has no predicate joining them — `wager` appears only as the
subject of `costs` — so the two kinds are two faces of one thing: what it costs, and what it
does to the argument graph. The shared name is the join, and it is a convention rather than an
edge because widening the vocabulary to say something both notes already say would be a poor
trade. See ADR 0010.

Deletion criterion: this module holds the wager that every dollar traces back to a question
through something that stated in advance how it could lose. Delete it and
`wager_without_a_kill_criterion_is_rejected` and
`experiment_result_committed_before_preregistration_is_rejected` both lose their verdicts, the
`WagerId` in the ledger goes back to being a string somebody typed, and a kill criterion
becomes something you can write down after seeing the result.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from g0rd0n.cells.playbook import version_of
from g0rd0n.evidence.channel import rivals
from g0rd0n.kernel import AssertionId, Bridge, Claim, EntityId, Provenance, Ref, ToolError
from g0rd0n.ledger import ZERO, Cost, Ledger, Reservation

#: A wager's human handle: lowercase words joined by hyphens. Inside the substance, so
#: relabelling a wager produces a different wager — the label is what `g0rd0n cost --by wager`
#: prints, and a label that could be reused would make two wagers indistinguishable in the one
#: report that has to reconcile with the money.
LABEL = re.compile(r"\A[a-z0-9]+(-[a-z0-9]+)*\Z")

#: What the falsifiability gate demands, and what each field is called in the refusal.
#: Transcribed from AGENTS.md §Falsifiability gate, which lists four items — the third is
#: compound (procedure *and* instrument) and is checked as two, for the same reason the
#: Charter checks the energy metric and its instrument separately: a procedure with no named
#: instrument is a plan, and a plan does not measure anything.
GATE: dict[str, str] = {
    "claim": "the falsifiable statement",
    "resource": "the resource held fixed",
    "task_family": "the task family",
    "test": "the measurement procedure that settles it",
    "instrument": "the instrument that procedure measures with",
    "kill": "the observation that would kill it",
}

#: The fields the version hashes, in canonical order: everything a wager pre-registers. The
#: order is fixed here rather than taken from the dataclass so that reordering the fields is
#: not silently a new identity for every wager ever registered.
SUBSTANCE: tuple[str, ...] = (
    "label",
    "question",
    "hypothesis",
    "claim",
    "resource",
    "task_family",
    "test",
    "instrument",
    "kill",
    "price",
    "prior",
)


class WagerError(Exception):
    """A wager, or something done with one, is not something this system can price."""


class Unfalsifiable(WagerError):
    """A wager did not state one of the things AGENTS.md requires before any spend.

    Its own class because this is the gate, and the gate is the phase: a caller that wants to
    tell "you forgot the kill criterion" apart from "that question does not have that
    hypothesis" should not have to read an error string to do it.
    """


class NotPreregistered(WagerError):
    """A result arrived for a wager the kernel was never told about in advance."""


class Verdict(StrEnum):
    """How a wager ended. Closed, per AGENTS.md §Core Types.

    `ABANDONED` is a legitimate outcome and requires a reason. Running out of money is **not**
    on this list and never will be: `BudgetExhausted` says something about g0rd0n's budget and
    nothing whatever about the world, and recording it as a verdict would put a claim about
    the universe into the kernel on the authority of an accountant.
    """

    CORROBORATED = "corroborated"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    ABANDONED = "abandoned"


#: What each verdict says to the argument graph, or nothing. `inconclusive` and `abandoned`
#: commit a result and no edge from it: a test that settled nothing is a fact about the test,
#: and turning it into a weak `corroborates` is how a null result becomes support for whatever
#: was being tested.
ARGUES: dict[Verdict, str | None] = {
    Verdict.CORROBORATED: "corroborates",
    Verdict.REFUTED: "refutes",
    Verdict.INCONCLUSIVE: None,
    Verdict.ABANDONED: None,
}


@dataclass(frozen=True)
class Wager:
    """One thing g0rd0n might spend money to find out, and how it could lose.

    The shape is AGENTS.md §Core Types' `Wager` with the falsifiability gate's other three
    items added as fields, because a gate that reads them out of free text is a gate that
    parses prose. `id` is derived rather than declared: an id you choose is an id you can
    reuse for a different question, and pre-registration means the identity has to be a
    function of what was registered.

    `hypothesis` and `claim` are both here and both load-bearing. The `Ref` is the entity the
    argument graph already knows — put there by the Evidence Channel or the portfolio — and
    the string is the falsifiable statement this wager is actually making about it. A wager
    that carried only the ref would be "we tested h-001" with no record of what was tested.
    """

    label: str
    question: Ref
    hypothesis: Ref
    claim: str
    resource: str
    task_family: str
    test: str
    instrument: str
    kill: str
    price: Cost
    prior: float

    @property
    def substance(self) -> str:
        """The canonical rendering the version hashes: one field per line, fixed order.

        Free text is whitespace-normalised, so reflowing a paragraph is not a new wager, in
        the same way that reordering the Charter's sections is not a new question. Changing a
        word is.
        """
        return "\n".join(f"{field}: {_canonical(getattr(self, field))}" for field in SUBSTANCE)

    @property
    def version(self) -> str:
        return version_of(self.substance.encode("utf-8"))

    @property
    def id(self) -> str:
        """The `WagerId` the ledger spends against: `w-landauer-floor-3f2a1c9d4e5f`.

        Label and hash together. The hash is the identity; the label is there so that a cost
        report is readable by a human, which is the whole point of a cost report.
        """
        return f"{self.label}-{self.version}"

    @property
    def ref(self) -> Ref:
        """The priced face of the wager: what `costs` is asserted of."""
        return Ref("wager", self.id)

    @property
    def experiment(self) -> Ref:
        """The argument face: what `tests` and `measures` are asserted of."""
        return Ref("experiment", self.id)

    @property
    def killer(self) -> Ref:
        """The observation that would kill the hypothesis, as an entity, named in advance."""
        return Ref("observation", f"{self.id}-kill")

    @property
    def priced(self) -> Ref:
        """The pre-registered price, as an entity. The estimate, never the actual."""
        return Ref("cost", f"{self.id}-price")

    @property
    def result(self) -> Ref:
        """What the test will have produced, whatever the verdict turns out to be."""
        return Ref("result", f"{self.id}-result")

    @property
    def source(self) -> Ref:
        """The wager document itself, cited by every edge registration commits."""
        return Ref("source", self.id)


@dataclass(frozen=True)
class Registration:
    """Proof that a wager was pre-registered, and the token that permits spending on it.

    Holding one of these means the kernel was told the claim, the test, the price, and the
    kill criterion *before* anything ran. There is no other way to get one, so there is no
    way to spend against a wager or record a result for one without it — the same enforcement
    the Ledger uses for `Reservation`, applied one layer up.
    """

    wager: Wager
    tests: AssertionId
    kills: AssertionId
    costs: AssertionId
    document: EntityId

    @property
    def assertions(self) -> tuple[AssertionId, ...]:
        return (self.tests, self.kills, self.costs)


@dataclass(frozen=True)
class Outcome:
    """What a wager turned out to be, and what was found.

    `finding` is required for every verdict, which is how "abandoned requires a reason"
    (AGENTS.md §Core Types) is enforced without a special case: there is no verdict this
    module will record that does not say what happened.
    """

    verdict: Verdict
    finding: str


@dataclass(frozen=True)
class Recorded:
    """A settled wager: the verdict, the result entity, and what went into the kernel."""

    wager: Wager
    verdict: Verdict
    result: Ref
    assertions: tuple[AssertionId, ...]


def check(wager: Wager) -> None:
    """Run the falsifiability gate. Raises `Unfalsifiable` naming the first thing missing.

    Called by `register` before anything reaches the kernel, and callable on its own: a
    portfolio can ask whether its candidates are wagers at all without a running knk.
    """
    if not LABEL.match(wager.label):
        raise WagerError(
            f"{wager.label!r} is not a usable wager label; lowercase words joined by hyphens, "
            "because this is what a cost report prints"
        )
    if wager.question.kind != "question":
        raise WagerError(f"a wager descends from a question, not a {wager.question.kind!r}")
    if wager.hypothesis.kind != "hypothesis":
        raise WagerError(f"a wager tests a hypothesis, not a {wager.hypothesis.kind!r}")

    for field, what in GATE.items():
        if not str(getattr(wager, field)).strip():
            raise Unfalsifiable(
                f"{wager.label}: a wager must state {what} (`{field}`). AGENTS.md "
                "§Falsifiability gate: no item 4, no Wager."
            )
    if wager.price == ZERO:
        raise Unfalsifiable(
            f"{wager.label}: a wager must state the price of looking, in at least one "
            "dimension. Work that costs nothing at all is not an experiment, it is a memory."
        )
    if not 0.0 < wager.prior < 1.0:
        raise Unfalsifiable(
            f"{wager.label}: a prior of {wager.prior} is a conviction rather than a wager — "
            "no observation could move it, so nothing is worth spending to find out."
        )


def register(bridge: Bridge, wager: Wager) -> Registration:
    """Pre-register a wager: put the claim, the test, the price, and the kill into the kernel.

    This happens **before** the experiment runs, and `record` will not accept a result without
    the `Registration` it returns. Refuses three ways, in this order: a wager that does not
    pass the gate, a wager whose question does not actually hypothesise its hypothesis, and a
    wager already registered.

    The second refusal is the one that does unexpected work. "No Wager without a parent
    Question" is checked against the kernel rather than taken on the wager's word, because a
    `question` field is a string until something resolves it, and a chain `g0rd0n why` cannot
    walk is not a chain.
    """
    check(wager)
    if wager.hypothesis not in rivals(wager.question, bridge=bridge):
        raise WagerError(
            f"{wager.question} does not hypothesise {wager.hypothesis}, so this wager has no "
            "parent question. Commit the hypothesis under the question first: AGENTS.md §4, "
            "no Wager without a parent Question."
        )
    if bridge.assertions_for(wager.experiment):
        raise WagerError(
            f"{wager.id} is already registered. A wager is registered once; a different "
            "claim, test, price, or kill criterion is a different wager with a different id."
        )

    document = bridge.intern_document(wager.substance.encode("utf-8"))
    fixed = (
        f"resource held fixed: {wager.resource}; task family: {wager.task_family}; "
        f"instrument: {wager.instrument}"
    )
    # Confidence 1.0 on all three: these assert what was registered, which is a fact about the
    # registration and not a degree of belief in the hypothesis. What g0rd0n believes about
    # the world changes when a result arrives, and only Phase 10 promotes it.
    return Registration(
        wager=wager,
        tests=bridge.hypothesise(
            Claim(wager.experiment, "tests", wager.hypothesis, 1.0),
            _from(wager, document, f"pre-registered test: {wager.test}. {fixed}"),
        ),
        kills=bridge.hypothesise(
            Claim(wager.hypothesis, "kills", wager.killer, 1.0),
            _from(wager, document, f"pre-registered kill criterion: {wager.kill}"),
        ),
        costs=bridge.hypothesise(
            Claim(wager.ref, "costs", wager.priced, 1.0),
            _from(wager, document, f"pre-registered price: {_canonical(wager.price)}"),
        ),
        document=document,
    )


def reserve(ledger: Ledger, registration: Registration, agent: str) -> Reservation:
    """Set money aside for a registered wager. The only way this system spends against one.

    Takes no estimate. The reservation is the price the wager pre-registered, because
    re-pricing a wager at the moment you run it is the post-hoc move wearing a different hat:
    a budget nobody committed to in advance is one that can always be found to have been
    exactly enough.

    The Ledger will happily price any string handed to it — it has to, it is owned by no layer
    and knows nothing about Wagers — so this is where the string becomes a claim somebody
    registered first.
    """
    return ledger.reserve(registration.wager.id, registration.wager.price, agent)


def record(bridge: Bridge, registration: Registration, outcome: Outcome) -> Recorded:
    """Commit what a wager found. Refuses a result the kernel has no pre-registration for.

    Always commits `experiment measures result`, whatever the verdict: a wager that was
    abandoned or came back inconclusive still spent something and still happened, and a record
    that kept only the conclusive ones would report a success rate nobody earned.

    A `corroborates` or `refutes` edge is committed on top of that only for the two verdicts
    that argue. Both at confidence 1.0, which is a statement about the *relation* — this
    result bears on that hypothesis, in this direction — and not about how likely the
    hypothesis now is. For a refutation that number is honest in a way it rarely is elsewhere:
    the observation that would kill the claim was written down before the test ran, and it was
    observed.
    """
    wager = registration.wager
    if not outcome.finding.strip():
        raise WagerError(
            f"{wager.id}: a {outcome.verdict} verdict must say what was found. An abandoned "
            "wager needs a reason, and a settled one needs the observation it settled on."
        )
    _preregistered(bridge, registration)
    if _measured(bridge, wager):
        raise WagerError(
            f"{wager.id} has already been settled. A wager gets one verdict; a second look "
            "is a second wager, priced and registered like the first."
        )

    verdict = outcome.verdict
    committed = [
        bridge.hypothesise(
            Claim(wager.experiment, "measures", wager.result, 1.0),
            _from(wager, registration.document, f"{verdict}: {outcome.finding}"),
        )
    ]
    argues = ARGUES[verdict]
    if argues is not None:
        against = wager.kill if verdict is Verdict.REFUTED else wager.test
        committed.append(
            bridge.hypothesise(
                Claim(wager.result, argues, wager.hypothesis, 1.0),
                _from(
                    wager,
                    registration.document,
                    f"{outcome.finding}, against the pre-registered "
                    f"{'kill criterion' if verdict is Verdict.REFUTED else 'test'}: {against}",
                ),
            )
        )
    return Recorded(wager=wager, verdict=verdict, result=wager.result, assertions=tuple(committed))


def _preregistered(bridge: Bridge, registration: Registration) -> None:
    """Check the token names an assertion the kernel actually holds, about this experiment.

    The type already says a caller holds a `Registration`, and a caller who built one by hand
    holds a token nobody minted. One lookup turns that into a refusal rather than a result
    filed under a pre-registration that never happened.
    """
    wager = registration.wager
    try:
        assertion = bridge.get(registration.tests)
    except ToolError as exc:
        raise NotPreregistered(
            f"{wager.id} names assertion {registration.tests}, which the kernel does not have"
        ) from exc
    if bridge.name_of(assertion.subject) != wager.experiment:
        raise NotPreregistered(
            f"assertion {registration.tests} is not the pre-registration of {wager.id}; a "
            "result may only be recorded against the wager that was registered before it ran"
        )


def _measured(bridge: Bridge, wager: Wager) -> bool:
    """Has this wager already produced a result?"""
    return any(
        bridge.predicate_of(assertion.predicate) == "measures"
        for assertion in bridge.assertions_for(wager.experiment)
    )


def _from(wager: Wager, document: EntityId, method: str) -> Provenance:
    """Provenance for an edge this module commits: the wager itself, and what it said.

    The wager's canonical substance is interned once per registration and cited from every
    edge, so "what exactly was registered" is answerable from the kernel rather than from
    whichever copy of the source happened to be checked out. Documents are cited, never
    asserted about (ADR 0003).
    """
    return Provenance(wager.source, f"{method}; knk document {document}")


def _canonical(value: object) -> str:
    """One field of the substance, rendered so that only a real change changes the hash."""
    if isinstance(value, Cost):
        return json.dumps(value.as_dict(), sort_keys=True)
    if isinstance(value, float):
        return repr(value)
    return " ".join(str(value).split())
