"""What may be reported: joules against a declared budget, and `cap` paired with the budget.

`CHARTER.md` §Energy metric, §Capability metric and §Matched-capability protocol. `meter` says
what read a joule; this module says what a joule figure is allowed to be quoted as. The two
sentences it exists to enforce are both in the Charter and both easy to break by accident:

- **"Raw accuracy alone is not a result under this Charter, and neither is `cap` without the
  budget it was measured at."** So there is no type here that carries a `cap` without a
  `Budget` and an `Expenditure` beside it, and no rendering of one that omits them. Phase 8a
  built the score half and said in its own docstring that quoting it alone would be quoting a
  capability with no budget; `Result` is the type that closes that.
- **"An estimate is never compared with a measurement unless the comparison is flagged as
  mixed on the face of the comparison."** `compare` is the only thing in this package that
  puts two instruments' numbers in one expression — `Joules.minus` refuses different
  instruments outright — and every `Comparison` carries `mixed` and renders it. The flag is
  derived rather than passed, so a caller cannot forget it and a caller cannot suppress it.

**Two denominators, and the difference is the point.** The budget test divides by instances
*attempted*, so a system cannot buy its way inside `B` by declining the instances it expects
to fail. `J_solved` divides by instances *solved*, so a system that answers fast and wrong is
charged for the answers it got wrong. Using either for both is the single easiest way to make
a bench flatter an arm, so they are separate properties with the reason on each.

**A secondary instrument is refused on its own.** The Charter admits on-die counters only
"alongside and never alone", because they miss DRAM on some parts and miss fans, PSU losses,
the host and the network on all of them — which is exactly where a comparison against 20 W is
won or lost. `expenditure` is where that becomes a raised exception.

**`W` is not a field here, and that is deliberate.** The Charter's protocol pre-registers `B`,
`P`, `N` and `W`, and `W` is already inside the family's version — `Family.spec` hashes
`ceiling_seconds` along with everything else — so a wager naming a family version has
pre-registered its wall-clock ceiling too. A second copy in `Budget` would be a second thing to
disagree with (ADR 0002). Enforcing it per instance belongs to the run loop, which is 8c's.

Deletion criterion: this module holds the wager that a capability number and the joules it was
bought with are one object or neither is a result. Delete it and
`a_cap_is_never_reported_without_the_budget_it_was_measured_at`,
`measured_and_estimated_energy_are_never_compared_without_a_flag` and
`counters_are_never_reported_alone` lose their verdicts, and the bench goes back to being able
to publish an accuracy.

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

from dataclasses import dataclass

from g0rd0n.instruments.capability import Curve
from g0rd0n.instruments.capability import cap as capability_of
from g0rd0n.instruments.meter import Basis, Instrument, Joules, MeterError, Role
from g0rd0n.instruments.tasks import Family, TaskError


@dataclass(frozen=True)
class Budget:
    """The energy this run was allowed: `B` per instance, `P` over a declared `N`.

    All three are pre-registered by the wager before anything runs, which is what makes
    "inside budget" a fact rather than a description written afterwards. `P` and `B` are split
    rather than folded together because a transformer's inference is cheap and its training is
    not, while a brain has no separate training phase — without the split, any comparison to
    20 W is a choice of accounting wearing the costume of a result.
    """

    #: `B`: joules per instance attempted.
    inference_joules: float
    #: `P`: joules spent before the first instance was answered.
    preparation_joules: float
    #: `N`: the deployment population `P` is amortised over.
    population: int

    def __post_init__(self) -> None:
        if self.inference_joules <= 0.0:
            raise TaskError("a budget of no joules per instance is not a budget, it is a ban")
        if self.preparation_joules < 0.0:
            raise TaskError("a preparation budget cannot be negative")
        if self.population < 1:
            raise TaskError(
                "a preparation budget is amortised over a declared deployment population, and "
                "N must be at least 1; CHARTER.md §Resource held fixed"
            )

    @property
    def amortised_joules(self) -> float:
        """`P/N`, the figure the Charter reports beside `B` with `N` stated."""
        return self.preparation_joules / self.population

    def __str__(self) -> str:
        return (
            f"B={self.inference_joules:g} J/instance, P={self.preparation_joules:g} J "
            f"over N={self.population} (P/N={self.amortised_joules:g} J)"
        )


@dataclass(frozen=True)
class Expenditure:
    """What one arm spent on one instance set, and how many instances it got right.

    Built by `expenditure`, which is where the Charter's refusals live. The secondaries are
    kept rather than collapsed into the primary because the Charter asks for the ratio
    `wall / counters` to be stated for the run, and a ratio needs both halves.
    """

    arm: str
    primary: Joules
    secondary: tuple[Joules, ...]
    attempted: int
    solved: int
    seconds: float
    preparation: Joules | None
    population: int

    @property
    def instrument(self) -> Instrument:
        return self.primary.instrument

    @property
    def basis(self) -> Basis:
        return self.primary.basis

    @property
    def per_attempted(self) -> Joules:
        """The budget test's numerator over its denominator: joules per instance *attempted*.

        Attempted, not solved, so a system cannot come in under `B` by declining every
        instance it expects to fail and answering only the cheap ones.
        """
        return self.primary.per(self.attempted)

    @property
    def j_solved(self) -> Joules | None:
        """`J_solved = E / k`. `None` when `k = 0`, which is a real state and not a zero.

        Solved, not attempted, so an arm that answers fast and wrong is charged for the
        answers it got wrong. A run with nothing solved reports its joules and no `J_solved`;
        dividing by zero instances would be reporting an efficiency for a system that was not
        efficient at anything.
        """
        return self.primary.per(self.solved) if self.solved else None

    @property
    def amortised(self) -> Joules | None:
        """`P/N` as measured, or `None` for an arm with no preparation phase at all.

        `None` is not zero. A paradigm that learns online has no preparation phase, and saying
        so is different from saying its preparation happened to cost nothing — the Charter
        chartered `T2` precisely so that adaptation cannot be hidden in `P`.
        """
        return self.preparation.per(self.population) if self.preparation is not None else None

    @property
    def ratios(self) -> tuple[tuple[str, float], ...]:
        """`wall / counters` for each secondary, which the Charter asks be stated per run.

        A ratio near one on a machine with an accelerator means the counters are seeing more
        than they should, not that the meter agrees with them.
        """
        return tuple(
            (reading.instrument.name, self.primary.value / reading.value)
            for reading in self.secondary
            if reading.value > 0.0
        )

    def within(self, budget: Budget) -> bool:
        """`E / attempted ≤ B`, and the preparation inside `P` for the declared `N`.

        Compared on the point estimate rather than the interval, deliberately: the budget is a
        commitment the arm made, and letting a wide error bar argue an arm back inside its
        budget would make a worse meter into a licence to overspend.
        """
        if self.per_attempted.value > budget.inference_joules:
            return False
        if self.population != budget.population:
            return False
        prepared = self.preparation.value if self.preparation is not None else 0.0
        return prepared <= budget.preparation_joules

    def __str__(self) -> str:
        solved = f"{self.j_solved} per solved" if self.j_solved else "nothing solved"
        return (
            f"{self.arm}: {self.primary} over {self.attempted} attempted "
            f"({self.solved} solved, {self.seconds:g}s); {self.per_attempted} per attempted; "
            f"{solved}"
        )


def expenditure(
    arm: str,
    primary: Joules,
    *,
    attempted: int,
    solved: int,
    seconds: float,
    secondary: tuple[Joules, ...] = (),
    preparation: Joules | None = None,
    population: int = 1,
) -> Expenditure:
    """Assemble one arm's spend, refusing the readings the Charter does not admit.

    The refusal that does the work is the first one. On-die counters are secondary "always
    reported alongside and never alone", and a bench that let them stand in for the primary
    would report the joules of the part of the machine that was easiest to instrument.
    """
    if not arm.strip():
        raise TaskError("an expenditure belongs to a named arm")
    if primary.instrument.role is Role.SECONDARY:
        raise TaskError(
            f"{primary.instrument.name} is a secondary instrument and cannot carry a run on "
            "its own. CHARTER.md §Energy instrument: counters are reported alongside a "
            "wall-plug meter and never instead of one, because they miss fans, PSU losses, "
            "the host and the network — which is where a comparison against 20 W is settled."
        )
    for reading in secondary:
        if reading.instrument.role is not Role.SECONDARY:
            raise TaskError(
                f"{reading.instrument.name} is {reading.instrument.role} and is being reported "
                "as a secondary; the primary is the figure the result is quoted from"
            )
    if primary.instrument.role is Role.ANALYTIC and secondary:
        raise TaskError(
            f"{arm} is an analytic estimate and carries {len(secondary)} counter reading(s); a "
            "substrate this bench cannot run has no counters on this machine to read"
        )
    if attempted < 1:
        raise TaskError(f"{arm}: a run that attempted nothing measured nothing")
    if not 0 <= solved <= attempted:
        raise TaskError(f"{arm}: {solved} solved out of {attempted} attempted")
    if seconds <= 0.0:
        raise TaskError(f"{arm}: a run has a duration")
    if population < 1:
        raise TaskError(f"{arm}: a deployment population is at least 1")
    return Expenditure(
        arm=arm,
        primary=primary,
        secondary=secondary,
        attempted=attempted,
        solved=solved,
        seconds=seconds,
        preparation=preparation,
        population=population,
    )


@dataclass(frozen=True)
class Comparison:
    """Two energy figures side by side, and whether anything measured both of them.

    The only place in this package where two instruments' numbers meet in one expression.
    `mixed` is derived from the two bases rather than passed in, so there is no argument a
    caller can leave out and no argument a caller can set to `False`.
    """

    left: Joules
    right: Joules

    @property
    def mixed(self) -> bool:
        """One of these was measured and the other was modelled."""
        return self.left.basis is not self.right.basis

    @property
    def ratio(self) -> float:
        """`left / right`."""
        if self.right.value == 0.0:
            raise MeterError("cannot take a ratio against zero joules")
        return self.left.value / self.right.value

    @property
    def relative_error(self) -> float:
        """The bar on the ratio: the two relative errors in quadrature.

        In quadrature rather than added, because two instruments' calibration deviations are
        independent — unlike `Joules.minus`, where one meter's scale error survives the
        subtraction unchanged because it is the *same* error on both terms.
        """
        return float((self.left.relative_error**2 + self.right.relative_error**2) ** 0.5)

    @property
    def separated(self) -> bool:
        """Do the two error bars fail to overlap? A difference smaller than this is noise."""
        low, high = self.left.interval
        other_low, other_high = self.right.interval
        return high < other_low or other_high < low

    def __str__(self) -> str:
        flag = f"MIXED ({self.left.basis} vs {self.right.basis}): " if self.mixed else ""
        overlap = "separated" if self.separated else "bars overlap"
        return (
            f"{flag}{self.left} vs {self.right} — "
            f"ratio {self.ratio:.4g} ± {self.ratio * self.relative_error:.3g}, {overlap}"
        )


def compare(left: Joules, right: Joules) -> Comparison:
    """Put two energy figures side by side. A mixed comparison is flagged, never refused.

    Flagged rather than refused because the Charter says a candidate that cannot be run on
    this bench "is evaluated by analytic estimate under the same protocol, and every
    comparison it appears in is flagged as mixed" — so the comparison is admissible and the
    label is what makes it honest. Refusing it outright would make the only evidence available
    about neuromorphic and analog substrates unreportable.
    """
    return Comparison(left=left, right=right)


@dataclass(frozen=True)
class Result:
    """`cap`, the curve under it, and the budget it was measured at. All three or none.

    The Charter's last line on the capability metric is that raw accuracy alone is not a
    result and neither is `cap` without its budget. This is the type that makes that
    structural: there is no field to drop, and `render` prints all three.

    `config_hash` is the hash of the arm's full configuration, and it is required. AGENTS.md
    §Phase 8: every run commits `measures` with the full config hash, "so a result nobody can
    reproduce is visibly a result nobody can reproduce". What goes into that hash is the arm's
    business, which is 8c's; that it cannot be empty is this module's.
    """

    arm: str
    family: Family
    curve: Curve
    budget: Budget
    spent: Expenditure
    config_hash: str

    def __post_init__(self) -> None:
        if not self.config_hash.strip():
            raise TaskError(
                f"{self.arm}: a result carries the hash of the config that produced it. "
                "AGENTS.md §Phase 8: a result nobody can reproduce must be visibly one."
            )
        if self.spent.arm != self.arm:
            raise TaskError(
                f"this result is {self.arm}'s and the energy is {self.spent.arm}'s; an arm is "
                "scored on the joules it spent"
            )
        if self.curve.family_version != self.family.version:
            raise TaskError(
                f"the curve is {self.curve.family}@{self.curve.family_version} and the family "
                f"is {self.family.slug}@{self.family.version}"
            )

    @property
    def within_budget(self) -> bool:
        return self.spent.within(self.budget)

    @property
    def cap(self) -> int | None:
        """The Charter's `cap`: the score prefix, and only if the run stayed inside `B` and `P`.

        A size *clears* when the scores clear **and** every instance was answered inside the
        budget. An arm that beat the threshold by spending more joules than it registered has
        not cleared anything — it has demonstrated what it could do with a budget nobody gave
        it — so a run outside its budget has no `cap` at all rather than a `cap` with a
        caveat. Wall-clock `W` is checked per instance by the run loop, not here.
        """
        if not self.within_budget:
            return None
        return capability_of(self.family, self.curve)

    @property
    def instrument(self) -> Instrument:
        return self.spent.instrument

    @property
    def basis(self) -> Basis:
        return self.spent.basis

    def render(self) -> str:
        """Every line the Charter asks for, and no way to print the headline without them."""
        reached = "undefined (the smallest measured size does not clear)"
        if self.cap is not None:
            reached = str(self.cap)
        elif not self.within_budget:
            reached = "undefined (the run did not stay inside its budget)"
        lines = [
            f"{self.arm} on {self.family.slug}@{self.family.version}  [{self.basis}]",
            f"  cap            {reached}   (θ={self.family.threshold:g})",
            f"  budget         {self.budget}",
            f"  spent          {self.spent.per_attempted} per instance attempted",
            f"  J_solved       {self.spent.j_solved or 'no instances solved'}",
            f"  instrument     {self.instrument.name}: {self.instrument.covers}",
            f"  config         {self.config_hash}",
            "  curve",
        ]
        for point in self.curve.points:
            low, high = point.interval
            clears = "clears" if point.clears(self.family.threshold) else "fails"
            lines.append(
                f"    n={point.size:<6d} {point.mean:.4f}  [{low:.4f}, {high:.4f}]  "
                f"{point.attempted} instances  {clears}"
            )
        for name, ratio in self.spent.ratios:
            lines.append(f"  wall/{name}  {ratio:.4g}")
        if self.spent.amortised is not None:
            lines.append(f"  P/N            {self.spent.amortised} over N={self.spent.population}")
        else:
            lines.append("  P/N            no preparation phase")
        return "\n".join(lines)
