"""The Wager, the falsifiability gate, and pre-registration.

Phase 7a's two minimum tests are here — `wager_without_a_kill_criterion_is_rejected` and
`experiment_result_committed_before_preregistration_is_rejected` — plus the gates either side
of them. The kernel tests use a real `knk` and a throwaway storage root, like every other
kernel test here: a pre-registration verified against a mock is a pre-registration verified
against what its author believed knk does.
"""

import inspect
from dataclasses import replace
from typing import Any

import pytest

from g0rd0n.config import Config
from g0rd0n.cortex import wager as wager_module
from g0rd0n.cortex.wager import (
    GATE,
    Outcome,
    Registration,
    Unfalsifiable,
    Verdict,
    Wager,
    WagerError,
)
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref
from g0rd0n.ledger import Cost, Ledger

QUESTION = Ref("question", "charter-0123456789ab")
HYPOTHESIS = Ref("hypothesis", "spiking-nets-win-at-matched-joules")
SEED_SOURCE = Ref("source", "a-test-source")

#: A wager that passes the gate. Every gate test takes this and removes one thing, so a test
#: that fails says which single field mattered.
WAGER = Wager(
    label="w-007-spiking-at-matched-joules",
    question=QUESTION,
    hypothesis=HYPOTHESIS,
    claim=(
        "A spiking network solves T1 sequence-recall at 0.8 capability for fewer joules than "
        "the transformer control arm at the same capability."
    ),
    resource="joules at the wall, budget B fixed per instance",
    task_family="T1 sequence recall, as CHARTER.md fixes it",
    test="run both arms on the T1 suite at matched capability and integrate wall power",
    instrument="wall-plug meter sampled at 1 Hz, logged per instance",
    kill="the spiking arm needs at least as many joules as the control arm at 0.8 capability",
    price=Cost(usd=4.0, seconds=1800.0),
    prior=0.25,
)


def wager(**changes: Any) -> Wager:  # noqa: ANN401 — `replace` is heterogeneous by nature
    """`WAGER`, with fields replaced. One line per thing a test is actually about."""
    return replace(WAGER, **changes)


def under_the_question(bridge: Bridge, hypothesis: Ref = HYPOTHESIS) -> None:
    """Put a hypothesis under the question, the way the Evidence Channel would have."""
    bridge.hypothesise(
        Claim(QUESTION, "hypothesises", hypothesis, 0.3),
        Provenance(SEED_SOURCE, "a test, standing in for the portfolio"),
    )


def edges(bridge: Bridge, subject: Ref) -> list[tuple[str, Ref]]:
    """Every assertion about `subject`, as (predicate, object)."""
    return [
        (bridge.predicate_of(assertion.predicate), bridge.name_of(assertion.object))
        for assertion in bridge.assertions_for(subject)
    ]


def method_of(bridge: Bridge, subject: Ref, predicate: str) -> str:
    """The provenance method of the one assertion with this subject and predicate."""
    for assertion in bridge.assertions_for(subject):
        if bridge.predicate_of(assertion.predicate) == predicate:
            provenance = bridge.provenance_for(assertion.id)
            assert provenance is not None
            return provenance.method
    raise AssertionError(f"no {predicate} edge on {subject}")


# --- The falsifiability gate ------------------------------------------------------------


def test_wager_without_a_kill_criterion_is_rejected() -> None:
    """AGENTS.md §Falsifiability gate: "No item 4, no Wager." A permanent CI invariant.

    Item 4 is the observation that would kill the claim, and its price, so both halves are
    checked here: a wager that cannot lose, and a wager that costs nothing to find out.
    """
    with pytest.raises(Unfalsifiable, match=r"kill"):
        wager_module.check(wager(kill="   "))

    with pytest.raises(Unfalsifiable, match="price"):
        wager_module.check(wager(price=Cost()))


def test_every_item_the_gate_demands_is_refused_when_missing() -> None:
    """The rest of the gate, one field at a time, so a rejection names what is missing."""
    for field, what in GATE.items():
        with pytest.raises(Unfalsifiable) as raised:
            wager_module.check(wager(**{field: ""}))
        assert what in str(raised.value), f"the refusal for {field} does not say what is missing"


def test_a_prior_of_certainty_is_not_a_wager() -> None:
    """Nothing could move it, so there is nothing worth spending to find out."""
    for prior in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(Unfalsifiable, match="conviction"):
            wager_module.check(wager(prior=prior))


def test_a_wager_descends_from_a_question_and_tests_a_hypothesis() -> None:
    with pytest.raises(WagerError, match="descends from a question"):
        wager_module.check(wager(question=Ref("statement", "not-a-question")))

    with pytest.raises(WagerError, match="tests a hypothesis"):
        wager_module.check(wager(hypothesis=Ref("observation", "not-a-hypothesis")))


def test_a_label_a_cost_report_could_not_print_is_rejected() -> None:
    for label in ("W 007", "Spiking Nets", "", "w_007"):
        with pytest.raises(WagerError, match="usable wager label"):
            wager_module.check(wager(label=label))


# --- Identity ---------------------------------------------------------------------------


def test_a_wager_is_identified_by_what_it_preregistered() -> None:
    """Post-hoc criteria are structurally impossible: an edited wager is a different wager."""
    softened = wager(kill="the spiking arm looks worse, broadly speaking")

    assert softened.id != WAGER.id
    assert wager().id == WAGER.id
    assert WAGER.id.startswith(f"{WAGER.label}-")


def test_reflowing_the_prose_is_not_a_new_wager() -> None:
    """Whitespace is not substance, in the same way that section order is not, for a charter."""
    rewrapped = wager(claim="\n".join(WAGER.claim.split()))

    assert rewrapped.id == WAGER.id


def test_every_field_a_wager_preregisters_is_inside_its_version() -> None:
    """A field outside the hash is a field that can be changed after registration."""
    changed: dict[str, Any] = {
        "label": "w-008-something-else",
        "question": Ref("question", "charter-ffffffffffff"),
        "hypothesis": Ref("hypothesis", "some-other-candidate"),
        "claim": "a different claim",
        "resource": "watts, not joules",
        "task_family": "T2 algorithmic induction",
        "test": "a different procedure",
        "instrument": "RAPL, not a wall meter",
        "kill": "a different observation",
        "price": Cost(usd=9.0),
        "prior": 0.6,
    }
    assert set(changed) == set(wager_module.SUBSTANCE)
    for field, value in changed.items():
        assert wager(**{field: value}).version != WAGER.version, f"{field} is outside the hash"


# --- Pre-registration -------------------------------------------------------------------


def test_registering_puts_the_test_the_kill_and_the_price_into_the_kernel(
    bridge: Bridge,
) -> None:
    """Claim, test, price and kill-criterion, committed before anything runs (AGENTS.md §7)."""
    under_the_question(bridge)

    registration = wager_module.register(bridge, WAGER)

    assert edges(bridge, WAGER.experiment) == [("tests", HYPOTHESIS)]
    assert ("kills", WAGER.killer) in edges(bridge, HYPOTHESIS)
    assert edges(bridge, WAGER.ref) == [("costs", WAGER.priced)]
    assert len(registration.assertions) == 3

    assert WAGER.kill in method_of(bridge, HYPOTHESIS, "kills")
    assert WAGER.test in method_of(bridge, WAGER.experiment, "tests")
    assert WAGER.instrument in method_of(bridge, WAGER.experiment, "tests")
    assert '"usd": 4.0' in method_of(bridge, WAGER.ref, "costs")


def test_a_wager_whose_question_does_not_ask_it_is_refused(bridge: Bridge) -> None:
    """AGENTS.md §4: no Wager without a parent Question — checked, not taken on trust."""
    under_the_question(bridge, Ref("hypothesis", "an-entirely-different-candidate"))

    with pytest.raises(WagerError, match="no parent question"):
        wager_module.register(bridge, WAGER)

    assert edges(bridge, WAGER.experiment) == []


def test_a_wager_is_registered_once(bridge: Bridge) -> None:
    under_the_question(bridge)
    wager_module.register(bridge, WAGER)

    with pytest.raises(WagerError, match="already registered"):
        wager_module.register(bridge, WAGER)


def test_the_gate_runs_before_the_kernel_is_touched(bridge: Bridge) -> None:
    """An unfalsifiable wager costs a round trip to nothing at all."""
    under_the_question(bridge)
    unfalsifiable = wager(kill="")

    with pytest.raises(Unfalsifiable):
        wager_module.register(bridge, unfalsifiable)

    assert edges(bridge, unfalsifiable.experiment) == []
    assert edges(bridge, unfalsifiable.ref) == []


# --- Results ----------------------------------------------------------------------------


def test_experiment_result_committed_before_preregistration_is_rejected(bridge: Bridge) -> None:
    """A permanent CI invariant (AGENTS.md §Testing Requirements).

    Enforced by the shape of the API first — `record` takes a `Registration`, and `register`
    is the only thing that makes one — and by a lookup second, because a caller who builds
    the token by hand holds a receipt nobody issued.
    """
    under_the_question(bridge)
    forged = Registration(wager=WAGER, tests=1, kills=2, costs=3, document=4)

    with pytest.raises(wager_module.NotPreregistered):
        wager_module.record(bridge, forged, Outcome(Verdict.REFUTED, "it lost"))

    assert edges(bridge, WAGER.experiment) == []
    assert edges(bridge, WAGER.result) == []


def test_a_registration_naming_another_wagers_preregistration_is_rejected(
    bridge: Bridge,
) -> None:
    """The lookup checks *which* wager was registered, not merely that something was."""
    under_the_question(bridge)
    registered = wager_module.register(bridge, WAGER)
    other = wager(label="w-008-someone-elses-wager")

    with pytest.raises(wager_module.NotPreregistered, match="registered before it ran"):
        wager_module.record(
            bridge, replace(registered, wager=other), Outcome(Verdict.REFUTED, "it lost")
        )


def test_a_refutation_names_the_criterion_that_was_written_down_first(bridge: Bridge) -> None:
    under_the_question(bridge)
    registration = wager_module.register(bridge, WAGER)

    recorded = wager_module.record(
        bridge,
        registration,
        Outcome(Verdict.REFUTED, "the spiking arm used 2.3x the joules at 0.8 capability"),
    )

    assert recorded.verdict is Verdict.REFUTED
    assert edges(bridge, WAGER.experiment) == [("tests", HYPOTHESIS), ("measures", WAGER.result)]
    assert edges(bridge, WAGER.result) == [("refutes", HYPOTHESIS)]
    assert WAGER.kill in method_of(bridge, WAGER.result, "refutes")


def test_a_corroboration_commits_the_edge_that_argues_for_it(bridge: Bridge) -> None:
    under_the_question(bridge)
    registration = wager_module.register(bridge, WAGER)

    wager_module.record(bridge, registration, Outcome(Verdict.CORROBORATED, "0.41x the joules"))

    assert edges(bridge, WAGER.result) == [("corroborates", HYPOTHESIS)]


def test_a_verdict_that_settles_nothing_argues_nothing(bridge: Bridge) -> None:
    """An inconclusive or abandoned wager is recorded and does not become weak support."""
    for verdict, finding in (
        (Verdict.INCONCLUSIVE, "the meter lost its serial connection halfway through"),
        (Verdict.ABANDONED, "the control arm could not be tuned honestly in the time we had"),
    ):
        under_the_question(bridge)
        one = wager(label=f"w-{verdict}-arm")
        recorded = wager_module.record(
            bridge, wager_module.register(bridge, one), Outcome(verdict, finding)
        )

        assert edges(bridge, one.experiment)[-1] == ("measures", one.result)
        assert edges(bridge, one.result) == []
        assert finding in method_of(bridge, one.experiment, "measures")
        assert recorded.verdict is verdict


def test_an_abandoned_wager_must_say_why(bridge: Bridge) -> None:
    """AGENTS.md §Core Types: abandoned is a legitimate outcome and requires a reason."""
    under_the_question(bridge)
    registration = wager_module.register(bridge, WAGER)

    with pytest.raises(WagerError, match="must say what was found"):
        wager_module.record(bridge, registration, Outcome(Verdict.ABANDONED, "  "))

    assert edges(bridge, WAGER.result) == []


def test_a_wager_gets_one_verdict(bridge: Bridge) -> None:
    under_the_question(bridge)
    registration = wager_module.register(bridge, WAGER)
    wager_module.record(bridge, registration, Outcome(Verdict.INCONCLUSIVE, "the meter died"))

    with pytest.raises(WagerError, match="already been settled"):
        wager_module.record(bridge, registration, Outcome(Verdict.REFUTED, "on reflection"))


def test_running_out_of_money_is_not_a_verdict() -> None:
    """AGENTS.md §Core Types. The enum is closed, and this is the thing it is closed against."""
    assert {str(verdict) for verdict in Verdict} == {
        "corroborated",
        "refuted",
        "inconclusive",
        "abandoned",
    }


# --- Money ------------------------------------------------------------------------------


def test_no_spend_against_an_unregistered_wager() -> None:
    """The Phase 7 half of the priced-before-run invariant, enforced by the API's shape.

    The Ledger prices any string handed to it, because it is owned by no layer and knows
    nothing about Wagers. `cortex.reserve` is where the string becomes a wager somebody
    committed to first: it takes a `Registration`, which only `register` produces, and it
    takes **no estimate**, so the price is the one that was pre-registered.
    """
    parameters = inspect.signature(wager_module.reserve).parameters

    assert list(parameters) == ["ledger", "registration", "agent"]
    assert parameters["registration"].annotation is Registration
    assert not {"estimate", "price", "cost"} & set(parameters)


def test_reserving_uses_the_price_that_was_written_down_first(
    bridge: Bridge, kernel_config: Config
) -> None:
    under_the_question(bridge)
    registration = wager_module.register(bridge, WAGER)
    ledger = Ledger(kernel_config, session="s-test", campaign="c-1", phase="7a")

    reservation = wager_module.reserve(ledger, registration, agent="bench")

    assert reservation.wager_id == WAGER.id
    assert reservation.estimate == WAGER.price
    assert ledger.open_reservations == (reservation,)
