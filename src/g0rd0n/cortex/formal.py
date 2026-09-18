"""The Formal Cell: a separation claim, the complexity bookkeeping it carries, and its stage.

AGENTS.md §Phase 9: "the ability to make a separation claim precisely, and to know when one
has not been made." `CHARTER.md` §Separation shape is why this matters less than it sounds and
more than it looks. The Charter chose S4 and not S1, because S1 separations "are contingent on
open problems (`TC⁰ ≠ NC¹` and friends)" and a question that can only be settled by resolving
an open problem is one this instrument cannot spend against — but it admits S1 results as
evidence, "recorded with its contingent assumptions attached, permanently". This module is that
recording, and the three things it will not let a claim do.

**A claim cannot shed a contingency.** A `Separation`'s identity is the hash of everything it
states — the family, the classes, the uniformity, what is pinned, and what it is contingent
on — exactly as a `Wager`'s is. There is no edit that drops `TC⁰ ≠ NC¹` and keeps the id, and
no stage transition that clears it: a machine-checked conditional result is still conditional,
and the only way to stop being contingent is to be a different claim. Every edge this module
commits repeats the contingency in its provenance, so a reader who meets the claim from any
direction meets the label with it. That is "labelled as contingent, forever".

**A claim cannot skip a stage, and the stage is part of the assertion.** `conjecture` →
`proof sketch` → `machine-checked`, in that order, each reached by committing the edge that
*is* that stage — `hypothesises` for a conjecture, `cites` a sketch document for a sketch,
`corroborates` from a checker's result for a machine-checked one — with the stage named at the
head of its provenance. `stage_of` reads it back from the kernel alone, so the stage is a fact
about the record rather than a field somebody set; retracting the sketch's edge steps the claim
back to a conjecture with no special case. The ordering is enforced because a sketch is where
the formal statement is pinned in front of a human reader: a proof of a formal statement is
only a proof of the claim if somebody could see that the two say the same thing.

**A claim cannot be called a theorem until it is one.** `describe` is the only wording there
is, and it says "theorem" for exactly one case — machine-checked *and* unconditional. A sketch
is an argument; a machine-checked contingent result is a conditional one; and a conjecture has
no proof at all. None of these stages is belief, either: every edge lands as a `Hypothesis`,
and promotion is Phase 10's referee, because a checker that proved the wrong formal statement
perfectly is exactly the failure a referee exists for.

Deletion criterion: this module holds the wager that an S1 claim cannot be reported as more
than it is. Delete it and `separation_claim_records_its_contingent_assumptions`,
`proof_sketch_is_never_reported_as_a_theorem` and `a_proof_that_assumes_what_the_claim_did_
not_declare_is_refused` lose their verdicts, and a conditional lower bound goes back to being
a sentence in which the word "unless" was easy to drop.
"""

from dataclasses import dataclass
from enum import StrEnum

from g0rd0n.content import version_of
from g0rd0n.cortex.wager import LABEL
from g0rd0n.evidence.channel import DEAD, sources_for
from g0rd0n.instruments.prover import Checked, ProverError, unadmitted
from g0rd0n.instruments.tasks import FAMILIES
from g0rd0n.kernel import AssertionId, Bridge, Claim, Provenance, Ref


class FormalError(Exception):
    """A formal claim, or something done with one, would report more than was shown."""


class Stage(StrEnum):
    """How far a claim's argument has got. Closed, ordered, and never belief."""

    CONJECTURE = "conjecture"
    SKETCH = "proof sketch"
    CHECKED = "machine-checked"


#: The order a claim moves through, one step at a time. A tuple rather than enum order so the
#: rule is a line to read rather than an implementation detail of `StrEnum`.
ORDER: tuple[Stage, ...] = (Stage.CONJECTURE, Stage.SKETCH, Stage.CHECKED)


class Pinned(StrEnum):
    """What an S1 claim holds fixed. AGENTS.md §The Question: "Any S1 claim must state which
    of depth, precision, steps, or parameters is pinned." Transcribed, and closed."""

    DEPTH = "depth"
    PRECISION = "precision"
    STEPS = "steps"
    PARAMETERS = "parameters"


#: The open separations a claim may be contingent on, by the name a formal proof would give
#: the axiom that assumes it. Closed, like the predicate vocabulary: two claims contingent on
#: one open problem should say so in one spelling, or "which of our results fall if this is
#: settled" has no answer. Adding a row is adding an open problem to what g0rd0n admits it
#: depends on, and a reviewer should see it happen.
OPEN: dict[str, str] = {
    "tc0_ne_nc1": (
        "TC⁰ ≠ NC¹, both DLOGTIME-uniform: some language decided by logarithmic-depth, "
        "bounded-fan-in circuits is not decided by constant-depth threshold circuits. Open."
    ),
    "nc1_not_in_l_uniform_tc0": (
        "NC¹ ⊄ logspace-uniform TC⁰. Implies `tc0_ne_nc1`, because logspace-uniform TC⁰ "
        "contains the DLOGTIME-uniform class; the converse is not known, so a claim that needs "
        "this and says `tc0_ne_nc1` has understated what it assumes. Open."
    ),
}


@dataclass(frozen=True)
class Separation:
    """An S1 claim, with the bookkeeping AGENTS.md §Phase 9 says every one must carry.

    `classes` records the class the resource-pinned model sits in and the class the task is
    hard for; `uniformity` is the uniformity condition the argument works at, stated
    separately because it is the part most easily left implicit and most often wrong;
    `contingent_on` names, from `OPEN`, every unproven separation the claim needs. An empty
    tuple is a claim to be unconditional, and it is rendered as one, loudly.

    `prior` is inside the identity for the reason a `Wager`'s is: changing what you believe
    about a claim before anyone has tested it is registering a different claim.
    """

    label: str
    family: str
    statement: str
    classes: str
    uniformity: str
    pinned: tuple[Pinned, ...]
    contingent_on: tuple[str, ...]
    prior: float

    def __post_init__(self) -> None:
        if not LABEL.match(self.label):
            raise FormalError(
                f"{self.label!r} is not a usable label; lowercase words joined by hyphens"
            )
        chartered = {family.slug for family in FAMILIES}
        if self.family not in chartered:
            raise FormalError(
                f"{self.family!r} is not a chartered task family ({', '.join(sorted(chartered))}). "
                "A separation on a family nobody chartered is about a task nobody pre-registered."
            )
        for field in ("statement", "classes", "uniformity"):
            if not str(getattr(self, field)).strip():
                raise FormalError(
                    f"{self.label}: an S1 claim must state its {field}. AGENTS.md §Phase 9: "
                    "every S1 claim records the class, the uniformity assumption, and the "
                    "unproven separations it is contingent on."
                )
        if not self.pinned:
            raise FormalError(
                f"{self.label}: an S1 claim must say which of depth, precision, steps or "
                "parameters is pinned. A separation with nothing held fixed is a claim about "
                "two Turing-complete systems, and those do not separate."
            )
        if len(set(self.pinned)) != len(self.pinned):
            raise FormalError(f"{self.label}: a resource is pinned twice")
        unknown = [name for name in self.contingent_on if name not in OPEN]
        if unknown:
            raise FormalError(
                f"{self.label}: contingent on {', '.join(unknown)}, which is not an open "
                f"problem this system has a name for ({', '.join(sorted(OPEN))}). Add it to "
                "`OPEN` first, so every claim that depends on it says so in the same words."
            )
        if len(set(self.contingent_on)) != len(self.contingent_on):
            raise FormalError(f"{self.label}: a contingency is listed twice")
        if not 0.0 < self.prior < 1.0:
            raise FormalError(
                f"{self.label}: a prior of {self.prior} is a conviction, not a conjecture"
            )

    @property
    def contingent(self) -> bool:
        return bool(self.contingent_on)

    @property
    def label_of_contingency(self) -> str:
        """The phrase every edge about this claim carries. The same for all three stages."""
        if not self.contingent:
            return "UNCONDITIONAL: contingent on no open problem"
        return "CONTINGENT on " + "; ".join(f"{name} ({OPEN[name]})" for name in self.contingent_on)

    @property
    def substance(self) -> str:
        """The canonical text the identity hashes. Free text is whitespace-normalised."""
        return "\n".join(
            (
                f"label: {self.label}",
                f"family: {self.family}",
                f"statement: {_flat(self.statement)}",
                f"classes: {_flat(self.classes)}",
                f"uniformity: {_flat(self.uniformity)}",
                f"pinned: {', '.join(sorted(self.pinned))}",
                f"contingent_on: {', '.join(sorted(self.contingent_on))}",
                f"prior: {self.prior!r}",
            )
        )

    @property
    def version(self) -> str:
        return version_of(self.substance.encode("utf-8"))

    @property
    def id(self) -> str:
        return f"{self.label}-{self.version}"

    @property
    def ref(self) -> Ref:
        """The claim as the argument graph holds it: a hypothesis, at every stage."""
        return Ref("hypothesis", self.id)

    @property
    def source(self) -> Ref:
        """The claim document itself, which a conjecture is sourced to: whoever conjectured it."""
        return Ref("source", self.id)

    @property
    def bookkeeping(self) -> str:
        """Everything AGENTS.md asks an S1 claim to record, as one line of provenance."""
        return "; ".join(
            (
                f"family {self.family}",
                f"classes: {_flat(self.classes)}",
                f"uniformity: {_flat(self.uniformity)}",
                f"pinned: {', '.join(self.pinned)}",
                self.label_of_contingency,
            )
        )


@dataclass(frozen=True)
class Sketch:
    """An argument for a claim, and the formal statement the claim is taken to mean.

    `formal` is the part that makes a sketch a stage rather than a note. It fixes, in front of
    a human reader, which formal statement a machine-checked proof would have to prove; the
    checker's artifact is later compared against it, and a proof of anything else does not
    advance the claim. The correspondence between the prose claim and the formal statement is
    the one thing no checker can check, so it is written down here, where it can be argued with.
    """

    argument: str
    formal: str

    def __post_init__(self) -> None:
        if not self.argument.strip():
            raise FormalError("a proof sketch with no argument in it is a conjecture")
        if not self.formal.strip():
            raise FormalError(
                "a proof sketch must state the formal statement the claim means; without one "
                "there is nothing a checker could be asked to prove"
            )

    @property
    def version(self) -> str:
        return version_of(f"formal: {_flat(self.formal)}\n\n{self.argument}".encode())

    def source(self, claim: Separation) -> Ref:
        return Ref("source", f"{claim.id}-sketch-{self.version}")


def describe(claim: Separation, stage: Stage | None) -> str:
    """The only wording there is for how far a claim has got. "Theorem" exactly once.

    Machine-checked and unconditional is a theorem. Machine-checked and contingent is a
    conditional result, and it says what it is conditional on, because "machine-checked" on
    its own reads as "true" and a conditional result is true only if an open problem goes the
    way the claim needs it to. A sketch is an argument. A conjecture has no proof at all.
    """
    if stage is None:
        return "not in the kernel"
    if stage is Stage.CONJECTURE:
        return "conjecture — no proof held"
    if stage is Stage.SKETCH:
        return "proof sketch — an argument, not machine-checked"
    if claim.contingent:
        return (
            "machine-checked conditional result — holds only if "
            f"{', '.join(claim.contingent_on)}; not a separation while "
            f"{'it is' if len(claim.contingent_on) == 1 else 'they are'} open"
        )
    return "machine-checked theorem"


def render(claim: Separation, stage: Stage | None) -> str:
    """A claim as a person should first meet it: its stage on the first line, its
    contingency on every screen it appears on, and its kernel status spelled out."""
    return "\n".join(
        (
            f"{claim.id}  [{describe(claim, stage)}]",
            f"  statement    {_flat(claim.statement)}",
            f"  family       {claim.family}",
            f"  classes      {_flat(claim.classes)}",
            f"  uniformity   {_flat(claim.uniformity)}",
            f"  pinned       {', '.join(claim.pinned)}",
            f"  contingency  {claim.label_of_contingency}",
            f"  prior        {claim.prior:g}",
            "  kernel       Hypothesis — a proof stage is not belief; promotion is Phase 10's",
        )
    )


# --- the three stages, committed ---------------------------------------------------------


def conjecture(bridge: Bridge, claim: Separation, question: Ref) -> AssertionId | None:
    """Put a claim under a question as a conjecture. Idempotent: `None` if it is already there.

    Refuses a question the kernel has never heard of, for the reason `wager.register` does:
    stating a parent is not the same as having one, and a claim hung off an uncommitted
    question creates the question by side effect.
    """
    if question.kind != "question":
        raise FormalError(f"a claim is conjectured under a question, not a {question.kind!r}")
    if not bridge.assertions_for(question):
        raise FormalError(
            f"{question} is not in the kernel. Commit the Charter first; a conjecture under a "
            "question nobody committed is a claim nobody asked for."
        )
    if stage_of(bridge, claim) is not None:
        return None
    document = bridge.intern_document(claim.substance.encode("utf-8"))
    return bridge.hypothesise(
        Claim(question, "hypothesises", claim.ref, claim.prior),
        Provenance(
            claim.source,
            f"{Stage.CONJECTURE}: {_flat(claim.statement)}; {claim.bookkeeping}; "
            f"knk document {document}",
        ),
    )


def sketch(bridge: Bridge, claim: Separation, argument: Sketch) -> AssertionId:
    """Advance a conjecture to a proof sketch, by citing the argument as a document.

    A conjecture only. A claim that is not in the kernel has nothing to sketch; one that is
    already sketched keeps the sketch it has, and a better argument arrives by retracting the
    old one first, which leaves both in the record.
    """
    _requires(bridge, claim, Stage.CONJECTURE, Stage.SKETCH)
    document = bridge.intern_document(f"formal: {argument.formal}\n\n{argument.argument}".encode())
    cited = argument.source(claim)
    return bridge.hypothesise(
        Claim(claim.ref, "cites", cited, 1.0),
        Provenance(
            cited,
            f"{Stage.SKETCH} (not machine-checked) of {claim.id}; formal statement: "
            f"{_flat(argument.formal)}; {claim.label_of_contingency}; knk document {document}",
        ),
    )


def checked(bridge: Bridge, claim: Separation, argument: Sketch, artifact: Checked) -> AssertionId:
    """Advance a sketched claim to machine-checked, on a checker's artifact and nothing else.

    Four refusals, and each is a way "machine-checked" could otherwise stop meaning anything:

    - the claim must be at `proof sketch`, and `argument` must be the sketch the kernel holds
      for it — a proof is a proof *of what a sketch pinned*, and a sketch nobody committed pins
      nothing;
    - the checker must have proved exactly the formal statement that sketch committed to, not
      a theorem with the same name and a friendlier type;
    - the proof must have no hole in it (`sorry`, to Lean); and
    - every assumption the proof made beyond the checker's own foundations must be one the
      claim declared as a contingency. A proof that silently assumes an open problem the claim
      never admitted to is the overclaim this phase exists to catch, and the checker's axiom
      report is the one place it can be caught mechanically.

    The edge is `result corroborates hypothesis` at confidence 1.0, which — as in
    `wager.record` — describes the relation and not a degree of belief. It lands as a
    `Hypothesis` like everything else: a checker that proved the wrong formal statement
    perfectly is a referee's problem, and the referee is Phase 10.
    """
    _requires(bridge, claim, Stage.SKETCH, Stage.CHECKED)
    if not sources_for(Claim(claim.ref, "cites", argument.source(claim), 1.0), bridge=bridge):
        raise FormalError(
            f"{argument.source(claim)} is not a live sketch of {claim.id}. A checked proof "
            "advances the claim only against the sketch that pinned its formal statement."
        )
    if _flat(artifact.statement) != _flat(argument.formal):
        raise FormalError(
            f"{artifact.checker} checked {artifact.theorem} : {_flat(artifact.statement)}, and "
            f"the sketch pinned {_flat(argument.formal)}. A proof of a different statement is "
            "not a proof of this claim, however close the two look."
        )
    try:
        undeclared = unadmitted(artifact, claim.contingent_on)
    except ProverError as exc:
        raise FormalError(str(exc)) from exc
    if undeclared:
        raise FormalError(
            f"{artifact.theorem} assumes {', '.join(undeclared)}, and {claim.id} declares "
            f"{', '.join(claim.contingent_on) or 'no contingencies'}. A proof contingent on "
            "something the claim never admitted is a stronger claim than the one being made — "
            "register the claim with that contingency, or prove it without the assumption."
        )

    unused = [name for name in claim.contingent_on if name not in artifact.assumptions]
    document = bridge.intern_document(artifact.proof)
    result = Ref("result", f"{claim.id}-checked-{artifact.digest}")
    return bridge.hypothesise(
        Claim(result, "corroborates", claim.ref, 1.0),
        Provenance(
            Ref("source", result.name),
            "; ".join(
                (
                    f"{Stage.CHECKED} by {artifact.checker} {artifact.version}",
                    f"declaration {artifact.theorem} : {_flat(artifact.statement)}",
                    f"proof {artifact.proof_version}",
                    f"axioms: {', '.join(sorted(artifact.axioms)) or 'none'}",
                    f"assumed: {', '.join(artifact.assumptions) or 'nothing beyond the checker'}",
                    f"declared but not used: {', '.join(unused) or 'none'}",
                    claim.label_of_contingency,
                    f"knk document {document}",
                )
            ),
        ),
    )


def stage_of(bridge: Bridge, claim: Separation) -> Stage | None:
    """How far a claim has got, read from the kernel alone. `None` if it is not there.

    The highest stage with a live edge behind it, provided the conjecture itself is still
    live: a claim whose `hypothesises` edge was retracted has been withdrawn, whatever else
    was once said about it. Reads the whole log, as `allocator.read` does, because two of the
    three edges point *at* the claim and knk answers by subject.
    """
    names: dict[int, Ref] = {}
    predicates: dict[int, str] = {}

    def name(entity_id: int) -> Ref:
        if entity_id not in names:
            names[entity_id] = bridge.name_of(entity_id)
        return names[entity_id]

    reached: set[Stage] = set()
    sketched = f"{claim.id}-sketch-"
    proved = f"{claim.id}-checked-"
    for assertion in bridge.changes_since(0):
        if assertion.status in DEAD:
            continue
        if assertion.predicate not in predicates:
            predicates[assertion.predicate] = bridge.predicate_of(assertion.predicate)
        edge = predicates[assertion.predicate]
        if edge not in {"hypothesises", "cites", "corroborates"}:
            continue
        subject, obj = name(assertion.subject), name(assertion.object)
        if edge == "hypothesises" and obj == claim.ref:
            reached.add(Stage.CONJECTURE)
        elif edge == "cites" and subject == claim.ref and obj.name.startswith(sketched):
            reached.add(Stage.SKETCH)
        elif edge == "corroborates" and obj == claim.ref and subject.name.startswith(proved):
            reached.add(Stage.CHECKED)

    if Stage.CONJECTURE not in reached:
        return None
    return max(reached, key=ORDER.index)


def _requires(bridge: Bridge, claim: Separation, stage: Stage, becoming: Stage) -> None:
    """Refuse a transition from anywhere but the stage immediately before it."""
    now = stage_of(bridge, claim)
    if now is not stage:
        raise FormalError(
            f"{claim.id} is {'not in the kernel' if now is None else f'at {now}'}, and "
            f"{becoming} follows {stage}. Stages are reached in order and never skipped: "
            f"{' → '.join(ORDER)}."
        )


def _flat(text: str) -> str:
    return " ".join(text.split())


# --- the one claim this repository ships ------------------------------------------------

#: T1's S1 claim, at the only stage g0rd0n can honestly give it today.
#:
#: CHARTER.md §Task families charters T1 "because the control arm's believed limitation is
#: depth", and this is that belief as a claim precise enough to be wrong. Three things about it
#: are deliberate:
#:
#: - **The contingency is `nc1_not_in_l_uniform_tc0`, not `tc0_ne_nc1`.** The upper bound on
#:   the transformer in the kernel is *logspace*-uniform — the seed audit's correction to
#:   AGENTS.md's unqualified "uniform" (docs/seed-audit.md) — so the separation the argument
#:   needs is from logspace-uniform TC⁰, which is the stronger assumption. Writing the familiar
#:   `TC⁰ ≠ NC¹` here would understate what the claim assumes, which is exactly the kind of
#:   error the uniformity field exists to surface.
#: - **It is a conjecture, though the literature treats it as a known conditional result.** The
#:   stage is about what g0rd0n holds, not what the world knows. The upper bound is in the
#:   kernel at 0.95; the NC¹-completeness of the S₅ word problem (Barrington, 1989) is not in
#:   the kernel at all, and a sketch citing a premise the record does not hold would be the
#:   Evidence Channel's rule broken one layer up. The sketch waits for that premise.
#: - **The prior is 0.6**: above the 0.30 an unaudited seed enters at, because the bound it
#:   rests on is corroborated; well below the 0.95 ceiling, because its other premise is
#:   unsourced here and the separation it is contingent on is open.
T1_WITHOUT_CHAIN_OF_THOUGHT = Separation(
    label="t1-beyond-single-pass-log-precision-transformers",
    family="T1",
    statement=(
        "No family of fixed-depth, log-precision transformers, answering in a single forward "
        "pass with no chain of thought, computes T1 — the composition of n transpositions of "
        "S5 — correctly at every size n."
    ),
    classes=(
        "the model: fixed-depth log-precision transformers sit in logspace-uniform TC0, "
        "constant-depth threshold circuits (hypothesis:log-precision-transformers-sit-in-"
        "uniform-tc0, corroborated in the kernel at 0.95 by arXiv:2207.00729v4); the task: "
        "T1 is the word problem over S5, NC1-complete under AC0 reductions (Barrington, 1989 "
        "— not yet in the kernel)"
    ),
    uniformity=(
        "logspace-uniform throughout: the transformer bound is logspace-uniform, so the "
        "separation needed is from logspace-uniform TC0, not from the DLOGTIME-uniform class"
    ),
    pinned=(Pinned.DEPTH, Pinned.PRECISION, Pinned.STEPS),
    contingent_on=("nc1_not_in_l_uniform_tc0",),
    prior=0.6,
)

#: Every claim this repository ships. Added to by review, like `portfolio.FAMILIES`.
CLAIMS: tuple[Separation, ...] = (T1_WITHOUT_CHAIN_OF_THOUGHT,)


def commit(bridge: Bridge, question: Ref) -> tuple[AssertionId, ...]:
    """Conjecture every shipped claim under a question. Idempotent."""
    committed = (conjecture(bridge, claim, question) for claim in CLAIMS)
    return tuple(assertion for assertion in committed if assertion is not None)
