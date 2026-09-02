"""The meter and what it licenses: joules with a bar on them, and a `cap` with a budget.

Phase 8b's half of AGENTS.md §Phase 8. Three of the four minimum tests are here —
`energy_measurement_reports_an_error_bar`,
`measured_and_estimated_energy_are_never_compared_without_a_flag` and
`result_carries_its_config_hash_and_instrument`. The fourth,
`baseline_arm_runs_on_every_evaluation`, is about a run loop with two arms in it, and it
arrives with them in 8c.

No kernel, no network, no model, no meter: every test here is a pure function of values, and
the two that touch a filesystem build a fake `sysfs` under `tmp_path`. That is deliberate. A
bench AGENTS.md asks to be "small enough that one person can verify it is not lying" should
not need hardware to check that it refuses correctly, and the machine this was written on
cannot read a joule at all — which is precisely the case the refusals exist for.
"""

from pathlib import Path

import pytest

from g0rd0n.instruments import bench, meter, tasks
from g0rd0n.instruments.capability import Point, curve
from g0rd0n.instruments.meter import (
    Basis,
    Calibration,
    Instrument,
    Joules,
    MeterError,
    Role,
)
from g0rd0n.instruments.tasks import TaskError

T1 = tasks.family("T1")

WALL = Instrument(
    name="wall-plug",
    role=Role.PRIMARY,
    covers="the whole machine at the plug, at 1 Hz",
    source="a bench power meter's datasheet",
)

RAPL = Instrument(
    name="rapl:package-0",
    role=Role.SECONDARY,
    covers="the CPU package domain only",
    source="Linux powercap sysfs",
)

MODEL = Instrument(
    name="loihi-analytic",
    role=Role.ANALYTIC,
    covers="spikes times energy per spike, assuming no host in the loop",
    source="the vendor's published energy-per-synaptic-operation figure",
)


def calibration(observed: float = 103.0, resolution: float = 0.5) -> Calibration:
    """A meter checked against a 100 W resistive load for the Charter's sixty seconds."""
    return Calibration(
        instrument=WALL,
        nominal_watts=100.0,
        observed_watts=observed,
        resolution_watts=resolution,
        seconds=meter.CALIBRATION_SECONDS,
    )


def run(load: float = 4000.0, idle: float = 20.0, seconds: float = 100.0) -> meter.Session:
    """A hundred seconds under load, with a 20 W idle baseline either side of it."""
    return meter.session(
        calibration(),
        load_joules=load,
        idle_before_watts=idle,
        idle_after_watts=idle,
        seconds=seconds,
    )


def points(*sizes_and_scores: tuple[int, float]) -> tuple[Point, ...]:
    """A curve's points: forty identical scores at each size, which is `MINIMUM` exactly."""
    return tuple(
        Point(size=size, scores=tuple([score] * meter_minimum()))
        for size, score in sizes_and_scores
    )


def meter_minimum() -> int:
    from g0rd0n.instruments.capability import MINIMUM

    return MINIMUM


def spent(
    primary: Joules | None = None,
    *,
    attempted: int = 40,
    solved: int = 40,
    secondary: tuple[Joules, ...] = (),
    preparation: Joules | None = None,
    population: int = 1,
) -> bench.Expenditure:
    return bench.expenditure(
        "control",
        primary if primary is not None else run().energy,
        attempted=attempted,
        solved=solved,
        seconds=100.0,
        secondary=secondary,
        preparation=preparation,
        population=population,
    )


def result(
    *,
    budget: bench.Budget | None = None,
    scores: tuple[tuple[int, float], ...] = ((8, 1.0), (16, 1.0)),
    expenditure: bench.Expenditure | None = None,
    config_hash: str = "0123456789ab",
) -> bench.Result:
    return bench.Result(
        arm="control",
        family=T1,
        curve=curve(T1, points(*scores)),
        budget=budget if budget is not None else bench.Budget(200.0, 0.0, 1),
        spent=expenditure if expenditure is not None else spent(),
        config_hash=config_hash,
    )


# --- the meter -------------------------------------------------------------------------


def test_a_session_without_a_calibration_produces_no_energy_result() -> None:
    """CHARTER.md §Energy instrument: not a result with a wide bar, a refusal.

    Two shapes of the same failure. A session with no meter check at all is refused outright,
    and a check shorter than the Charter's sixty seconds is refused too — a meter read against
    a known load for two seconds has measured its own transient, not its deviation.

    The distinction the Charter is drawing matters more than it looks. A wide error bar is
    still a number: it can be quoted, argued down, or averaged into a table with narrow ones.
    A refusal cannot.
    """
    with pytest.raises(MeterError, match="not a result with a wide bar, a refusal"):
        meter.session(
            None, load_joules=4000.0, idle_before_watts=20.0, idle_after_watts=20.0, seconds=100.0
        )

    with pytest.raises(MeterError, match="60s"):
        Calibration(
            instrument=WALL,
            nominal_watts=100.0,
            observed_watts=103.0,
            resolution_watts=0.5,
            seconds=2.0,
        )


def test_energy_measurement_reports_an_error_bar() -> None:
    """AGENTS.md §Phase 8, and it holds down to the meter that agrees with the load exactly.

    A calibration reading exactly its nominal load does not license a claim of a perfect
    instrument: the bar floors at the meter's least count, which is the smallest difference it
    could have displayed. Without that floor the honest-looking case — a meter that agrees —
    is the one that produces `0 ± 0 J`.
    """
    assert run().energy.error > 0.0
    assert meter.estimated(MODEL, 1200.0, 0.25).error == pytest.approx(300.0)

    exact = Calibration(
        instrument=WALL,
        nominal_watts=100.0,
        observed_watts=100.0,
        resolution_watts=0.5,
        seconds=meter.CALIBRATION_SECONDS,
    )
    assert exact.relative_error == pytest.approx(0.005), "the least count is the floor"

    with pytest.raises(MeterError, match="claims a perfect instrument"):
        Joules(1000.0, 0.0, WALL)


def test_an_analytic_estimate_states_its_model_its_assumptions_and_its_source() -> None:
    """CHARTER.md §Energy instrument, and the labelling that goes with it.

    An estimate is admissible — it is the only evidence available about a substrate this bench
    cannot run — but only carrying what it rests on, and only labelled `estimated`. The two
    refusals are the ones that let an estimate stop looking like one: an instrument with
    nothing behind it, and an estimate minted against a meter that was never read.
    """
    estimate = meter.estimated(MODEL, 1200.0, 0.25)
    assert estimate.basis is Basis.ESTIMATED
    assert "assuming no host" in estimate.instrument.covers
    assert estimate.instrument.source

    with pytest.raises(MeterError, match="must declare its source"):
        Instrument(name="hand-wave", role=Role.ANALYTIC, covers="joules, roughly", source="  ")
    with pytest.raises(MeterError, match="must declare its covers"):
        Instrument(name="hand-wave", role=Role.ANALYTIC, covers="", source="a paper")

    with pytest.raises(MeterError, match="cannot be run on this bench"):
        meter.estimated(WALL, 1200.0, 0.25)
    with pytest.raises(MeterError, match="no error bar"):
        meter.estimated(MODEL, 1200.0, 0.0)


def test_an_idle_subtraction_keeps_the_scale_error_and_refuses_a_second_meter() -> None:
    """A calibration deviation is a scale error, so it survives `load - idle` unchanged.

    And the subtraction is confined to one meter. Subtracting one instrument's reading from
    another's would arrive at a bare number with no flag on it, which is the mixed comparison
    with the label filed off — `bench.compare` is the only place two instruments meet.
    """
    session = run(load=4000.0, idle=20.0, seconds=100.0)
    assert session.raw.value == pytest.approx(4000.0)
    assert session.idle_joules == pytest.approx(2000.0)
    assert session.energy.value == pytest.approx(2000.0)
    assert session.energy.relative_error == session.raw.relative_error

    other = Joules(500.0, 0.03, RAPL)
    with pytest.raises(MeterError, match="compared by"):
        session.raw.minus(other)


def test_a_session_whose_idle_baseline_moved_under_the_run_is_refused() -> None:
    """The Charter asks for both baselines "under the same ambient conditions".

    A machine that idled at 20 W before the run and 40 W after did not hold ambient
    conditions, and the subtraction between them is not an idle subtraction — it is a choice
    of which baseline flatters the result, made after seeing both.
    """
    with pytest.raises(MeterError, match="drift"):
        meter.session(
            calibration(),
            load_joules=4000.0,
            idle_before_watts=20.0,
            idle_after_watts=40.0,
            seconds=100.0,
        )


def test_a_run_that_drew_less_than_idle_is_refused_rather_than_reported_as_negative() -> None:
    """A negative idle-subtracted energy is a statement about the baseline, never about the run."""
    session = meter.session(
        calibration(),
        load_joules=100.0,
        idle_before_watts=20.0,
        idle_after_watts=20.0,
        seconds=100.0,
    )
    assert session.raw.value == pytest.approx(100.0)
    with pytest.raises(MeterError, match="below the"):
        _ = session.energy


def test_a_counter_that_wrapped_is_not_a_negative_reading() -> None:
    """RAPL counters wrap, and a long enough session will see one wrap.

    The naive subtraction of two cumulative reads returns a negative energy across a wrap —
    or, if the run was long, a small positive one that looks entirely plausible. That second
    case is the reason this is a function with a test rather than a subtraction inline.
    """
    assert meter.delta(10.0, 40.0, wraps_at=100.0) == pytest.approx(30.0)
    assert meter.delta(90.0, 20.0, wraps_at=100.0) == pytest.approx(30.0)
    with pytest.raises(MeterError, match="no stated range"):
        meter.delta(90.0, 20.0, wraps_at=0.0)


def test_a_counter_says_why_it_cannot_be_read_before_a_run_rather_than_during_one(
    tmp_path: Path,
) -> None:
    """`unusable` is asked before a session, because the answer is usually "you are not root".

    `energy_uj` has been root-only since CVE-2020-8694, so on most machines a counter that
    looks present cannot be read. Discovering that at the end of a measured run is discovering
    it after the run has to be thrown away.
    """
    domain = tmp_path / "intel-rapl:0"
    domain.mkdir()
    (domain / "name").write_text("package-0", encoding="utf-8")
    (domain / "max_energy_range_uj").write_text("65532610987", encoding="utf-8")

    counter = meter.Rapl(domain)
    assert counter.label == "package-0"
    assert counter.instrument.role is Role.SECONDARY
    assert counter.unusable(), "no energy_uj at all is a reason, not a crash"

    (domain / "energy_uj").write_text("12500000", encoding="utf-8")
    assert counter.unusable() is None
    assert counter.read() == pytest.approx(12.5)
    assert counter.wraps_at == pytest.approx(65532.610987)

    (domain / "energy_uj").write_text("not a number", encoding="utf-8")
    assert counter.unusable(), "a counter holding prose is unusable, and says so"


def test_counters_are_enumerated_without_reading_them(tmp_path: Path) -> None:
    """Enumeration is a directory listing, so it works on a machine that refuses every read.

    Including this one: the real `/sys/class/powercap` is listed as well, which must not raise
    whether it holds two domains or does not exist at all.
    """
    for name in ("intel-rapl:0", "intel-rapl:0:0"):
        domain = tmp_path / name
        domain.mkdir()
        (domain / "energy_uj").write_text("1", encoding="utf-8")
    (tmp_path / "not-a-domain").mkdir()

    found = meter.counters(tmp_path)
    assert [counter.domain.name for counter in found] == ["intel-rapl:0", "intel-rapl:0:0"]
    assert meter.counters(tmp_path / "nowhere") == ()

    for counter in meter.counters():
        assert counter.instrument.role is Role.SECONDARY


def test_a_model_is_not_calibrated_against_a_resistive_load() -> None:
    """An analytic instrument has no meter to check, and states its own uncertainty instead."""
    with pytest.raises(MeterError, match="is analytic"):
        Calibration(
            instrument=MODEL,
            nominal_watts=100.0,
            observed_watts=100.0,
            resolution_watts=0.5,
            seconds=meter.CALIBRATION_SECONDS,
        )


# --- what may be reported ----------------------------------------------------------------


def test_counters_are_never_reported_alone() -> None:
    """CHARTER.md §Energy instrument: alongside a wall-plug meter, never instead of one.

    The refusal is worth more than it looks. Counters are the instrument a machine always has
    and a wall meter is the one it usually does not, so the path of least resistance for any
    bench is to quote RAPL and call it the run's energy — which reports the joules of whichever
    part of the machine happened to be easiest to instrument.
    """
    with pytest.raises(TaskError, match="cannot carry a run on its own"):
        bench.expenditure(
            "control", Joules(2000.0, 0.03, RAPL), attempted=40, solved=40, seconds=100.0
        )

    with pytest.raises(TaskError, match="reported as a secondary"):
        spent(secondary=(Joules(500.0, 0.03, WALL),))

    with pytest.raises(TaskError, match="has no counters"):
        bench.expenditure(
            "loihi",
            meter.estimated(MODEL, 1200.0, 0.25),
            attempted=40,
            solved=40,
            seconds=100.0,
            secondary=(Joules(500.0, 0.03, RAPL),),
        )


def test_measured_and_estimated_energy_are_never_compared_without_a_flag() -> None:
    """AGENTS.md §Phase 8, and CHARTER.md §Energy instrument.

    The flag is derived from the two bases rather than passed in, so there is no argument a
    caller can leave out and none they can set to `False`; and it is in `__str__`, so it is on
    the face of the comparison rather than an attribute somebody has to think to read.

    Note what is *not* being tested: that a mixed comparison is refused. The Charter says a
    candidate that cannot be run here "is evaluated by analytic estimate under the same
    protocol, and every comparison it appears in is flagged as mixed" — refusing it outright
    would make the only available evidence about neuromorphic substrates unreportable.
    """
    measured = run().energy
    estimate = meter.estimated(MODEL, 1200.0, 0.25)

    mixed = bench.compare(estimate, measured)
    assert mixed.mixed
    assert "MIXED" in str(mixed)
    assert f"{Basis.ESTIMATED} vs {Basis.MEASURED}" in str(mixed)

    matched = bench.compare(measured, run(load=3000.0).energy)
    assert not matched.mixed
    assert "MIXED" not in str(matched)


def test_a_comparison_reports_a_ratio_with_the_two_bars_in_quadrature() -> None:
    """Two instruments' calibration deviations are independent, unlike one meter's own.

    `Joules.minus` keeps a scale error unchanged because it is the same error on both terms;
    a ratio across two instruments adds theirs in quadrature. Both choices are stated where
    they are made, because getting either backwards changes every bar the bench reports.
    """
    comparison = bench.compare(Joules(2000.0, 0.03, WALL), Joules(1000.0, 0.04, MODEL))
    assert comparison.ratio == pytest.approx(2.0)
    assert comparison.relative_error == pytest.approx((0.03**2 + 0.04**2) ** 0.5)
    assert comparison.separated, "2000 ± 60 J and 1000 ± 40 J do not overlap"

    close = bench.compare(Joules(1000.0, 0.10, WALL), Joules(1050.0, 0.10, MODEL))
    assert not close.separated
    assert "bars overlap" in str(close)


def test_the_budget_test_divides_by_attempted_and_the_efficiency_report_by_solved() -> None:
    """CHARTER.md §Energy metric: the two denominators, and why they are not the same one.

    Attempted for the budget, so a system cannot come in under `B` by declining the instances
    it expects to fail. Solved for `J_solved`, so a system that answers fast and wrong is
    charged for the answers it got wrong. Using either for both is the cheapest way to make a
    bench flatter an arm.
    """
    partial = spent(attempted=40, solved=10)
    assert partial.per_attempted.value == pytest.approx(50.0)
    assert partial.j_solved is not None
    assert partial.j_solved.value == pytest.approx(200.0)

    assert partial.within(bench.Budget(50.0, 0.0, 1))
    assert not partial.within(bench.Budget(49.0, 0.0, 1))


def test_a_run_with_nothing_solved_reports_its_joules_and_no_j_solved() -> None:
    """`k = 0` is a real state. An efficiency for a system that solved nothing is not."""
    nothing = spent(attempted=40, solved=0)
    assert nothing.j_solved is None
    assert nothing.per_attempted.value == pytest.approx(50.0)
    assert "nothing solved" in str(nothing)


def test_p_over_n_is_reported_beside_b_and_no_preparation_phase_is_not_zero() -> None:
    """A paradigm that learns online has no `P`, which is a different claim from `P = 0`.

    The Charter chartered T2 precisely so that adaptation cannot be hidden in the preparation
    budget, so "there was no preparation phase" has to be sayable and has to be distinguishable
    from "the preparation happened to be free".
    """
    online = spent()
    assert online.amortised is None
    assert "no preparation phase" in result(expenditure=online).render()

    trained = spent(preparation=Joules(1_000_000.0, 0.03, WALL), population=1000)
    assert trained.amortised is not None
    assert trained.amortised.value == pytest.approx(1000.0)
    assert "N=1000" in result(expenditure=trained).render()


def test_a_wall_over_counters_ratio_is_stated_for_the_run() -> None:
    """CHARTER.md §Energy instrument asks for the ratio, and the ratio needs both halves.

    A ratio near one on a machine with an accelerator in it means the counters are seeing more
    than they can see, not that the meter agrees with them.
    """
    both = spent(secondary=(Joules(800.0, 0.02, RAPL),))
    assert [name for name, _ in both.ratios] == ["rapl:package-0"]
    assert both.ratios[0][1] == pytest.approx(2.5)
    assert "wall/rapl:package-0" in result(expenditure=both).render()


def test_result_carries_its_config_hash_and_instrument() -> None:
    """AGENTS.md §Phase 8: a result nobody can reproduce must be visibly a result nobody can.

    The hash is required at construction rather than defaulted, because the default value for
    "which configuration produced this" is the one nobody notices is missing until the result
    is in a table and the run is a month gone.
    """
    reported = result()
    assert reported.config_hash == "0123456789ab"
    assert reported.instrument == WALL
    assert reported.basis is Basis.MEASURED

    rendered = reported.render()
    assert "0123456789ab" in rendered
    assert WALL.name in rendered
    assert WALL.covers in rendered

    with pytest.raises(TaskError, match="hash of the config"):
        result(config_hash="   ")


def test_a_cap_is_never_reported_without_the_budget_it_was_measured_at() -> None:
    """CHARTER.md §Capability metric: `cap` without its budget is not a result.

    Phase 8a's `capability.cap` computes the score half and its own docstring says quoting it
    alone would be quoting a capability with no budget beside it. This is the type that closes
    that: there is no field to leave out, and no rendering that prints the headline without
    `B`, `P`, `N`, the instrument, and the curve the number came off.
    """
    rendered = result().render()
    assert "cap            16" in rendered
    assert "B=200 J/instance" in rendered
    assert "P=0 J over N=1" in rendered
    assert "n=8" in rendered and "n=16" in rendered, "a curve, never a single accuracy"
    assert "per instance attempted" in rendered

    with pytest.raises(TaskError, match="the joules it spent"):
        bench.Result(
            arm="candidate",
            family=T1,
            curve=curve(T1, points((8, 1.0), (16, 1.0))),
            budget=bench.Budget(200.0, 0.0, 1),
            spent=spent(),
            config_hash="0123456789ab",
        )


def test_an_arm_outside_its_budget_has_no_cap_even_when_its_scores_clear() -> None:
    """A size clears when the scores clear *and* the instances were answered inside `B`.

    An arm that beat the threshold by spending more joules than it registered has not cleared
    anything — it has shown what it could do with a budget nobody gave it. So the answer is no
    `cap` at all rather than a `cap` with a caveat attached, because a caveat is the part that
    gets dropped when the number is quoted somewhere else.
    """
    generous = result(budget=bench.Budget(200.0, 0.0, 1))
    assert generous.within_budget
    assert generous.cap == 16

    mean = result(budget=bench.Budget(10.0, 0.0, 1))
    assert not mean.within_budget
    assert mean.cap is None
    assert "did not stay inside its budget" in mean.render()

    prepared = result(
        budget=bench.Budget(200.0, 500.0, 1),
        expenditure=spent(preparation=Joules(9000.0, 0.03, WALL)),
    )
    assert prepared.cap is None, "P is half the budget and is tested like the other half"


def test_a_cap_stops_being_defined_when_the_smallest_size_fails() -> None:
    """`None`, not zero: zero is a size somebody could have measured and this arm did not."""
    assert result(scores=((8, 0.0), (16, 0.0))).cap is None
    assert (
        "the smallest measured size does not clear"
        in result(scores=((8, 0.0),) * 1 + ((16, 0.0),)).render()
    )
    assert result(scores=((8, 1.0), (16, 0.0))).cap == 8


def test_a_budget_is_refused_before_it_can_be_registered() -> None:
    """The three fields the Charter fixes, and the three ways of not fixing them."""
    with pytest.raises(TaskError, match="not a budget, it is a ban"):
        bench.Budget(0.0, 0.0, 1)
    with pytest.raises(TaskError, match="cannot be negative"):
        bench.Budget(100.0, -1.0, 1)
    with pytest.raises(TaskError, match="N must be at least 1"):
        bench.Budget(100.0, 100.0, 0)
