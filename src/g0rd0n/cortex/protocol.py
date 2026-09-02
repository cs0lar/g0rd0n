"""The matched-capability protocol: two arms, one instance set, one `measures`.

`CHARTER.md` §Matched-capability protocol, all six steps, and the place where Phase 8's three
halves meet. 8a says what a score means, 8b says what a joule figure may be quoted as, and
this module is what runs both arms and decides whether anything was shown.

**There is no evaluation with one arm.** `Evaluation` has a `control` field with no default,
and `control.attempt.arm.kind` must be `transformer` — the Charter's question is whether a
paradigm attains a capability "that no honestly-tuned transformer control arm attains within
the same `P`, `B`, and `N`", and that sentence is not satisfied by comparing against whatever
was convenient. `baseline_arm_runs_on_every_evaluation` is a field, not a rule.

**`evaluate` takes a `Registration`, and it is the only thing that makes an `Evaluation`.**
`Registration` is minted by `cortex.wager.register` and by nothing else, so a result cannot
physically exist before the wager that pre-registered it. That is ADR 0010's open gap closed:
at the end of Phase 7 nothing proved a wager was registered *before the experiment ran*, only
that it was registered before the result was recorded.

**The control arm runs first.** Protocol step 2 puts the tuning first for a reason that
carries over to the running: if the money runs out halfway, the arm that got measured should
be the one that would otherwise be quietly dropped. `BudgetExhausted` mid-evaluation leaves a
control attempt and no comparison, which is the honest failure.

**A separation needs an interval, not two numbers.** Step 5 allows the claim only when the
margin on `cap` excludes zero, so `verdict` is `corroborated` when it does and `inconclusive`
when it does not. `inconclusive` is a verdict and is recorded as one.

**Every comparison of a measurement with an estimate is flagged, on the face of the finding.**
`mixed` is derived from the two arms' bases, and the finding that goes into `measures` leads
with it. On a machine with no wall-plug meter this is the ordinary case rather than the
exception — see `g0rd0n bench meters`.

Deletion criterion: this module holds the wager that an experiment cannot produce a result
before the wager that priced it. Delete it and `baseline_arm_runs_on_every_evaluation`,
`an_evaluation_cannot_be_recorded_against_a_registration_the_kernel_does_not_have` and
`a_separation_needs_a_margin_whose_interval_excludes_zero` lose their verdicts, and the
protocol goes back to being six numbered paragraphs in a document.
"""

from collections.abc import Callable
from dataclasses import dataclass

from g0rd0n.cells.arm import CONTROL, Arm, ArmError, Attempt, attempt
from g0rd0n.cells.model import Model
from g0rd0n.config import Config
from g0rd0n.cortex.wager import Outcome, Recorded, Registration, Verdict
from g0rd0n.cortex.wager import record as record_verdict
from g0rd0n.cortex.wager import reserve as reserve_for
from g0rd0n.instruments.bench import Budget, Expenditure, Result, expenditure
from g0rd0n.instruments.capability import margin
from g0rd0n.instruments.meter import Basis, Joules
from g0rd0n.instruments.tasks import Family, InstanceSet
from g0rd0n.kernel import Bridge
from g0rd0n.ledger import Ledger

#: The agent name the reservation is booked under, so `g0rd0n cost --by agent` separates the
#: joules-measuring work from everything else g0rd0n spends on.
AGENT = "bench"


class ProtocolError(Exception):
    """An evaluation is not one the Charter's protocol would admit."""


@dataclass(frozen=True)
class Measurement:
    """One arm's run, and the joules the operator accounted to it.

    The energy is supplied from outside rather than derived here, and that is 8b's decision
    carried forward: an arm's config says what the arm *is*, and how its joules were accounted
    is a property of the session that ran it. It also means g0rd0n never invents an energy
    figure — a measured one comes from a calibrated `Session`, an analytic one from a model
    with its assumptions and its source attached, and there is no third way to get one.
    """

    attempt: Attempt
    energy: Joules
    secondary: tuple[Joules, ...] = ()
    preparation: Joules | None = None

    @property
    def arm(self) -> Arm:
        return self.attempt.arm

    @property
    def basis(self) -> Basis:
        return self.energy.basis

    def spent(self, budget: Budget) -> Expenditure:
        return expenditure(
            self.arm.name,
            self.energy,
            attempted=self.attempt.attempted,
            solved=self.attempt.solved,
            seconds=self.attempt.seconds,
            secondary=self.secondary,
            preparation=self.preparation,
            population=budget.population,
        )

    def result(self, budget: Budget) -> Result:
        return Result(
            arm=self.arm.name,
            family=self.attempt.family,
            curve=self.attempt.curve,
            budget=budget,
            spent=self.spent(budget),
            config_hash=self.arm.config_hash,
        )


#: How an arm's joules are accounted, supplied by the operator. One function for both arms:
#: it is handed the `Attempt`, so it knows which arm it is accounting for and may reach a
#: different instrument for each — which is exactly the case a mixed comparison arises from.
Accounting = Callable[[Attempt], Measurement]


@dataclass(frozen=True)
class Evaluation:
    """Two arms on one instance set at one budget, and what may be claimed from it.

    Built by `evaluate` and by nothing else worth doing: the refusals below are protocol steps
    2, 3 and 5, and a hand-built `Evaluation` is an experiment that skipped them.
    """

    registration: Registration
    budget: Budget
    control: Measurement
    candidate: Measurement

    def __post_init__(self) -> None:
        if self.control.arm.kind != CONTROL:
            raise ProtocolError(
                f"the control arm is a {self.control.arm.kind!r} and CHARTER.md §Question asks "
                f"whether a paradigm beats an honestly-tuned {CONTROL} control arm. A "
                "separation measured against something else is a separation from something "
                "else."
            )
        if self.control.arm.version == self.candidate.arm.version:
            raise ProtocolError(
                f"{self.control.arm.name} is on both sides of this comparison, so whatever it "
                "shows is a statement about the instance set"
            )
        if self.control.attempt.instances.version != self.candidate.attempt.instances.version:
            raise ProtocolError(
                "the arms answered different instance sets "
                f"({self.control.attempt.instances.version} and "
                f"{self.candidate.attempt.instances.version}). CHARTER.md §Matched-capability "
                "protocol step 3: run both arms on the identical instance set."
            )
        if self.control.arm.tuning_joules < self.candidate.arm.tuning_joules:
            raise ProtocolError(
                f"{self.control.arm.name} was tuned with {self.control.arm.tuning_joules:g} J "
                f"and {self.candidate.arm.name} with "
                f"{self.candidate.arm.tuning_joules:g} J. CHARTER.md §Matched-capability "
                "protocol step 2: tune the control arm first, spending at least as much energy "
                "on it as will be spent on the candidate. A separation measured against a "
                "baseline nobody tried to make good is not a separation."
            )
        if self.family.version not in self.registration.wager.task_family:
            raise ProtocolError(
                f"{self.registration.wager.id} pre-registered task family "
                f"{self.registration.wager.task_family!r}, which does not name "
                f"{self.family.slug}@{self.family.version}. Step 1 pre-registers the checker "
                "version, and a result on a family nobody pre-registered is a result nobody "
                "pre-registered."
            )

    @property
    def family(self) -> Family:
        return self.control.attempt.family

    @property
    def instances(self) -> InstanceSet:
        return self.control.attempt.instances

    @property
    def mixed(self) -> bool:
        """One arm was measured and the other modelled. Flagged, never refused."""
        return self.control.basis is not self.candidate.basis

    @property
    def results(self) -> tuple[Result, Result]:
        return (self.control.result(self.budget), self.candidate.result(self.budget))

    @property
    def margin(self) -> tuple[float, float]:
        """The 95% interval on `cap(candidate) - cap(control)`. Step 5's arithmetic."""
        return margin(self.family, self.candidate.attempt.curve, self.control.attempt.curve)

    @property
    def within_budget(self) -> bool:
        """Did both arms stay inside `B` and `P`? Step 5 compares "at equal `B`, `P`, and `N`"."""
        return all(result.within_budget for result in self.results)

    @property
    def separated(self) -> bool:
        """Does the margin exclude zero, on the side that would be a separation?

        And did both arms stay inside the budget. The margin is computed on scores alone,
        because that is what a bootstrap over `cap` can resample — but a `cap` is undefined for
        an arm that overspent, and a positive margin between two score curves where one arm
        bought its scores outside its budget is not a separation at matched energy. Without
        this clause an evaluation could report a separation while `Result.cap` reported `None`
        for the arm that supposedly won.
        """
        return self.within_budget and self.margin[0] > 0.0

    @property
    def verdict(self) -> Verdict:
        """Step 5, read literally: a separation, or `inconclusive`.

        And `inconclusive` covers a candidate that came out *behind* the control arm as well,
        which looks like a refutation and is worded by the Charter as neither. That is
        recorded as a criticism a superseding Charter could quote rather than fixed here —
        `ARGUES` is a table, and quietly mapping a negative margin to `refutes` would put a
        stronger claim into the argument graph than the protocol licenses. See ADR 0015.
        """
        return Verdict.CORROBORATED if self.separated else Verdict.INCONCLUSIVE

    @property
    def finding(self) -> str:
        """What goes into `measures`, including both config hashes. One line, then the detail.

        AGENTS.md §Phase 8: "Every run commits `measures` with the full config hash, so a
        result nobody can reproduce is visibly a result nobody can reproduce." Both hashes,
        because a comparison nobody can reproduce needs both halves.
        """
        control, candidate = self.results
        low, high = self.margin
        flag = f"MIXED ({self.candidate.basis} vs {self.control.basis}); " if self.mixed else ""
        if self.separated:
            headline = "cap margin excludes zero: a separation"
        elif not self.within_budget:
            outside = ", ".join(result.arm for result in self.results if not result.within_budget)
            headline = f"no separation shown: {outside} did not stay inside the budget"
        else:
            headline = "cap margin includes zero: no separation shown"
        return "; ".join(
            (
                f"{flag}{headline}",
                f"margin [{low:g}, {high:g}] on cap({self.candidate.arm.name})"
                f" - cap({self.control.arm.name})",
                f"{self.candidate.arm.name} cap {candidate.cap} config "
                f"{self.candidate.arm.config_hash} instrument {candidate.instrument.name}",
                f"{self.control.arm.name} cap {control.cap} config "
                f"{self.control.arm.config_hash} instrument {control.instrument.name}",
                f"budget {self.budget}",
                f"family {self.family.slug}@{self.family.version}",
                f"instances {self.instances.version} "
                f"({self.instances.count} per size at {self.instances.sizes})",
                f"tuning: {self.control.arm.name} {self.control.arm.tuning_joules:g} J, "
                f"{self.candidate.arm.name} {self.candidate.arm.tuning_joules:g} J",
            )
        )

    def render(self) -> str:
        """Both arms in full, then the comparison. Step 4's report."""
        control, candidate = self.results
        low, high = self.margin
        return "\n\n".join(
            (
                control.render(),
                candidate.render(),
                "\n".join(
                    (
                        f"margin         [{low:g}, {high:g}]  "
                        f"cap({self.candidate.arm.name}) - cap({self.control.arm.name})",
                        f"verdict        {self.verdict}"
                        + ("  [MIXED: an estimate against a measurement]" if self.mixed else ""),
                        f"wager          {self.registration.wager.id}",
                    )
                ),
            )
        )


def evaluate(
    registration: Registration,
    budget: Budget,
    *,
    control: Arm,
    candidate: Arm,
    family: Family,
    instances: InstanceSet,
    account: Accounting,
    config: Config,
    ledger: Ledger,
    model: Model,
) -> Evaluation:
    """Run both arms on one instance set, under one reservation, and assemble the comparison.

    One reservation covers both arms, because the wager pre-registered one price for finding
    this out and splitting it in two would let the second half be re-priced after seeing the
    first. Settlement is in a `finally`, so a failure anywhere leaves nothing open.

    The control arm goes first. If the budget runs out midway the record shows a control
    attempt and no comparison — which is the failure that admits it happened.
    """
    if control.version == candidate.version:
        raise ArmError(f"{control.name} cannot be both arms of its own comparison")

    reservation = reserve_for(ledger, registration, AGENT)
    try:
        measured = account(
            attempt(
                control,
                family,
                instances,
                config=config,
                ledger=ledger,
                model=model,
                reservation=reservation,
            )
        )
        challenger = account(
            attempt(
                candidate,
                family,
                instances,
                config=config,
                ledger=ledger,
                model=model,
                reservation=reservation,
            )
        )
    finally:
        ledger.settle(reservation)

    return Evaluation(
        registration=registration,
        budget=budget,
        control=measured,
        candidate=challenger,
    )


def settle(bridge: Bridge, evaluation: Evaluation) -> Recorded:
    """Commit the one `measures` this evaluation earns, through the one write path there is.

    `cortex.wager.record` is reused rather than reimplemented: it already refuses a result the
    kernel has no pre-registration for, refuses a second verdict on one wager, and knows which
    verdicts argue and which do not. A second commit path for bench results would be a second
    place for those three rules to be almost the same.
    """
    return record_verdict(
        bridge, evaluation.registration, Outcome(evaluation.verdict, evaluation.finding)
    )
