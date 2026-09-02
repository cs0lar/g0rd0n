"""The arms and the matched-capability protocol: two arms, one instance set, one `measures`.

Phase 8c, and the last of Phase 8's four minimum tests —
`baseline_arm_runs_on_every_evaluation` — lands here with the arms it needs.

Most of this file runs without `knk`, deliberately. A `Registration` is a frozen dataclass and
a hand-built one is easy to make, so every refusal in `Evaluation` can be checked without a
kernel; what a hand-built one *cannot* do is survive `settle`, which is itself one of the
tests. The two that reach the kernel do the whole round trip against a real `knk`: register,
run, record, and read the `measures` edge back.

The family here is a toy, not one of the three chartered ones. That is on purpose. These tests
are about the protocol, and a protocol test that has to solve S₅ compositions to shape a curve
is a test of `tasks.py` wearing the wrong name. `tests/test_bench.py` checks the real
families against a second implementation; this file checks that two arms are run honestly
against whatever family they were pre-registered on.
"""

import math
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from g0rd0n.cells import arm as arms
from g0rd0n.cells.arm import Arm, ArmError, Attempt, attempt
from g0rd0n.cells.cell import Tool
from g0rd0n.cells.model import ModelUnavailable, Reply, Turn
from g0rd0n.config import Config
from g0rd0n.cortex import protocol
from g0rd0n.cortex.protocol import Evaluation, Measurement, ProtocolError
from g0rd0n.cortex.wager import (
    NotPreregistered,
    Registration,
    Verdict,
    Wager,
    register,
)
from g0rd0n.instruments import meter
from g0rd0n.instruments.bench import Budget
from g0rd0n.instruments.capability import MINIMUM, margin
from g0rd0n.instruments.meter import Instrument, Role
from g0rd0n.instruments.tasks import Family, Instance, InstanceSet, TaskError, instances
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref
from g0rd0n.ledger import Cost, Ledger

REPO = Path(__file__).resolve().parents[1]

#: Enough of every dimension for 80 instances. The Ledger checks overspend in all six, so an
#: estimate right about money and wrong about tokens still stops a run.
PRICE = Cost(tokens_in=100_000, tokens_out=100_000, usd=1.0, seconds=600.0)

#: Two sizes, forty instances each — `MINIMUM` exactly, so a curve is admissible.
SIZES = (4, 8)

WALL = Instrument(
    name="wall-plug",
    role=Role.PRIMARY,
    covers="the whole machine at the plug, at 1 Hz",
    source="a bench power meter's datasheet",
)

MODEL = Instrument(
    name="loihi-analytic",
    role=Role.ANALYTIC,
    covers="spikes times energy per spike, assuming no host in the loop",
    source="the vendor's published energy-per-synaptic-operation figure",
)


# --- a toy family, so the protocol can be tested without solving anything ----------------


def toy_generate(size: int, seed: int) -> Instance:
    """An instance whose right answer is written on it. The checker still has to be told.

    The size is in the token because `instances` restarts its index at each size, so a token
    built from the seed alone would be identical across sizes — and the fake model below
    recovers the size from what it was asked, to shape a curve.
    """
    return Instance(
        family="TOY",
        size=size,
        seed=seed,
        question=f"Repeat this token and nothing else: t{size}-{seed}",
        data=f"t{size}-{seed}",
    )


def toy_check(instance: Instance, answer: str) -> float:
    return 1.0 if answer.strip() == instance.data else 0.0


TOY = Family(
    slug="TOY",
    what="repeat a token",
    size_is="ignored; the toy family is the same difficulty at every size",
    answers="the token",
    threshold=0.9,
    ceiling_seconds=1.0,
    generate=toy_generate,
    check=toy_check,
)


# --- arms, and a model that answers exactly as well as a test tells it to ----------------


def an_arm(
    name: str = "control",
    *,
    kind: str = arms.CONTROL,
    system: str = "Repeat the token.",
    tuning_joules: float = 0.0,
    tuning_note: str = "",
) -> Arm:
    return Arm(
        name=name,
        kind=kind,
        model="test-model",
        system=system,
        max_tokens=64,
        tuning_joules=tuning_joules,
        tuning_note=tuning_note,
    )


class Answering:
    """A model that gets a stated fraction of each size right, and takes a stated time.

    Right answers come first within a size, which makes the curve exactly reproducible: a test
    that says "0.95 at size 4" gets 38 of 40 correct and can predict the mean. The wrongness is
    a token that is not the answer, so the toy checker scores it zero the way a real one would.
    """

    def __init__(
        self,
        accuracy: Mapping[int, float],
        *,
        seconds: float = 0.0,
        ledger: Ledger | None = None,
    ) -> None:
        self.accuracy = accuracy
        self.seconds = seconds
        self.asked: list[str] = []
        self.systems: list[str] = []
        self.reserved_at_each_call: list[int] = []
        self._ledger = ledger
        self._seen: dict[int, int] = {}

    def reply(
        self,
        *,
        model: str,
        system: str,
        turns: tuple[Turn, ...],
        tools: tuple[Tool, ...],
        max_tokens: int,
    ) -> Reply:
        self.asked.append(turns[0].text)
        self.systems.append(system)
        if self._ledger is not None:
            self.reserved_at_each_call.append(len(self._ledger.open_reservations))

        token = turns[0].text.rsplit(" ", 1)[1]
        size = int(token[1:].split("-", 1)[0])
        index = self._seen.get(size, 0)
        self._seen[size] = index + 1
        right = index < round(self.accuracy.get(size, 0.0) * MINIMUM)
        if self.seconds:
            _spin(self.seconds)
        return Reply(text=token if right else "nope", tokens_in=40, tokens_out=8)


class Breaking:
    """A model that answers `after` instances and then cannot be reached."""

    def __init__(self, after: int) -> None:
        self.after = after
        self.calls = 0

    def reply(
        self,
        *,
        model: str,
        system: str,
        turns: tuple[Turn, ...],
        tools: tuple[Tool, ...],
        max_tokens: int,
    ) -> Reply:
        self.calls += 1
        if self.calls > self.after:
            raise ModelUnavailable("the endpoint did not answer usably")
        return Reply(text=turns[0].text.rsplit(" ", 1)[1], tokens_in=40, tokens_out=8)


def _spin(seconds: float) -> None:
    """Burn wall-clock without sleeping, so a `W` test does not depend on a sleeping clock."""
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        pass


def a_set(count: int = MINIMUM, seed: int = 0) -> InstanceSet:
    return instances(TOY, SIZES, count, seed)


def a_wager(family: Family = TOY, label: str = "toy-separation") -> Wager:
    return Wager(
        label=label,
        question=Ref("question", "charter-0123456789ab"),
        hypothesis=Ref("hypothesis", "h-toy"),
        claim="the candidate clears a larger size than the control arm at the same budget",
        resource="energy, in joules at the wall",
        task_family=f"{family.slug}@{family.version}",
        test="run both arms on the pre-registered instance set and compare cap",
        instrument="a wall-plug meter at 1 Hz, calibrated against a 100 W load",
        kill="the cap margin's 95% interval includes zero",
        price=PRICE,
        prior=0.2,
    )


def a_registration(wager: Wager | None = None) -> Registration:
    """A `Registration` nobody minted. Good enough to build an `Evaluation`, and no further.

    `settle` looks the assertion up in the kernel, so this shortcut buys the pure tests and
    stops exactly where it should — `an_evaluation_cannot_be_recorded_against_a_registration_
    the_kernel_does_not_have` is that boundary, tested.
    """
    return Registration(
        wager=wager if wager is not None else a_wager(),
        tests=1,
        kills=2,
        costs=3,
        document=4,
    )


def measurement(
    arm: Arm,
    accuracy: Mapping[int, float],
    *,
    config: Config,
    joules: float = 1000.0,
    instrument: Instrument = WALL,
    seconds: float = 0.0,
    pool: InstanceSet | None = None,
) -> Measurement:
    """Run one arm against a fresh ledger, and account its joules however the test says."""
    ledger = Ledger(config, session="s-1", campaign="c-1", phase="8c")
    reservation = ledger.reserve("w-toy", PRICE, "test")
    try:
        ran = attempt(
            arm,
            TOY,
            pool if pool is not None else a_set(),
            config=config,
            ledger=ledger,
            model=Answering(accuracy, seconds=seconds),
            reservation=reservation,
        )
    finally:
        ledger.settle(reservation)
    energy = (
        meter.estimated(instrument, joules, 0.2)
        if instrument.role is Role.ANALYTIC
        else meter.session(
            meter.Calibration(instrument, 100.0, 103.0, 0.5, meter.CALIBRATION_SECONDS),
            load_joules=joules,
            idle_before_watts=0.0,
            idle_after_watts=0.0,
            seconds=100.0,
        ).energy
    )
    return Measurement(attempt=ran, energy=energy)


@pytest.fixture
def toy_config(cell_config: Config) -> Config:
    """The Phase 4 config, which already prices `test-model`."""
    return cell_config


# --- the arm --------------------------------------------------------------------------


def test_an_arms_version_is_the_hash_of_its_whole_config(toy_config: Config) -> None:
    """An arm retuned is a different arm, and a differently-prompted arm is a different arm.

    Every field is inside the hash, `tuning_joules` included, because "how hard did you try to
    make the baseline good" is exactly the number that gets adjusted after the fact if nothing
    pins it. And `config_hash` is the same string, so a reader chasing AGENTS.md's phrase and
    a reader chasing this module's land in the same place.
    """
    control = an_arm()
    assert control.config_hash == control.version
    assert len(control.version) == 12

    for other in (
        an_arm(system="Repeat the token, please."),
        an_arm(name="control-2"),
        an_arm(tuning_joules=1.0, tuning_note="swept the temperature"),
    ):
        assert other.version != control.version

    assert an_arm().version == control.version, "the same config is the same arm"


def test_an_arm_declaring_tuning_must_say_what_it_tuned() -> None:
    """Step 2 asks for the figure to be *recorded*, and an uninterpretable figure is not."""
    with pytest.raises(ArmError, match="no note saying what was tuned"):
        an_arm(tuning_joules=1000.0)
    with pytest.raises(ArmError, match="negative energy"):
        an_arm(tuning_joules=-1.0, tuning_note="somehow")


def test_the_shipped_control_arm_loads_and_is_a_transformer() -> None:
    """`bench/baselines/` is a versioned artifact directory, reviewed in a diff like a playbook.

    Asserted about the file this repository actually ships, so the arm cannot drift into
    something the protocol would refuse while the tests pass on a synthetic one.
    """
    shipped = arms.baselines(REPO / "bench" / "baselines")
    assert [baseline.name for baseline in shipped] == ["transformer-control"]

    control = shipped[0]
    assert control.kind == arms.CONTROL
    assert control.tuning_joules == 0.0, "nothing has been tuned, and it says so"
    assert "final line must be the answer" in control.system, (
        "the checkers are strict, so an arm that was never told the format would score near "
        "zero on prose alone — and a separation from that is a separation from a formatting "
        "accident"
    )


def test_an_arm_config_rejects_a_setting_nobody_reads(tmp_path: Path) -> None:
    """Closed keys, like a playbook's and like the config file's."""
    path = tmp_path / "a.toml"
    path.write_text(
        'kind = "transformer"\nmodel = "m"\nsystem = "s"\nmax_tokens = 8\ntemperature = 0.7\n',
        encoding="utf-8",
    )
    with pytest.raises(ArmError, match="unknown setting temperature"):
        arms.load(path)

    path.write_text('kind = "transformer"\nmodel = "m"\n', encoding="utf-8")
    with pytest.raises(ArmError, match="must set max_tokens, system"):
        arms.load(path)


def test_an_arm_cannot_be_run_without_a_reservation(toy_config: Config) -> None:
    """`attempt` takes a `Reservation`, and only `Ledger.reserve` makes one.

    The same trick the runtime uses one layer down, and the reason it matters here is ADR
    0010's open gap: the chain from a model call back to a pre-registered wager runs
    `attempt` → `Reservation` → `cortex.wager.reserve` → `Registration` → `register`, with no
    string anywhere in it that a caller could have typed.
    """
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    model = Answering({4: 1.0, 8: 1.0}, ledger=ledger)
    reservation = ledger.reserve("w-toy", PRICE, "test")
    ran = attempt(
        an_arm(),
        TOY,
        a_set(),
        config=toy_config,
        ledger=ledger,
        model=model,
        reservation=reservation,
    )
    ledger.settle(reservation)

    assert ran.attempted == 2 * MINIMUM
    assert ran.solved == 2 * MINIMUM
    assert set(model.reserved_at_each_call) == {1}, "priced before every call, not after"
    assert ran.cost.usd > 0.0


def test_an_arm_is_shown_the_question_and_never_the_checkers_data(toy_config: Config) -> None:
    """An `Instance` carries two strings, and the arm sees exactly one of them."""
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    model = Answering({4: 1.0, 8: 1.0})
    reservation = ledger.reserve("w-toy", PRICE, "test")
    attempt(
        an_arm(system="A system prompt."),
        TOY,
        a_set(),
        config=toy_config,
        ledger=ledger,
        model=model,
        reservation=reservation,
    )
    ledger.settle(reservation)

    assert all(asked.startswith("Repeat this token") for asked in model.asked)
    assert set(model.systems) == {"A system prompt."}


def test_an_instance_answered_outside_the_wall_clock_ceiling_scores_zero(
    toy_config: Config,
) -> None:
    """§Resource held fixed: exceeding `W` is a failed instance, not a longer run.

    "A paradigm that stays inside `B` by taking a year per instance is not a result about
    anything anyone can use." The arm answers every instance correctly here and still scores
    zero, which is the whole point — `W` is a second fixed resource and not a timeout.
    """
    slow = replace(TOY, ceiling_seconds=0.001)
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    reservation = ledger.reserve("w-toy", PRICE, "test")
    ran = attempt(
        an_arm(),
        slow,
        instances(slow, SIZES, MINIMUM, 0),
        config=toy_config,
        ledger=ledger,
        model=Answering({4: 1.0, 8: 1.0}, seconds=0.005),
        reservation=reservation,
    )
    ledger.settle(reservation)

    assert ran.overran == ran.attempted
    assert ran.solved == 0
    assert all(answered.score == 0.0 for answered in ran.answers)
    assert all(answered.answer for answered in ran.answers), "the answer is kept, and was right"


def test_a_partly_correct_answer_is_not_a_solved_one(toy_config: Config) -> None:
    """`J_solved` is joules per *correct answer*, and T3's checker gives partial credit by F1.

    An arm that half-finishes every instance has an efficiency of nothing per joule, and
    counting a 0.5 as solved would report one. Partial credit belongs on the curve, where it
    moves the mean and therefore `cap`; it does not belong in the denominator of `J_solved`.
    """
    halves = replace(TOY, check=lambda instance, answer: 0.5)
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    reservation = ledger.reserve("w-toy", PRICE, "test")
    ran = attempt(
        an_arm(),
        halves,
        instances(halves, SIZES, MINIMUM, 0),
        config=toy_config,
        ledger=ledger,
        model=Answering({4: 1.0, 8: 1.0}),
        reservation=reservation,
    )
    ledger.settle(reservation)

    assert ran.attempted == 2 * MINIMUM
    assert ran.solved == 0, "half-right is not right"
    assert all(point.mean == pytest.approx(0.5) for point in ran.curve.points)


def test_a_model_that_stops_answering_fails_the_attempt_and_settles_the_reservation(
    toy_config: Config,
) -> None:
    """A refused instance is the arm failing; a dead endpoint is g0rd0n failing.

    Scoring an unreachable endpoint against the arm would put an infrastructure problem into a
    result, so the attempt raises and nothing is recorded. What must still happen is the
    settlement: `evaluate` settles in a `finally`, so a failure halfway through 160 model
    calls costs the run and never leaves a reservation open, quietly shrinking every later
    budget.
    """
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    with pytest.raises(ModelUnavailable):
        protocol.evaluate(
            a_registration(),
            Budget(100.0, 0.0, 1),
            control=an_arm("control"),
            candidate=an_arm("candidate", kind="spiking"),
            family=TOY,
            instances=a_set(),
            account=lambda ran: Measurement(ran, meter.estimated(MODEL, 1000.0, 0.2)),
            config=toy_config,
            ledger=ledger,
            model=Breaking(after=10),
        )
    assert not ledger.open_reservations


def test_an_arm_is_refused_an_instance_set_built_against_another_checker(
    toy_config: Config,
) -> None:
    """The silent failure 8a's `cap` refuses, refused one layer earlier as well."""
    other = replace(TOY, threshold=0.5)
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    reservation = ledger.reserve("w-toy", PRICE, "test")
    with pytest.raises(ArmError, match="pre-registered against"):
        attempt(
            an_arm(),
            TOY,
            instances(other, SIZES, MINIMUM, 0),
            config=toy_config,
            ledger=ledger,
            model=Answering({}),
            reservation=reservation,
        )
    ledger.settle(reservation)


# --- the margin ------------------------------------------------------------------------


def test_two_caps_that_differ_are_not_a_separation(toy_config: Config) -> None:
    """Step 5: the margin's 95% interval has to exclude zero, not merely be non-zero.

    `cap` is a step function of the scores — one instance flipping at the threshold size moves
    it by a whole size — so two arms whose caps differ by a size can be two draws from one
    system. The interval is what tells those apart, and it is why a bench that reported "8 vs
    4, therefore a separation" would be wrong most of the time it looked right.
    """
    near = measurement(an_arm("a"), {4: 1.0, 8: 0.925}, config=toy_config)
    also_near = measurement(an_arm("b"), {4: 1.0, 8: 0.875}, config=toy_config)
    low, high = margin(TOY, near.attempt.curve, also_near.attempt.curve)
    assert low <= 0.0 <= high, "one instance either side of the threshold is not a separation"

    clear = measurement(an_arm("c"), {4: 1.0, 8: 1.0}, config=toy_config)
    behind = measurement(an_arm("d"), {4: 0.2, 8: 0.0}, config=toy_config)
    low, high = margin(TOY, clear.attempt.curve, behind.attempt.curve)
    assert low > 0.0, "clearing every size against clearing none is a separation"
    assert high >= low


def test_the_margin_is_the_same_number_twice(toy_config: Config) -> None:
    """Same curves, same interval — the contract a published margin rests on.

    **This test does not prove the seeding works, and nothing here can.** 8a's
    `the_interval_is_the_same_in_a_second_process` catches an unseeded bootstrap because its
    statistic is a mean, which is continuous and moves with the draws. `cap` is an *ordinal*:
    the resampled difference takes a handful of distinct values, and a 2.5% quantile over 2000
    draws lands in the same mass every time. Replacing the content-hash seed with a bare
    `random.Random()` was tried and this suite stayed green, and a sweep over sixteen
    near-threshold curve pairs found no configuration where it changed the endpoints.

    The seed is still right — an exactly reproducible margin is the point, and the robustness
    that hides the bug here would not hold at a smaller `RESAMPLES` or on a finer size ladder
    — but it is defended by review and by the module docstring rather than by a test, and
    saying so is cheaper than a test tuned to be flaky enough to notice. ADR 0015.
    """
    left = measurement(an_arm("a"), {4: 1.0, 8: 0.95}, config=toy_config)
    right = measurement(an_arm("b"), {4: 1.0, 8: 0.5}, config=toy_config)
    once = margin(TOY, left.attempt.curve, right.attempt.curve)
    assert margin(TOY, left.attempt.curve, right.attempt.curve) == once
    assert all(math.isfinite(end) for end in once)


def test_a_margin_across_two_different_instance_sets_is_refused(toy_config: Config) -> None:
    """Step 3, checked where two curves first meet as well as where two arms do."""
    left = measurement(an_arm("a"), {4: 1.0, 8: 1.0}, config=toy_config)
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    reservation = ledger.reserve("w-toy", PRICE, "test")
    narrow = attempt(
        an_arm("b"),
        TOY,
        instances(TOY, (4, 16), MINIMUM, 0),
        config=toy_config,
        ledger=ledger,
        model=Answering({4: 1.0, 16: 1.0}),
        reservation=reservation,
    )
    ledger.settle(reservation)

    with pytest.raises(TaskError, match="identical instance set"):
        margin(TOY, left.attempt.curve, narrow.curve)


# --- the protocol ----------------------------------------------------------------------


def test_baseline_arm_runs_on_every_evaluation(toy_config: Config) -> None:
    """AGENTS.md §Phase 8, and it is a field rather than a rule somebody remembers.

    Three ways of not having a baseline, and all three are refused: no control field at all
    (a `TypeError` from the dataclass, which is the strongest form the check can take), a
    control that is not a transformer, and the candidate standing in for its own control.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    candidate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config
    )
    budget = Budget(100.0, 0.0, 1)

    with pytest.raises(TypeError):
        Evaluation(registration=a_registration(), budget=budget, candidate=candidate)  # type: ignore[call-arg]

    with pytest.raises(ProtocolError, match="honestly-tuned transformer control arm"):
        Evaluation(
            registration=a_registration(), budget=budget, control=candidate, candidate=control
        )

    with pytest.raises(ProtocolError, match="on both sides"):
        Evaluation(registration=a_registration(), budget=budget, control=control, candidate=control)

    both = Evaluation(
        registration=a_registration(), budget=budget, control=control, candidate=candidate
    )
    assert both.control.arm.kind == arms.CONTROL
    assert [result.arm for result in both.results] == ["control", "candidate"]


def test_the_two_arms_must_have_answered_the_identical_instance_set(toy_config: Config) -> None:
    """Step 3, and the case that matters is the one the sizes agree on.

    Two sets built at the same sizes from different seeds hold different *questions*, and every
    downstream number — the curves, the means, the margin — is the same shape and comparable
    to look at. `InstanceSet.version` hashes the instances rather than the recipe precisely so
    this is checkable, and this is where it is checked.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    elsewhere = measurement(
        an_arm("candidate", kind="spiking"),
        {4: 1.0, 8: 1.0},
        config=toy_config,
        pool=a_set(seed=7),
    )
    assert control.attempt.instances.sizes == elsewhere.attempt.instances.sizes
    assert control.attempt.instances.version != elsewhere.attempt.instances.version

    with pytest.raises(ProtocolError, match="identical instance set"):
        Evaluation(
            registration=a_registration(),
            budget=Budget(100.0, 0.0, 1),
            control=control,
            candidate=elsewhere,
        )


def test_a_candidate_tuned_harder_than_the_control_arm_is_refused(toy_config: Config) -> None:
    """Step 2: a separation measured against a baseline nobody tried to make good is not one.

    The check is on the declared figures, which are inside each arm's version — so the way to
    pass it is to tune the control arm, not to edit a number after the run.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    tuned = measurement(
        an_arm("candidate", kind="spiking", tuning_joules=5.0, tuning_note="swept the decay"),
        {4: 1.0, 8: 1.0},
        config=toy_config,
    )
    with pytest.raises(ProtocolError, match="tune the control arm first"):
        Evaluation(
            registration=a_registration(),
            budget=Budget(100.0, 0.0, 1),
            control=control,
            candidate=tuned,
        )


def test_an_evaluation_on_a_family_the_wager_never_named_is_refused(toy_config: Config) -> None:
    """Step 1 pre-registers the checker version, and this is where that is cashed in."""
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    candidate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config
    )
    stale = replace(a_wager(), task_family="TOY@000000000000")

    with pytest.raises(ProtocolError, match="does not name"):
        Evaluation(
            registration=a_registration(stale),
            budget=Budget(100.0, 0.0, 1),
            control=control,
            candidate=candidate,
        )


def test_a_separation_needs_a_margin_whose_interval_excludes_zero(toy_config: Config) -> None:
    """Step 5, and `inconclusive` is a verdict rather than a shrug.

    Note the second half. A candidate that came out *behind* the control arm also reports
    `inconclusive`, because the Charter says "anything else is `inconclusive`" and mapping a
    negative margin to `refutes` would put a stronger claim into the argument graph than the
    protocol licenses. Recorded as a criticism in ADR 0015, not fixed here.
    """
    control = measurement(an_arm("control"), {4: 0.2, 8: 0.0}, config=toy_config)
    ahead = measurement(an_arm("ahead", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config)
    budget = Budget(100.0, 0.0, 1)

    separation = Evaluation(
        registration=a_registration(), budget=budget, control=control, candidate=ahead
    )
    assert separation.separated
    assert separation.verdict is Verdict.CORROBORATED
    assert "a separation" in separation.finding

    strong = measurement(an_arm("strong"), {4: 1.0, 8: 1.0}, config=toy_config)
    weak = measurement(an_arm("weak", kind="spiking"), {4: 0.2, 8: 0.0}, config=toy_config)
    behind = Evaluation(
        registration=a_registration(), budget=budget, control=strong, candidate=weak
    )
    assert not behind.separated
    assert behind.verdict is Verdict.INCONCLUSIVE
    assert "no separation shown" in behind.finding


def test_a_finding_carries_both_config_hashes_and_both_instruments(toy_config: Config) -> None:
    """AGENTS.md §Phase 8: a result nobody can reproduce must be visibly one.

    Both hashes, because a *comparison* nobody can reproduce needs both halves, and the arm
    that usually goes unrecorded is the baseline.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    candidate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config
    )
    evaluation = Evaluation(
        registration=a_registration(),
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=candidate,
    )

    finding = evaluation.finding
    for side in (control, candidate):
        assert side.arm.config_hash in finding
        assert side.arm.name in finding
    assert WALL.name in finding
    assert evaluation.instances.version in finding
    assert f"{TOY.slug}@{TOY.version}" in finding
    assert "tuning:" in finding

    rendered = evaluation.render()
    assert "margin" in rendered and "verdict" in rendered
    assert evaluation.registration.wager.id in rendered


def test_an_estimate_against_a_measurement_is_flagged_on_the_face_of_the_finding(
    toy_config: Config,
) -> None:
    """The Charter's mixed-comparison rule, carried all the way into what `measures` records.

    On a machine with no wall-plug meter this is the ordinary case, not the exception — see
    `g0rd0n bench meters`. The flag rides in the finding rather than only on the object,
    because the finding is what a person reads out of the kernel a year later.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    modelled = measurement(
        an_arm("candidate", kind="spiking"),
        {4: 1.0, 8: 1.0},
        config=toy_config,
        instrument=MODEL,
    )
    evaluation = Evaluation(
        registration=a_registration(),
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=modelled,
    )

    assert evaluation.mixed
    assert evaluation.finding.startswith("MIXED (estimated vs measured)")
    assert "MIXED" in evaluation.render()

    matched = Evaluation(
        registration=a_registration(),
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=measurement(an_arm("c2", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config),
    )
    assert not matched.mixed
    assert "MIXED" not in matched.finding


def test_an_arm_outside_its_budget_wins_nothing(toy_config: Config) -> None:
    """8b's rule seen through the protocol, and the seam between the two halves of `clears`.

    The margin is computed on scores alone, because scores are what a bootstrap over `cap` can
    resample. So a candidate that outscored the control arm by spending a thousand times the
    joules produces a *positive margin* and a `cap` of `None` — and without a budget clause on
    `separated` the evaluation would report a separation while the result for the winning arm
    reported no capability at all. Step 5 compares "at equal `B`, `P`, and `N`", and this is
    where that phrase is cashed in.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.0}, config=toy_config, joules=1000.0)
    profligate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config, joules=1_000_000.0
    )
    evaluation = Evaluation(
        registration=a_registration(),
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=profligate,
    )

    _, reported = evaluation.results
    assert reported.cap is None
    assert "did not stay inside its budget" in reported.render()

    assert evaluation.margin[0] > 0.0, "on scores alone it looks like a separation"
    assert not evaluation.within_budget
    assert not evaluation.separated
    assert evaluation.verdict is Verdict.INCONCLUSIVE
    assert "candidate did not stay inside the budget" in evaluation.finding


def test_an_evaluation_cannot_be_recorded_against_a_registration_the_kernel_does_not_have(
    toy_config: Config, bridge: Bridge
) -> None:
    """A `Registration` is a frozen dataclass, and `settle` does not take one on trust.

    The type says a caller pre-registered; the lookup says the kernel agrees. This is the same
    check `cortex.wager.record` has always made, and it is worth a test here because 8c is the
    first module that hands `record` a registration it did not watch being minted.
    """
    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    candidate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config
    )
    evaluation = Evaluation(
        registration=a_registration(),
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=candidate,
    )
    with pytest.raises(NotPreregistered):
        protocol.settle(bridge, evaluation)


def test_an_evaluation_commits_one_measures_carrying_the_config_hashes(
    toy_config: Config, bridge: Bridge
) -> None:
    """The whole round trip against a real `knk`: register, run, record, read it back.

    One `measures` for the pair, not one per arm and not one per instance. The Charter asks for
    the per-instance records in the *result*; the argument graph gets the claim the experiment
    settles, and an arm's 80 answers are not 80 claims about the world.
    """
    wager = a_wager()
    _hypothesise(bridge, wager)
    registration = register(bridge, wager)

    control = measurement(an_arm("control"), {4: 1.0, 8: 0.5}, config=toy_config)
    candidate = measurement(
        an_arm("candidate", kind="spiking"), {4: 1.0, 8: 1.0}, config=toy_config
    )
    evaluation = Evaluation(
        registration=registration,
        budget=Budget(100.0, 0.0, 1),
        control=control,
        candidate=candidate,
    )
    recorded = protocol.settle(bridge, evaluation)

    assert recorded.verdict is evaluation.verdict
    measures = [
        assertion
        for assertion in bridge.assertions_for(wager.experiment)
        if bridge.predicate_of(assertion.predicate) == "measures"
    ]
    assert len(measures) == 1

    provenance = bridge.provenance_for(measures[0].id)
    assert provenance is not None
    for side in (control, candidate):
        assert side.arm.config_hash in provenance.method

    with pytest.raises(Exception, match="already been settled"):
        protocol.settle(bridge, evaluation)


def test_evaluate_runs_the_control_arm_first_and_settles_whatever_happens(
    toy_config: Config,
) -> None:
    """One reservation for both arms, control first, settled in a `finally`.

    Control first because if the money runs out halfway the arm that got measured should be
    the one that would otherwise be quietly dropped. One reservation because the wager
    pre-registered one price for finding this out, and splitting it would let the second half
    be re-priced after seeing the first.
    """
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    order: list[str] = []

    def account(ran: Attempt) -> Measurement:
        order.append(ran.arm.name)
        return Measurement(
            attempt=ran,
            energy=meter.estimated(MODEL, 1000.0, 0.2),
        )

    evaluation = protocol.evaluate(
        a_registration(),
        Budget(100.0, 0.0, 1),
        control=an_arm("control"),
        candidate=an_arm("candidate", kind="spiking"),
        family=TOY,
        instances=a_set(),
        account=account,
        config=toy_config,
        ledger=ledger,
        model=Answering({4: 1.0, 8: 1.0}),
    )

    assert order == ["control", "candidate"]
    assert not ledger.open_reservations, "settled in a finally, whatever happened"
    assert evaluation.control.arm.name == "control"
    assert not evaluation.mixed, "both arms modelled is not mixed; both were estimates"


def test_evaluate_refuses_an_arm_compared_with_itself(toy_config: Config) -> None:
    """Refused before the reservation, so a pointless comparison costs nothing."""
    ledger = Ledger(toy_config, session="s-1", campaign="c-1", phase="8c")
    with pytest.raises(ArmError, match="both arms of its own comparison"):
        protocol.evaluate(
            a_registration(),
            Budget(100.0, 0.0, 1),
            control=an_arm("control"),
            candidate=an_arm("control"),
            family=TOY,
            instances=a_set(),
            account=lambda ran: Measurement(ran, meter.estimated(MODEL, 1.0, 0.2)),
            config=toy_config,
            ledger=ledger,
            model=Answering({}),
        )
    assert not ledger.open_reservations


def _hypothesise(bridge: Bridge, wager: Wager) -> None:
    """Put the wager's hypothesis under its question, so `register` can find a parent."""
    bridge.hypothesise(
        Claim(wager.question, "hypothesises", wager.hypothesis, 0.2),
        Provenance(Ref("source", "test-fixture"), "a test standing a question up"),
    )
