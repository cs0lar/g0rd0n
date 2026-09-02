"""Energy instruments: what read the joules, how far off it was, and whether anything read it.

`CHARTER.md` §Energy instrument names a wall-plug meter as primary, on-die counters as
secondary and never alone, and analytic models for substrates that cannot be run on this
bench. This module is those three roles, the calibration that licenses a reading, and the one
type a joule figure is allowed to travel in.

**A joule figure carries its error bar and its basis, or it does not exist.** The two routes
to one are a `Session`, which cannot be built without a `Calibration`, and `estimated`, which
needs a model, its assumptions, its source, and a stated uncertainty. There is no path to a
bare float that has forgotten which of those it came from, which is what makes
`measured_and_estimated_energy_are_never_compared_without_a_flag` enforceable one layer up —
the flag cannot be lost if the label was never separable from the number.

**No calibration, no result — a refusal, not a wide bar.** The Charter is explicit, and the
distinction is the whole point: a wide bar is a measurement somebody can still quote, argue
down, or average away, and a session whose meter was never checked against a known load did
not measure anything. `CALIBRATION_SECONDS` is the Charter's sixty, and a shorter calibration
is refused for the same reason.

**The error bar has a floor, and the floor is the meter's least count.** The Charter says the
deviation from the known load is the session's error bar, and a meter that happens to agree
with the load to the digit it displays would otherwise report `± 0`, which is a claim of a
perfect instrument. The bar is `max(deviation, resolution)`, so the number a meter cannot
resolve is the smallest error it can claim.

**A relative error passes through an idle subtraction unchanged, and that is a modelling
choice.** A calibration deviation is a *scale* error — the meter reads some percent high or
low — and a scale error survives `load - idle` as the same percent. It is stated here rather
than hidden in the arithmetic because the choice has a known weakness: it says nothing about
the meter's noise, so a load barely above idle gets a difference with a proportionally tiny
bar. See ADR 0014. `minus` refuses two different instruments outright, so the choice can never
be stretched across a comparison — that path exists only in `bench.compare`, which flags.

**RAPL is here to be refused as a primary.** It is shipped because "secondary, never alone" is
worth having as a running refusal rather than a sentence, and because `bench meters` should be
able to tell an operator what this machine actually has. On the machine this was written on it
has been root-only since CVE-2020-8694, which `unusable` reports rather than discovering at
the moment a measurement was supposed to happen.

Deletion criterion: this module holds the wager that a joule figure nobody calibrated is not a
measurement. Delete it and `a_session_without_a_calibration_produces_no_energy_result`,
`energy_measurement_reports_an_error_bar` and `an_analytic_estimate_states_its_model_its_
assumptions_and_its_source` lose their verdicts, and an energy number goes back to being
whatever the last script printed.

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

#: The Charter's calibration window: a known resistive load, read for sixty seconds.
CALIBRATION_SECONDS = 60.0

#: How far the idle baselines taken before and after a session may differ, as a fraction of
#: the larger, before the subtraction between them stops meaning anything. The Charter asks
#: for both under "the same ambient conditions"; this is what that sentence costs.
DRIFT = 0.10

#: Where the kernel exposes RAPL. The `intel-rapl` name is the interface's, not the vendor's:
#: AMD parts report through the same powercap tree.
RAPL_ROOT = Path("/sys/class/powercap")


class MeterError(Exception):
    """A joule figure is not one this bench is allowed to report."""


class Basis(StrEnum):
    """Whether anything measured this number. Closed, and it appears in every result.

    The Charter labels analytic figures `estimated` in the result assertion; this is that
    label, as a type rather than a string somebody remembered to set.
    """

    MEASURED = "measured"
    ESTIMATED = "estimated"


class Role(StrEnum):
    """What kind of instrument produced a number, per `CHARTER.md` §Energy instrument."""

    #: A wall-plug meter across the whole machine. The only role admissible on its own.
    PRIMARY = "primary"
    #: On-die counters — RAPL, NVML. Reported alongside a primary and never instead of one.
    SECONDARY = "secondary"
    #: A model, for a substrate this bench cannot run. Produces estimates, never measurements.
    ANALYTIC = "analytic"


#: Role to basis, as a table rather than an `if`, so that "an analytic figure is an estimate"
#: is a line a reviewer reads instead of a branch a reviewer reconstructs.
BASIS: dict[Role, Basis] = {
    Role.PRIMARY: Basis.MEASURED,
    Role.SECONDARY: Basis.MEASURED,
    Role.ANALYTIC: Basis.ESTIMATED,
}


@dataclass(frozen=True)
class Instrument:
    """What produced a joule figure: its name, its role, what it can see, and what it rests on.

    `covers` is the honest scope — "the whole machine at the plug", "CPU package only", or, for
    an analytic model, what it models and what it assumes. `source` is the datasheet, kernel
    interface, or citation behind it. Both are required for every role, because the failure
    they prevent is an instrument that turns out, after the number is in a table, to have been
    missing the accelerator all along.
    """

    name: str
    role: Role
    covers: str
    source: str

    def __post_init__(self) -> None:
        for field in ("name", "covers", "source"):
            if not str(getattr(self, field)).strip():
                raise MeterError(
                    f"an instrument must declare its {field}; CHARTER.md §Energy instrument "
                    "requires the model, its assumptions and its source to travel with the "
                    "number, and a nameless instrument is a number with no provenance"
                )

    @property
    def basis(self) -> Basis:
        return BASIS[self.role]

    def __str__(self) -> str:
        return f"{self.name} ({self.role}, {self.basis})"


@dataclass(frozen=True)
class Calibration:
    """A meter read a known load, and this is how far off it was.

    `resolution_watts` is the meter's least count — the smallest difference it can display.
    It is here because it is the floor under the error bar, and a meter that cannot state its
    resolution cannot state an error bar either.
    """

    instrument: Instrument
    nominal_watts: float
    observed_watts: float
    resolution_watts: float
    seconds: float

    def __post_init__(self) -> None:
        if self.instrument.role is Role.ANALYTIC:
            raise MeterError(
                f"{self.instrument.name} is analytic, and a model is not calibrated against a "
                "resistive load; an estimate states its own uncertainty instead"
            )
        if self.nominal_watts <= 0.0:
            raise MeterError("a calibration load must draw a known, positive number of watts")
        if self.observed_watts < 0.0 or self.resolution_watts <= 0.0:
            raise MeterError(
                "a calibration must state what the meter read and the least count it reads in"
            )
        if self.seconds < CALIBRATION_SECONDS:
            raise MeterError(
                f"{self.instrument.name} was read against the known load for {self.seconds:g}s "
                f"and CHARTER.md §Energy instrument asks for {CALIBRATION_SECONDS:g}s; a "
                "shorter window measures the meter's transient rather than its deviation"
            )

    @property
    def relative_error(self) -> float:
        """The session's error bar, as a fraction of reading, floored at the least count.

        A deviation of exactly zero is a meter agreeing with the load to the digit it happens
        to display, not a perfect meter, so the resolution is the smallest bar it may claim.
        """
        deviation = abs(self.observed_watts - self.nominal_watts)
        return max(deviation, self.resolution_watts) / self.nominal_watts


@dataclass(frozen=True)
class Joules:
    """An energy figure, its error bar, and the instrument that stands behind it.

    Built by `measured` or `estimated` and by nothing else worth doing. The dataclass is
    reachable, as `Reservation` and `Registration` are, and constructing one by hand is the
    same act as writing a receipt for a purchase nobody made.
    """

    value: float
    relative_error: float
    instrument: Instrument

    def __post_init__(self) -> None:
        if self.relative_error <= 0.0:
            raise MeterError(
                f"{self.instrument.name}: an energy figure with no error bar claims a perfect "
                "instrument. AGENTS.md §Phase 8: energy measurement reports an error bar."
            )

    @property
    def basis(self) -> Basis:
        return self.instrument.basis

    @property
    def error(self) -> float:
        """The bar, in joules."""
        return abs(self.value) * self.relative_error

    @property
    def interval(self) -> tuple[float, float]:
        return (self.value - self.error, self.value + self.error)

    def minus(self, other: "Joules") -> "Joules":
        """Idle subtraction, and the only subtraction there is.

        Refuses two different instruments. Subtracting one meter's reading from another's is
        the mixed comparison wearing the costume of arithmetic, and it would arrive at a bare
        number with no flag on it — `bench.compare` is the only place two instruments meet.
        """
        if other.instrument != self.instrument:
            raise MeterError(
                f"cannot subtract {other.instrument.name} from {self.instrument.name}: an idle "
                "baseline is subtracted from the load the same meter read. Two instruments are "
                "compared by `bench.compare`, which says so on the face of the comparison."
            )
        return Joules(self.value - other.value, self.relative_error, self.instrument)

    def per(self, count: int) -> "Joules":
        """Joules per instance. A count is exact, so the relative error is unchanged."""
        if count <= 0:
            raise MeterError(f"cannot divide {self.value:g} J over {count} instances")
        return Joules(self.value / count, self.relative_error, self.instrument)

    def __str__(self) -> str:
        return f"{self.value:.4g} ± {self.error:.3g} J ({self.basis}, {self.instrument.name})"


@dataclass(frozen=True)
class Session:
    """One calibrated measurement window: the load, the two idle baselines, the duration.

    Everything `CHARTER.md` §Energy metric asks to be reported alongside `J_solved` is a field
    here, so a report cannot quote the idle-subtracted figure while dropping the un-subtracted
    total that would let a reader check it.

    The two idle baselines are the Charter's "immediately before and immediately after under
    the same ambient conditions". They are both kept, and a session whose ambient conditions
    moved more than `DRIFT` between them is refused: a subtraction against an idle that
    changed under the run is not idle-subtracted, it is idle-flavoured.
    """

    calibration: Calibration
    load_joules: float
    idle_before_watts: float
    idle_after_watts: float
    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0.0:
            raise MeterError("a measurement session has a duration")
        if self.load_joules < 0.0 or min(self.idle_before_watts, self.idle_after_watts) < 0.0:
            raise MeterError("a meter does not read negative energy")
        largest = max(self.idle_before_watts, self.idle_after_watts)
        drift = abs(self.idle_after_watts - self.idle_before_watts)
        if largest > 0.0 and drift / largest > DRIFT:
            raise MeterError(
                f"{self.instrument.name}: idle was {self.idle_before_watts:g} W before the run "
                f"and {self.idle_after_watts:g} W after, a drift of {drift / largest:.0%}. "
                "CHARTER.md §Energy instrument asks for both under the same ambient "
                "conditions, and a subtraction against a baseline that moved is not one."
            )

    @property
    def instrument(self) -> Instrument:
        return self.calibration.instrument

    @property
    def idle_watts(self) -> float:
        """The baseline that was subtracted: the mean of the two the Charter asks for."""
        return (self.idle_before_watts + self.idle_after_watts) / 2.0

    @property
    def idle_joules(self) -> float:
        """The product that was subtracted, reported so a reader can undo it."""
        return self.idle_watts * self.seconds

    @property
    def raw(self) -> Joules:
        """`E_load`: what the meter read, before anything was taken off it."""
        return Joules(self.load_joules, self.calibration.relative_error, self.instrument)

    @property
    def energy(self) -> Joules:
        """The idle-subtracted figure. Refuses to go below zero rather than reporting it.

        A negative idle-subtracted energy means the machine drew less under load than at rest,
        which is a statement about the baseline and never about the run.
        """
        subtracted = self.load_joules - self.idle_joules
        if subtracted < 0.0:
            raise MeterError(
                f"{self.instrument.name}: {self.load_joules:g} J under load is below the "
                f"{self.idle_joules:g} J the idle baseline predicts for {self.seconds:g}s. "
                "The baseline is wrong, and subtracting it would report a negative run."
            )
        return Joules(subtracted, self.calibration.relative_error, self.instrument)


def session(
    calibration: Calibration | None,
    *,
    load_joules: float,
    idle_before_watts: float,
    idle_after_watts: float,
    seconds: float,
) -> Session:
    """Open a measurement session, refusing the one that has no calibration record.

    The type already makes a measurement without a calibration unconstructible — `Session`
    has a `Calibration` field and no default, so there is no session without one, and `Joules`
    only comes out of a session or out of `estimated`. This function exists for the shape the
    refusal actually arrives in: an operator holding a run's numbers and no meter check.
    `None` is that case, and it gets a refusal rather than a result with a wide bar, because a
    wide bar is a number somebody can still quote.
    """
    if calibration is None:
        raise MeterError(
            "no calibration record for this session, so it produces no energy result. "
            "CHARTER.md §Energy instrument: not a result with a wide bar, a refusal — the "
            f"meter reads a known load for {CALIBRATION_SECONDS:g}s before each session, and "
            "the deviation is that session's error bar."
        )
    return Session(
        calibration=calibration,
        load_joules=load_joules,
        idle_before_watts=idle_before_watts,
        idle_after_watts=idle_after_watts,
        seconds=seconds,
    )


def estimated(instrument: Instrument, value: float, relative_error: float) -> Joules:
    """An analytic figure for a substrate this bench cannot run. Labelled, never measured.

    Refuses anything but an analytic instrument, and refuses an estimate with no stated
    uncertainty. A model that cannot say how wrong it might be is not evidence about joules;
    it is a number with a citation stapled to it.
    """
    if instrument.role is not Role.ANALYTIC:
        raise MeterError(
            f"{instrument.name} is {instrument.role}, and a measurement comes from a session "
            "with a calibration behind it. `estimated` is for substrates that cannot be run "
            "on this bench at all."
        )
    if value < 0.0:
        raise MeterError("a model that predicts negative energy is not a model of energy")
    return Joules(value, relative_error, instrument)


# --- what this machine actually has ------------------------------------------------------


@dataclass(frozen=True)
class Rapl:
    """One RAPL domain, through the kernel's powercap interface. Secondary, always.

    Secondary because of what it cannot see: DRAM is a separate domain on some parts and
    absent on others, and fans, PSU losses, the host and the network are outside it entirely
    — which is exactly the territory a comparison against 20 W is won or lost in.
    """

    domain: Path

    @property
    def instrument(self) -> Instrument:
        return Instrument(
            name=f"rapl:{self.label}",
            role=Role.SECONDARY,
            covers=(
                f"the {self.label} RAPL domain only: no fans, no PSU losses, no host, and "
                "DRAM only where this part exposes it as its own domain"
            ),
            source=f"Linux powercap sysfs, {self.domain}",
        )

    @property
    def label(self) -> str:
        """The domain's own name — `package-0`, `core`, `dram`."""
        try:
            return self.domain.joinpath("name").read_text(encoding="utf-8").strip()
        except OSError:
            return self.domain.name

    @property
    def wraps_at(self) -> float:
        """The counter's range, in joules. It wraps, and a long run will see it wrap."""
        return _read_micro(self.domain / "max_energy_range_uj")

    def unusable(self) -> str | None:
        """Why this counter cannot be read, or `None` when it can.

        Asked before a session rather than discovered during one. `energy_uj` has been
        root-only since CVE-2020-8694, so on most machines the answer is a permissions
        message, and finding that out at the end of a measured run is finding it out too late.
        """
        try:
            _read_micro(self.domain / "energy_uj")
        except MeterError as exc:
            return str(exc)
        return None

    def read(self) -> float:
        """The counter's cumulative joules. Rises, wraps, and means nothing on its own."""
        return _read_micro(self.domain / "energy_uj")


def counters(root: Path = RAPL_ROOT) -> tuple[Rapl, ...]:
    """Every RAPL domain this machine exposes, in path order. Empty where there are none."""
    try:
        found = sorted(path for path in root.iterdir() if (path / "energy_uj").exists())
    except OSError:
        return ()
    return tuple(Rapl(path) for path in found)


def delta(before: float, after: float, wraps_at: float) -> float:
    """Joules between two counter reads, allowing for one wrap.

    A cumulative counter that has wrapped reads lower than it did, and the naive subtraction
    reports a negative energy — or, worse, a plausible small one. One wrap is allowed because
    a session long enough to wrap twice has a bigger problem than this function.
    """
    if wraps_at <= 0.0:
        raise MeterError("a counter with no stated range cannot be read for a difference")
    if after >= before:
        return after - before
    return after + wraps_at - before


def _read_micro(path: Path) -> float:
    """Read a sysfs microjoule counter, in joules."""
    try:
        return int(path.read_text(encoding="utf-8").strip()) / 1_000_000.0
    except OSError as exc:
        raise MeterError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise MeterError(f"{path} does not hold a microjoule count: {exc}") from exc
