"""The Formal Cell: separation claims, their stages, and what a checker has to show.

Phase 9's three minimum tests are here — `separation_claim_records_its_contingent_assumptions`,
`proof_sketch_is_never_reported_as_a_theorem` and
`machine_checked_status_requires_a_checker_artifact` — with the refusals around them.

No proof assistant is installed on the machine this was written on, and none is shipped (see
`instruments/prover.py`). So the checker here is a stand-in that hands back whatever artifact a
test tells it to. That is honest about what is and is not being tested: these tests check
what g0rd0n does *with* a checker's report — refuse a hole, refuse an undeclared assumption,
refuse a proof of a different statement — and say nothing about whether a real Lean would
produce that report. The kernel tests run against a real `knk`, as every kernel test in this
repository does.
"""

from dataclasses import replace

import pytest

from g0rd0n.cortex import formal
from g0rd0n.cortex.formal import (
    OPEN,
    ORDER,
    FormalError,
    Pinned,
    Separation,
    Sketch,
    Stage,
)
from g0rd0n.instruments.prover import Checked, ProverError, unadmitted
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref
from g0rd0n.vault import note, projector

QUESTION = Ref("question", "charter-0123456789ab")

SHIPPED = formal.T1_WITHOUT_CHAIN_OF_THOUGHT

#: The formal statement a sketch pins, and a proof has to prove exactly.
FORMAL = "∀ (d : Nat), ¬ ComputesT1 (LogPrecisionTransformer d)"


def a_claim(**changes: object) -> Separation:
    """A contingent S1 claim, varied field by field."""
    base = Separation(
        label="toy-separation",
        family="T1",
        statement="Single-pass transformers do not compute T1 at every size.",
        classes="the model in logspace-uniform TC0; the task NC1-complete",
        uniformity="logspace-uniform",
        pinned=(Pinned.DEPTH, Pinned.PRECISION),
        contingent_on=("nc1_not_in_l_uniform_tc0",),
        prior=0.5,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def a_sketch(formal_statement: str = FORMAL) -> Sketch:
    return Sketch(
        argument=(
            "The model is simulated by logspace-uniform TC0 circuits. T1 is NC1-complete. "
            "So a model computing T1 at every size would put NC1 inside logspace-uniform TC0."
        ),
        formal=formal_statement,
    )


def an_artifact(
    *, axioms: tuple[str, ...] = ("propext", "nc1_not_in_l_uniform_tc0"), statement: str = FORMAL
) -> Checked:
    """What a checker would hand back. The proof bytes are a stand-in; nothing reads them."""
    return Checked(
        checker="lean4",
        version="4.x (stand-in)",
        theorem="single_pass_transformers_miss_t1",
        statement=statement,
        proof=b"theorem single_pass_transformers_miss_t1 : ... := by\n  exact ...\n",
        axioms=axioms,
    )


def ask(bridge: Bridge, question: Ref = QUESTION) -> None:
    """Put a question in the kernel, so a conjecture has a parent to hang off."""
    bridge.hypothesise(
        Claim(question, "asks", Ref("statement", f"{question.name}-question"), 1.0),
        Provenance(Ref("source", "test-fixture"), "a test standing a question up"),
    )


def provenance_of(bridge: Bridge, claim: Separation) -> list[str]:
    """Every provenance method on every edge touching the claim, from either end."""
    found = []
    for assertion in bridge.changes_since(0):
        ends = (bridge.name_of(assertion.subject), bridge.name_of(assertion.object))
        if claim.ref in ends:
            recorded = bridge.provenance_for(assertion.id)
            assert recorded is not None
            found.append(recorded.method)
    return found


# --- the three minimum tests -----------------------------------------------------------


def test_separation_claim_records_its_contingent_assumptions() -> None:
    """AGENTS.md §Phase 9: the class, the uniformity, and the unproven separations, forever.

    "Forever" is the identity. Every field the claim states is inside its hash, so there is no
    edit that drops `NC¹ ⊄ L-uniform TC⁰` and keeps the id — the only way to stop being
    contingent is to be a different claim, and the old one stays in the record with its label.
    """
    assert SHIPPED.contingent
    assert SHIPPED.contingent_on == ("nc1_not_in_l_uniform_tc0",)
    assert "logspace-uniform" in SHIPPED.uniformity
    assert "TC0" in SHIPPED.classes and "NC1" in SHIPPED.classes
    assert set(SHIPPED.pinned) == {Pinned.DEPTH, Pinned.PRECISION, Pinned.STEPS}

    for label in (SHIPPED.label_of_contingency, SHIPPED.bookkeeping, formal.render(SHIPPED, None)):
        assert "CONTINGENT on nc1_not_in_l_uniform_tc0" in label
        assert OPEN["nc1_not_in_l_uniform_tc0"] in label, "the open problem, spelled out"

    for field, value in (
        ("contingent_on", ()),
        ("contingent_on", ("tc0_ne_nc1",)),
        ("uniformity", "DLOGTIME-uniform"),
        ("classes", "the model in TC0"),
        ("pinned", (Pinned.DEPTH,)),
    ):
        changed = replace(SHIPPED, **{field: value})  # type: ignore[arg-type]
        assert changed.id != SHIPPED.id, f"{field} is not in the id"

    unconditional = replace(SHIPPED, contingent_on=())
    assert not unconditional.contingent
    assert unconditional.label_of_contingency.startswith("UNCONDITIONAL")


def test_proof_sketch_is_never_reported_as_a_theorem() -> None:
    """The word "theorem" is reserved for one case: machine-checked and unconditional.

    Checked exhaustively over every stage and both kinds of claim, because the failure is a
    wording that drifts one case at a time. A machine-checked *contingent* result is not a
    theorem either — it is a conditional result, and its description says what it is
    conditional on, because "machine-checked" on its own reads as "true".
    """
    contingent = a_claim()
    unconditional = a_claim(contingent_on=())

    for claim in (contingent, unconditional):
        for stage in (None, *ORDER):
            said = formal.describe(claim, stage)
            is_theorem = stage is Stage.CHECKED and not claim.contingent
            assert ("theorem" in said) is is_theorem, (claim.label_of_contingency, stage, said)
            assert formal.render(claim, stage).splitlines()[0].endswith(f"[{said}]")

    assert "not machine-checked" in formal.describe(contingent, Stage.SKETCH)
    conditional = formal.describe(contingent, Stage.CHECKED)
    assert "conditional" in conditional and "nc1_not_in_l_uniform_tc0" in conditional
    assert "no proof held" in formal.describe(contingent, Stage.CONJECTURE)

    for stage in (None, *ORDER):
        assert "Phase 10" in formal.render(contingent, stage), "a stage is never belief"


def test_machine_checked_status_requires_a_checker_artifact(bridge: Bridge) -> None:
    """The third stage is reached through `checked`, which takes a checker's artifact, and
    nothing else reaches it.

    Three things are shown. There is no path to `machine-checked` that skips the artifact: a
    sketched claim stays a sketch until one is presented. The artifact has to name everything
    needed to repeat the check — checker, version, declaration, statement, the proof itself.
    And a checker g0rd0n has no table for is refused rather than trusted, because its
    foundational axioms could not be told apart from what the proof assumed.
    """
    ask(bridge)
    claim = a_claim()
    formal.conjecture(bridge, claim, QUESTION)
    formal.sketch(bridge, claim, a_sketch())
    assert formal.stage_of(bridge, claim) is Stage.SKETCH

    for field in ("checker", "version", "theorem", "statement"):
        with pytest.raises(ProverError, match=f"must name its {field}"):
            replace(an_artifact(), **{field: " "})  # type: ignore[arg-type]
    with pytest.raises(ProverError, match="must carry the proof"):
        replace(an_artifact(), proof=b"")
    with pytest.raises(ProverError, match="not a checker g0rd0n knows how to read"):
        replace(an_artifact(), checker="trust-me")

    assert formal.stage_of(bridge, claim) is Stage.SKETCH, "no artifact, no third stage"
    formal.checked(bridge, claim, a_sketch(), an_artifact())
    assert formal.stage_of(bridge, claim) is Stage.CHECKED


# --- the prover's reading of an artifact -------------------------------------------------


def test_a_proof_with_a_hole_in_it_is_not_machine_checked(bridge: Bridge) -> None:
    """`sorry` compiles. A proof that depends on it is a sketch that compiles, and is refused.

    Not reported as "machine-checked, contingent on sorry" either: a hole is not an assumption
    the claim could have declared, it is the absence of the proof.
    """
    holed = an_artifact(axioms=("propext", "sorryAx"))
    with pytest.raises(ProverError, match="hole in the proof"):
        unadmitted(holed, ("sorryAx",))

    ask(bridge)
    claim = a_claim()
    formal.conjecture(bridge, claim, QUESTION)
    formal.sketch(bridge, claim, a_sketch())
    with pytest.raises(FormalError, match="hole in the proof"):
        formal.checked(bridge, claim, a_sketch(), holed)
    assert formal.stage_of(bridge, claim) is Stage.SKETCH


def test_a_proof_that_assumes_what_the_claim_did_not_declare_is_refused(bridge: Bridge) -> None:
    """The one place Phase 9's bookkeeping is checked by a machine rather than by a reader.

    A proof that assumes an open problem as an axiom is a proof *contingent on* that problem.
    If the claim never declared it, the claim is stronger than what was proved — and the
    checker's axiom report is exactly where that shows. Foundational axioms are the checker's
    own logic and say nothing about the claim; everything else is an assumption.
    """
    assert unadmitted(an_artifact(axioms=("propext", "Quot.sound")), ()) == ()
    assert unadmitted(an_artifact(), ("nc1_not_in_l_uniform_tc0",)) == ()
    assert unadmitted(an_artifact(axioms=("tc0_ne_nc1",)), ("nc1_not_in_l_uniform_tc0",)) == (
        "tc0_ne_nc1",
    )
    assert unadmitted(an_artifact(axioms=("Lean.ofReduceBool",)), ()) == ("Lean.ofReduceBool",), (
        "native_decide trusts the compiler, and that is an assumption like any other"
    )

    ask(bridge)
    overclaim = a_claim(contingent_on=())
    formal.conjecture(bridge, overclaim, QUESTION)
    formal.sketch(bridge, overclaim, a_sketch())
    with pytest.raises(FormalError, match="assumes nc1_not_in_l_uniform_tc0"):
        formal.checked(bridge, overclaim, a_sketch(), an_artifact())
    assert formal.stage_of(bridge, overclaim) is Stage.SKETCH


def test_a_proof_of_a_different_statement_does_not_advance_the_claim(bridge: Bridge) -> None:
    """A sketch pins a formal statement; a proof of anything else is not a proof of the claim.

    The declaration's *name* would let a different theorem with a friendlier type through, so
    the comparison is on the statement the checker elaborated. Whitespace is not a difference.
    """
    ask(bridge)
    claim = a_claim()
    formal.conjecture(bridge, claim, QUESTION)
    formal.sketch(bridge, claim, a_sketch())

    weaker = an_artifact(statement="∀ (d : Nat), d = 1 → ¬ ComputesT1 (LogPrecisionTransformer d)")
    with pytest.raises(FormalError, match="not a proof of this claim"):
        formal.checked(bridge, claim, a_sketch(), weaker)

    other = Sketch(argument="A different argument.", formal="True")
    with pytest.raises(FormalError, match="not a live sketch"):
        formal.checked(bridge, claim, other, an_artifact(statement="True"))

    reflowed = an_artifact(statement=FORMAL.replace(" ", "   "))
    formal.checked(bridge, claim, a_sketch(), reflowed)
    assert formal.stage_of(bridge, claim) is Stage.CHECKED


# --- the stages, in the kernel ------------------------------------------------------------


def test_stages_are_reached_in_order_and_never_skipped(bridge: Bridge) -> None:
    """`conjecture` → `proof sketch` → `machine-checked`, one step at a time.

    Never skipped, because the sketch is where the formal statement is pinned in front of a
    human reader, and a proof that never passed through one is a proof of a statement nobody
    compared with the claim. Never repeated, because a second sketch or a second check is a
    second argument, and it arrives by retracting the first.
    """
    ask(bridge)
    claim = a_claim()

    with pytest.raises(FormalError, match="not in the kernel"):
        formal.sketch(bridge, claim, a_sketch())
    formal.conjecture(bridge, claim, QUESTION)

    with pytest.raises(FormalError, match="follows proof sketch"):
        formal.checked(bridge, claim, a_sketch(), an_artifact())
    formal.sketch(bridge, claim, a_sketch())

    with pytest.raises(FormalError, match="at proof sketch"):
        formal.sketch(bridge, claim, a_sketch())
    formal.checked(bridge, claim, a_sketch(), an_artifact())

    with pytest.raises(FormalError, match="at machine-checked"):
        formal.checked(bridge, claim, a_sketch(), an_artifact())


def test_the_stage_is_read_back_from_the_kernel_alone(bridge: Bridge) -> None:
    """The stage is a fact about the record, not a field somebody set.

    So stepping back needs no special case. Retracting the sketch's edge returns the claim to
    a conjecture, with both edges still in the record; retracting the conjecture withdraws
    the claim, whatever else was once said about it.
    """
    ask(bridge)
    claim = a_claim()
    assert formal.stage_of(bridge, claim) is None

    conjectured = formal.conjecture(bridge, claim, QUESTION)
    assert conjectured is not None
    assert formal.stage_of(bridge, claim) is Stage.CONJECTURE

    sketched = formal.sketch(bridge, claim, a_sketch())
    assert formal.stage_of(bridge, claim) is Stage.SKETCH

    withdrawn = Provenance(Ref("source", "a-referee"), "the sketch's second step does not follow")
    bridge.retract(sketched, withdrawn)
    assert formal.stage_of(bridge, claim) is Stage.CONJECTURE

    bridge.retract(conjectured, withdrawn)
    assert formal.stage_of(bridge, claim) is None


def test_every_edge_about_a_contingent_claim_carries_its_contingency(bridge: Bridge) -> None:
    """ "Labelled as contingent, forever", from whichever direction a reader arrives.

    Three edges, three different predicates, three different ends — and every one repeats the
    contingency in its provenance, headed by the stage that edge *is*. A reader who meets the
    machine-checked result first meets "CONTINGENT" on the same line.
    """
    ask(bridge)
    claim = a_claim()
    formal.conjecture(bridge, claim, QUESTION)
    formal.sketch(bridge, claim, a_sketch())
    formal.checked(bridge, claim, a_sketch(), an_artifact())

    methods = provenance_of(bridge, claim)
    assert len(methods) == 3
    assert all(claim.label_of_contingency in method for method in methods)
    assert [method.split(":")[0].split(" (")[0].split(" by ")[0] for method in methods] == [
        str(stage) for stage in ORDER
    ]
    assert "assumed: nc1_not_in_l_uniform_tc0" in methods[-1]
    assert "theorem" not in " ".join(methods), "a conditional result is never called a theorem"


def test_conjecturing_needs_a_committed_question_and_is_idempotent(bridge: Bridge) -> None:
    """No claim without a parent question, and seeding twice commits once."""
    with pytest.raises(FormalError, match="not in the kernel"):
        formal.conjecture(bridge, a_claim(), QUESTION)
    with pytest.raises(FormalError, match="under a question"):
        formal.conjecture(bridge, a_claim(), Ref("hypothesis", "not-a-question"))

    ask(bridge)
    first = formal.commit(bridge, QUESTION)
    assert len(first) == len(formal.CLAIMS)
    assert formal.commit(bridge, QUESTION) == ()
    assert all(formal.stage_of(bridge, claim) is Stage.CONJECTURE for claim in formal.CLAIMS)


def test_a_sketched_claim_reads_as_a_sketch_in_the_vault(bridge: Bridge) -> None:
    """The vault is today's display, and a sketch must not read like a result in it.

    Nothing in the projection knows what a proof stage is. It does not need to: every edge's
    provenance leads with the stage it is and carries the contingency, and the vault prints
    provenance next to every edge. So the claim's note says "proof sketch (not
    machine-checked)" and "CONTINGENT" on the line where its sketch appears, and nowhere does
    it say "theorem".
    """
    ask(bridge)
    claim = a_claim()
    formal.conjecture(bridge, claim, QUESTION)
    formal.sketch(bridge, claim, a_sketch())

    notes = note.render(projector.snapshot(bridge))
    page = notes[f"Hypotheses/{claim.id}.md"]
    assert "proof sketch (not machine-checked)" in page
    assert "CONTINGENT on nc1_not_in_l_uniform_tc0" in page
    assert "theorem" not in page


# --- the claim itself --------------------------------------------------------------------


def test_an_s1_claim_must_state_what_it_pins_and_what_it_rests_on() -> None:
    """Each field AGENTS.md asks for, refused when it is missing, and the table closed."""
    with pytest.raises(FormalError, match="which of depth, precision, steps"):
        a_claim(pinned=())
    with pytest.raises(FormalError, match="pinned twice"):
        a_claim(pinned=(Pinned.DEPTH, Pinned.DEPTH))
    for field in ("statement", "classes", "uniformity"):
        with pytest.raises(FormalError, match=f"must state its {field}"):
            a_claim(**{field: "  "})
    with pytest.raises(FormalError, match="not an open problem this system has a name for"):
        a_claim(contingent_on=("p_ne_np",))
    with pytest.raises(FormalError, match="listed twice"):
        a_claim(contingent_on=("tc0_ne_nc1", "tc0_ne_nc1"))
    with pytest.raises(FormalError, match="not a chartered task family"):
        a_claim(family="T9")
    with pytest.raises(FormalError, match="conviction"):
        a_claim(prior=1.0)
    with pytest.raises(FormalError, match="usable label"):
        a_claim(label="Not A Label")


def test_the_shipped_claim_needs_the_stronger_contingency() -> None:
    """The worked example, and the trap it exists to show.

    The transformer bound in the kernel is logspace-uniform (the seed audit's correction to
    AGENTS.md's unqualified "uniform"), so the separation the argument needs is from
    logspace-uniform TC⁰ — which implies `TC⁰ ≠ NC¹` and is not known to follow from it.
    Declaring the familiar one would understate what the claim assumes. It is a conjecture,
    because the NC¹-completeness it rests on is not yet in the kernel.
    """
    assert SHIPPED.contingent_on == ("nc1_not_in_l_uniform_tc0",)
    assert "tc0_ne_nc1" not in SHIPPED.contingent_on
    assert "Implies `tc0_ne_nc1`" in OPEN["nc1_not_in_l_uniform_tc0"]
    assert "not yet in the kernel" in SHIPPED.classes
    assert SHIPPED in formal.CLAIMS
    assert "theorem" not in formal.render(SHIPPED, Stage.CONJECTURE)
