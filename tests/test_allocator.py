"""The portfolio, and cheapest-falsifier-first allocation over it.

Phase 7b's two minimum tests are here — `allocator_prefers_the_cheaper_of_two_equally_
informative_wagers` and `exhausted_question_triggers_reformulation_not_more_spending`.

Most of this file needs no kernel, which is the point of `read` being the only impure part:
the ranking is a function of a `Board`, so a board can be built by hand and the arithmetic
checked without a subprocess. The tests that do touch the kernel are about `read` itself, and
they use a real `knk` and a throwaway storage root like everything else here.
"""

from dataclasses import replace

import pytest

from g0rd0n.cortex import allocator, portfolio
from g0rd0n.cortex import charter as charter_document
from g0rd0n.cortex import wager as wager_module
from g0rd0n.cortex.allocator import PATIENCE, AllocationError, Board, Exhausted, Next, Standing
from g0rd0n.cortex.portfolio import CONTROL_ARM, FAMILIES, Family
from g0rd0n.cortex.wager import Outcome, Verdict, Wager
from g0rd0n.evidence.channel import belief
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref
from g0rd0n.ledger import Cost

QUESTION = Ref("question", "charter-0123456789ab")
SOURCE = Ref("source", "a-test-source")

#: Three families of our own, so the arithmetic tests do not move when somebody edits a prior
#: in the shipped portfolio. The shipped nine get their own tests below.
LEADER = Family("leader", "the leading paradigm", "T1", 0.4, "it loses on T1 at equal B")
RIVAL = Family("rival", "the second paradigm", "T2", 0.3, "it loses on T2 at equal B")
OUTSIDER = Family("outsider", "the long shot", "T3", 0.05, "it loses on T3 at equal B")


def standing(family: Family, belief_at: float, **changes: int | bool) -> Standing:
    """A row of a board, with everything untried unless the test says otherwise."""
    base = Standing(
        family=family,
        belief=belief_at,
        attempts=0,
        settled=0,
        conclusive=0,
        refuted=False,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def board(*standings: Standing) -> Board:
    return Board(
        question=QUESTION,
        standings=tuple(sorted(standings, key=lambda s: (-s.belief, s.family.slug))),
    )


def field() -> Board:
    """The ordinary case: a leader, a rival that could overtake, and a long shot that cannot."""
    return board(
        standing(LEADER, 0.40),
        standing(RIVAL, 0.30),
        standing(OUTSIDER, 0.05),
    )


#: What a wager costs unless a test is about the price.
ORDINARY = Cost(usd=10.0)


def bet(
    family: Family, *, label: str | None = None, prior: float = 0.3, price: Cost = ORDINARY
) -> Wager:
    """A wager against a family, priced as the test asks and otherwise unremarkable."""
    return Wager(
        label=label or f"w-{family.slug}",
        question=QUESTION,
        hypothesis=family.ref,
        claim=f"{family.what} separates from the control arm at matched B",
        resource="joules at the wall, B per instance",
        task_family=family.arena,
        test="run both arms at matched capability and integrate wall power",
        instrument="wall-plug meter at 1 Hz",
        kill=family.kill,
        price=price,
        prior=prior,
    )


def under_the_question(bridge: Bridge, family: Family) -> None:
    bridge.hypothesise(
        Claim(QUESTION, "hypothesises", family.ref, family.prior),
        Provenance(SOURCE, "a test, standing in for the portfolio"),
    )


# --- The portfolio ----------------------------------------------------------------------


def test_the_portfolio_declares_a_kill_criterion_for_every_family() -> None:
    """AGENTS.md §Phase 7: explicit priors *and* explicit kill criteria, per family.

    Checked for substance rather than for length. ADR 0011 is about exactly this: a floor on
    how many words a criterion has is cleared by anything, so the check is that each one is
    denominated in the currency this Charter fixed — a budget, and the control arm it has to
    be beaten against. A "kill criterion" naming neither is a wish.
    """
    assert len(FAMILIES) == 9
    assert len({family.slug for family in FAMILIES}) == 9

    for family in FAMILIES:
        assert 0.0 < family.prior < 1.0, f"{family.slug} has no usable prior"
        assert family.arena.startswith(("T1", "T2", "T3")), (
            f"{family.slug} names no chartered task family to lose on"
        )
        assert "control arm" in family.kill, (
            f"{family.slug} could lose without losing to anything; the control arm is mandatory"
        )
        assert " B" in family.kill or "P/N" in family.kill, (
            f"{family.slug} states no budget it would have to lose at, so nothing is held fixed"
        )

    kills = {family.kill for family in FAMILIES}
    assert len(kills) == 9, "two families share a kill criterion, so one of them was not written"


def test_the_control_arm_is_in_the_portfolio() -> None:
    """AGENTS.md: "The control arm is mandatory." A portfolio without one proves nothing."""
    arms = [family for family in FAMILIES if family.control_arm]

    assert [family.slug for family in arms] == [CONTROL_ARM]


def test_every_survey_wager_passes_the_falsifiability_gate() -> None:
    """The shipped wagers are wagers, not sketches — checked without a kernel."""
    for wager in portfolio.surveys(QUESTION):
        wager_module.check(wager)


def test_a_survey_cannot_refute_a_family_by_finding_nothing() -> None:
    """ADR 0009, pinned into the shipped data rather than left in a docstring.

    A literature survey observes *retrieved sources*. Silence is `inconclusive`; a survey
    whose kill criterion were the family's bare kill would refute every family whose
    literature happens to live on a host nobody allowlisted.
    """
    for wager in portfolio.surveys(QUESTION):
        assert wager.kill.startswith("a retrievable primary source reports")


def test_seeding_puts_the_families_and_their_kill_criteria_under_the_question(
    bridge: Bridge,
) -> None:
    committed = portfolio.commit(bridge, QUESTION)

    asked = {
        bridge.name_of(assertion.object)
        for assertion in bridge.assertions_for(QUESTION)
        if bridge.predicate_of(assertion.predicate) == "hypothesises"
    }
    assert asked == {family.ref for family in FAMILIES}
    assert len(committed) == 2 * len(FAMILIES)

    for family in FAMILIES:
        kills = [
            assertion
            for assertion in bridge.assertions_for(family.ref)
            if bridge.predicate_of(assertion.predicate) == "kills"
        ]
        assert [bridge.name_of(k.object) for k in kills] == [family.killer]
        provenance = bridge.provenance_for(kills[0].id)
        assert provenance is not None and family.kill in provenance.method


def test_seeding_twice_does_not_double_the_field(bridge: Bridge) -> None:
    portfolio.commit(bridge, QUESTION)

    assert portfolio.commit(bridge, QUESTION) == ()


# --- Ranking ----------------------------------------------------------------------------


def test_allocator_prefers_the_cheaper_of_two_equally_informative_wagers() -> None:
    """AGENTS.md §Phase 7's minimum test, and the whole of "cheapest falsifier first".

    Two wagers on the same family with the same prior are equally informative by
    construction: identical `P(flip)` and identical `value`. Only the divisor differs.
    """
    cheap = bet(LEADER, label="w-cheap", price=Cost(usd=10.0))
    dear = bet(LEADER, label="w-dear", price=Cost(usd=100.0))

    ranking = allocator.rank(field(), [dear, cheap])

    assert [ranked.wager.label for ranked in ranking] == ["w-cheap", "w-dear"]
    assert ranking[0].flip == ranking[1].flip
    assert ranking[0].value == ranking[1].value
    assert ranking[0].score == pytest.approx(ranking[1].score * 10.0)


def test_the_allocator_runs_what_could_kill_the_leader() -> None:
    """Popper as a budget function: the best wager is not the one likeliest to succeed."""
    allocation = allocator.allocate(field(), [bet(LEADER), bet(RIVAL), bet(OUTSIDER)])

    assert isinstance(allocation, Next)
    assert allocation.run.wager.hypothesis == LEADER.ref
    assert "refuting the leader" in allocation.run.why


def test_a_wager_that_cannot_flip_anything_ranks_last_however_cheap_it_is() -> None:
    """ADR 0001 names wager inflation as a failure mode; this is the arithmetic that stops it.

    The long shot at 0.05 cannot reach the leader's 0.40 even if corroborated, so its
    `P(flip)` is exactly zero and no price makes it worth running.
    """
    hopeless = bet(OUTSIDER, label="w-nearly-free", price=Cost(usd=0.01))
    expensive = bet(LEADER, label="w-costly", price=Cost(usd=1000.0))

    ranking = allocator.rank(field(), [hopeless, expensive])

    assert [ranked.wager.label for ranked in ranking] == ["w-costly", "w-nearly-free"]
    assert ranking[1].score == 0.0
    assert ranking[1].flip == 0.0
    assert "short of" in ranking[1].why


def test_a_challenger_that_would_overtake_is_worth_the_margin_it_wins_by() -> None:
    strong = allocator.score(field(), bet(RIVAL, prior=0.6))

    assert strong.flip == 0.6
    assert strong.value == pytest.approx(0.72 - 0.40)  # combine(0.30, 0.60) = 0.72
    assert "past 0.40" in strong.why


def test_a_refuted_or_impatient_family_is_not_worth_spending_on() -> None:
    dead = board(
        standing(LEADER, 0.40, refuted=True),
        standing(RIVAL, 0.30, attempts=PATIENCE, settled=PATIENCE),
        standing(OUTSIDER, 0.05),
    )

    ranking = {r.wager.hypothesis: r for r in allocator.rank(dead, [bet(LEADER), bet(RIVAL)])}

    assert ranking[LEADER.ref].score == 0.0
    assert "refuted" in ranking[LEADER.ref].why
    assert ranking[RIVAL.ref].score == 0.0
    assert "out of patience" in ranking[RIVAL.ref].why


def test_patience_runs_out_only_on_wagers_that_settled_nothing() -> None:
    """A family that lost three arguments is refuted; one whose tests keep failing to argue
    is a problem with the tests, and patience is the rule that says so."""
    argued = standing(LEADER, 0.4, attempts=PATIENCE, settled=PATIENCE, conclusive=PATIENCE)
    silent = standing(LEADER, 0.4, attempts=PATIENCE, settled=PATIENCE, conclusive=0)

    assert not argued.out_of_patience
    assert silent.out_of_patience
    assert not silent.untested


def test_a_family_nothing_tried_to_kill_is_flagged_as_such() -> None:
    """AGENTS.md §Phase 7: surviving and never having been attacked look identical in a
    belief number, and are opposites."""
    survived = standing(LEADER, 0.4, attempts=2, settled=2, conclusive=2)

    assert standing(LEADER, 0.4).untested
    assert not survived.untested


def test_the_ranking_is_a_function_of_the_board() -> None:
    """Ties break on wager id, so two identical boards produce identical rankings — the same
    determinism the vault gets, for the same reason."""
    wagers = [bet(LEADER, label=f"w-{n:02d}", price=Cost(usd=10.0)) for n in range(6)]

    forwards = allocator.rank(field(), wagers)
    backwards = allocator.rank(field(), list(reversed(wagers)))

    assert [r.wager.label for r in forwards] == [r.wager.label for r in backwards]
    assert [r.wager.label for r in forwards] == sorted(w.label for w in wagers)


# --- Price ------------------------------------------------------------------------------


def test_an_hour_of_somebody_s_attention_is_not_free() -> None:
    """A wager costing only reading time would otherwise rank first forever."""
    reading = bet(LEADER, price=Cost(human_seconds=3600.0))

    assert allocator.price_of(reading) == pytest.approx(allocator.HUMAN_USD_PER_HOUR)


def test_a_wager_priced_in_neither_dollars_nor_attention_is_refused() -> None:
    """No guessed number, for the same reason there is no default model price."""
    gpu_only = bet(LEADER, price=Cost(gpu_seconds=1000.0))

    with pytest.raises(AllocationError, match="usd or human_seconds"):
        allocator.price_of(gpu_only)


# --- Stopping -----------------------------------------------------------------------------


def test_exhausted_question_triggers_reformulation_not_more_spending() -> None:
    """AGENTS.md §Phase 7's other minimum test.

    Exhaustion is not budget exhaustion. It is "nothing we could run could change what we
    believe", and the answer to that is a better question rather than a bigger budget — so
    the result carries criticisms for the Question Engine and, deliberately, no wager to run.
    """
    spent = board(
        standing(LEADER, 0.40, refuted=True),
        standing(RIVAL, 0.30, attempts=PATIENCE, settled=PATIENCE),
    )

    allocation = allocator.allocate(spent, [bet(LEADER), bet(RIVAL)])

    assert isinstance(allocation, Exhausted)
    assert not hasattr(allocation, "run")
    assert "the field is empty" in allocation.reason
    assert all(ranked.score == 0.0 for ranked in allocation.ranking)
    assert allocation.criticisms


def test_a_question_nothing_can_unseat_is_exhausted_even_with_families_left() -> None:
    """Every family live, every wager scoring zero: more spending buys no verdict."""
    allocation = allocator.allocate(field(), [bet(OUTSIDER, prior=0.05)])

    assert isinstance(allocation, Exhausted)
    assert "scored zero" in allocation.reason


def test_offering_no_wagers_is_exhaustion_rather_than_a_crash() -> None:
    allocation = allocator.allocate(field(), [])

    assert isinstance(allocation, Exhausted)
    assert allocation.ranking == ()


def test_exhaustion_hands_back_criticisms_a_charter_could_actually_use() -> None:
    """The handover to Phase 5 is only real if the Question Engine accepts what comes back.

    ADR 0007 refuses a supersession with no criticism, so an exhausted question that produced
    none — or produced prose the parser drops — would be a dead end rather than a handover.
    """
    spent = board(
        standing(LEADER, 0.40, refuted=True),
        standing(RIVAL, 0.30, attempts=PATIENCE, settled=PATIENCE),
        standing(OUTSIDER, 0.05),
    )
    allocation = allocator.allocate(spent, [])
    assert isinstance(allocation, Exhausted)
    criticisms = allocation.criticisms

    assert len(criticisms) == 3
    assert "was refuted" in criticisms[0]
    assert "settled without a verdict" in criticisms[1]
    assert "nothing tried to kill it" in criticisms[2]

    written = "\n".join(
        [
            "# Charter",
            *(f"\n## {heading}\n\nsomething" for heading in charter_document.ELEMENTS),
            "\n## Definitions\n\n0123456789ab",
            "\n## Supersedes\n\ncharter-0123456789ab",
            "\n## Criticisms\n",
            *(f"- {criticism}" for criticism in criticisms),
            "",
        ]
    )
    assert charter_document.parse(written).criticisms == criticisms


# --- Reading the kernel -------------------------------------------------------------------


def test_the_board_agrees_with_the_evidence_channel_about_belief(bridge: Bridge) -> None:
    """One scan and nine lookups must say the same thing, or one of them is wrong.

    Retraction is the case that separates them: the Evidence Channel drops `Retracted` and
    `Retraction` statuses, and a board that counted them would keep believing a withdrawn
    claim and go on funding a family nobody stands behind any more.
    """
    portfolio.commit(bridge, QUESTION)
    withdrawn = FAMILIES[0]
    for assertion in bridge.assertions_for(QUESTION):
        if bridge.name_of(assertion.object) == withdrawn.ref:
            bridge.retract(assertion.id, Provenance(SOURCE, "a test, withdrawing a prior"))

    read = allocator.read(bridge, QUESTION, FAMILIES)

    for row in read.standings:
        asked = Claim(QUESTION, "hypothesises", row.family.ref, row.family.prior)
        assert row.belief == pytest.approx(belief(asked, bridge=bridge))
        expected = 0.0 if row.family == withdrawn else row.family.prior
        assert row.belief == pytest.approx(expected)


def test_a_settled_wager_shows_up_as_an_attempt_on_its_family(bridge: Bridge) -> None:
    under_the_question(bridge, LEADER)
    wager = bet(LEADER, price=Cost(usd=1.0))
    registration = wager_module.register(bridge, wager)

    tried = allocator.read(bridge, QUESTION, [LEADER]).standings[0]
    assert (tried.attempts, tried.settled, tried.conclusive) == (1, 0, 0)
    assert not tried.untested

    wager_module.record(bridge, registration, Outcome(Verdict.REFUTED, "it lost at equal B"))

    done = allocator.read(bridge, QUESTION, [LEADER]).standings[0]
    assert (done.attempts, done.settled, done.conclusive) == (1, 1, 1)
    assert done.refuted
    assert not done.live


def test_a_verdict_that_settled_nothing_is_an_attempt_that_argued_nothing(
    bridge: Bridge,
) -> None:
    under_the_question(bridge, LEADER)
    wager = bet(LEADER, price=Cost(usd=1.0))
    registration = wager_module.register(bridge, wager)

    wager_module.record(bridge, registration, Outcome(Verdict.INCONCLUSIVE, "the meter died"))

    row = allocator.read(bridge, QUESTION, [LEADER]).standings[0]
    assert (row.attempts, row.settled, row.conclusive) == (1, 1, 0)
    assert not row.refuted


def test_the_board_is_the_kernel_and_not_the_wagers_we_happen_to_hold(bridge: Bridge) -> None:
    """`untested` has to mean "nothing tried", not "nothing on this list tried".

    A wager registered from another file, another session, or another branch still counts.
    Reading the wagers in hand instead would report a family as never attacked because the
    attack was declared somewhere the caller did not look.
    """
    under_the_question(bridge, LEADER)
    wager_module.register(bridge, bet(LEADER, label="w-somebody-elses", price=Cost(usd=1.0)))

    row = allocator.read(bridge, QUESTION, [LEADER]).standings[0]

    assert row.attempts == 1
    assert not row.untested
