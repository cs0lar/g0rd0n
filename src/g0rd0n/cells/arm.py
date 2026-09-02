"""An arm: a system under evaluation, its versioned config, and the loop that runs it.

`CHARTER.md` §Matched-capability protocol steps 2 and 3. An arm is not a Cell doing g0rd0n's
research — it is the *subject* of the experiment, and the difference decides almost everything
about this module.

**An arm commits nothing.** `cells/runtime.py` interns a transcript and commits a `plays` edge
for every run, because a cell doing g0rd0n's work is work g0rd0n should have to answer for. An
arm answering 120 instances is not that. Interning 240 transcripts per evaluation would fill
the argument graph with the experimental subject's output, and the Charter asks for the
per-instance records in the *result*, not in the kernel. The one commit an evaluation makes is
`cortex/protocol.py`'s single `measures`.

**But it is priced like everything else.** g0rd0n spends real money asking an arm 120
questions, and `attempt` takes a `Reservation` — not a wager id, not a config, a
`Reservation`. The only thing that makes one is `Ledger.reserve`, and the only thing that
reserves against a wager is `cortex.wager.reserve`, which takes a `Registration`. So the chain
from a model call back to a pre-registered wager is unbroken by construction, which is what
ADR 0010 recorded as the open gap at the end of Phase 7.

**`operating_cost` is not `target_energy`.** The `Cost` an `Attempt` carries is dollars,
tokens and seconds g0rd0n spent — it never appears in `B`, `P`, or any result. The arm's
joules are a separate quantity, accounted by the operator with an instrument, and this module
does not know how. AGENTS.md §The Two Energies, and the confusion it warns about is exactly
one field away in either direction.

**The wall-clock ceiling `W` is applied here, and it is honest about what it measured.** An
instance answered outside `Family.ceiling_seconds` scores zero rather than being allowed to
run on, per §Resource held fixed. For an arm behind an HTTP API that clock includes the
network and somebody else's queue, so `W` on such an arm bounds the round trip and not the
computation. That is a real weakness of evaluating a hosted model and it is recorded rather
than smoothed over: see ADR 0015.

**A failed model call fails the attempt; it does not score zero.** A refused instance is the
arm failing. A dead endpoint is g0rd0n failing, and scoring it against the arm would attribute
an infrastructure problem to the system under test. Nothing is retried, for the reason
`cells/runtime.py` gives.

Deletion criterion: this module holds the wager that a system under evaluation is fully
described by an artifact somebody can diff. Delete it and
`an_arms_version_is_the_hash_of_its_whole_config`,
`an_instance_answered_outside_the_wall_clock_ceiling_scores_zero` and
`an_arm_cannot_be_run_without_a_reservation` lose their verdicts, and "the control arm" goes
back to meaning whatever settings the last run happened to use.
"""

import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from g0rd0n.cells.model import Model, Turn
from g0rd0n.config import Config
from g0rd0n.content import version_of
from g0rd0n.instruments.capability import Curve, Point, curve
from g0rd0n.instruments.tasks import Family, Instance, InstanceSet, TaskError
from g0rd0n.ledger import Cost, Ledger
from g0rd0n.ledger.ledger import Reservation

#: Where the versioned baseline configs live. AGENTS.md's layout puts task suites and baseline
#: configs in `bench/`, beside the repository rather than inside the package: they are
#: artifacts to be reviewed in a diff, like a playbook, not code.
BASELINES = Path("bench/baselines")

#: The keys a config file may have. Closed, like a playbook's and like the config file's —
#: a mistyped setting that silently does nothing is the failure this rejection exists for.
KNOWN_KEYS = frozenset({"kind", "model", "system", "max_tokens", "tuning_joules", "tuning_note"})

#: The kind the Charter's question names as the thing to beat. `Evaluation` requires the
#: baseline to be one: "no honestly-tuned transformer control arm attains" is not satisfied by
#: comparing against whatever was convenient.
CONTROL = "transformer"

#: The fields the version hashes, in canonical order. Fixed here rather than taken from the
#: dataclass so that reordering the fields is not silently a new identity for every arm.
SUBSTANCE: tuple[str, ...] = (
    "name",
    "kind",
    "model",
    "system",
    "max_tokens",
    "tuning_joules",
    "tuning_note",
)


class ArmError(Exception):
    """An arm, or an attempt with one, is not something this bench could report."""


@dataclass(frozen=True)
class Arm:
    """A system under evaluation, described completely enough to be run again.

    `tuning_joules` and `tuning_note` are protocol step 2, which asks that the control arm be
    tuned first, with at least as much energy as the candidate, and that **both figures are
    recorded in the result**. They are inside the version because an arm retuned is a
    different arm — a separation measured against a baseline nobody tried to make good is not
    a separation, and "how hard did you try" is exactly the number that gets adjusted after
    the fact if nothing pins it.
    """

    name: str
    kind: str
    model: str
    system: str
    max_tokens: int
    tuning_joules: float
    tuning_note: str

    def __post_init__(self) -> None:
        for field in ("name", "kind", "model", "system"):
            if not str(getattr(self, field)).strip():
                raise ArmError(f"an arm must declare its {field}")
        if self.max_tokens < 1:
            raise ArmError(f"{self.name}: an arm allowed no output tokens cannot answer")
        if self.tuning_joules < 0.0:
            raise ArmError(f"{self.name}: tuning cannot have cost negative energy")
        if self.tuning_joules > 0.0 and not self.tuning_note.strip():
            raise ArmError(
                f"{self.name}: {self.tuning_joules:g} J of tuning with no note saying what was "
                "tuned. CHARTER.md §Matched-capability protocol step 2 asks for the figure to "
                "be recorded, and a figure nobody can interpret is not recorded"
            )

    @property
    def spec(self) -> str:
        """The canonical text the version hashes: everything that makes this arm this arm."""
        return "\n".join(f"{field}: {getattr(self, field)!r}" for field in SUBSTANCE)

    @property
    def version(self) -> str:
        return version_of(self.spec.encode("utf-8"))

    @property
    def config_hash(self) -> str:
        """What a `Result` carries and `measures` commits. The same thing as the version.

        Two names for one string, deliberately: AGENTS.md §Phase 8 asks for "the full config
        hash" and this module thinks of it as the arm's version, and a reader chasing either
        phrase should land on the same twelve characters rather than wondering which is which.
        """
        return self.version


@dataclass(frozen=True)
class Answered:
    """One instance, what the arm said, how long it took, and what the checker made of it."""

    instance: Instance
    answer: str
    seconds: float
    score: float
    overran: bool

    @property
    def solved(self) -> bool:
        """Correct, not nearly correct.

        `J_solved` is joules per *correct answer*, and T3's checker gives partial credit by F1
        — so a 0.8 is a partly right answer and counting it would report an efficiency for
        work that did not finish. The curve is where partial credit belongs.
        """
        return self.score >= 1.0


@dataclass(frozen=True)
class Attempt:
    """One arm's run over one pre-registered instance set, instance by instance.

    Holds every answer rather than a summary, because protocol step 4 asks for the
    per-instance records alongside the headline and a summary cannot be un-summarised.
    """

    arm: Arm
    family: Family
    instances: InstanceSet
    answers: tuple[Answered, ...]
    cost: Cost

    @property
    def attempted(self) -> int:
        return len(self.answers)

    @property
    def solved(self) -> int:
        return sum(1 for answered in self.answers if answered.solved)

    @property
    def overran(self) -> int:
        """How many instances were scored as failures for exceeding `W`."""
        return sum(1 for answered in self.answers if answered.overran)

    @property
    def seconds(self) -> float:
        """Wall-clock across every instance, which is what an energy session would span."""
        return sum(answered.seconds for answered in self.answers)

    @property
    def curve(self) -> Curve:
        """Score against size. Refuses a single size, forty instances a point, as 8a's does."""
        return curve(
            self.family,
            tuple(
                Point(
                    size=size,
                    scores=tuple(
                        answered.score
                        for answered in self.answers
                        if answered.instance.size == size
                    ),
                )
                for size in self.instances.sizes
            ),
        )


def attempt(
    arm: Arm,
    family: Family,
    instances: InstanceSet,
    *,
    config: Config,
    ledger: Ledger,
    model: Model,
    reservation: Reservation,
) -> Attempt:
    """Ask one arm every instance in a pre-registered set, and score what comes back.

    Takes a `Reservation` and not a wager id. The Ledger will price any string handed to it,
    and `cortex.wager.reserve` is the only thing that turns a registered wager into one of
    these — so an arm cannot be run against a wager the kernel was never told about.

    Raises rather than scoring zero when a model call fails: a dead endpoint is g0rd0n's
    failure, and charging it to the arm would put an infrastructure problem into a result.
    """
    if instances.family_version != family.version:
        raise ArmError(
            f"the instance set is {instances.family}@{instances.family_version} and the family "
            f"is {family.slug}@{family.version}; an arm is scored by the checker its "
            "instances were pre-registered against"
        )
    if not instances.instances:
        raise TaskError(f"{arm.name}: an instance set with nothing in it measures nothing")

    price = config.price_of(arm.model)
    answers: list[Answered] = []
    spent = Cost()

    for instance in instances.instances:
        started = time.monotonic()
        reply = model.reply(
            model=arm.model,
            system=arm.system,
            turns=(Turn(role="user", text=instance.question),),
            tools=(),
            max_tokens=arm.max_tokens,
        )
        seconds = time.monotonic() - started
        cost = Cost(
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            usd=price.usd(reply.tokens_in, reply.tokens_out),
            seconds=seconds,
        )
        spent = spent + cost
        ledger.spend(reservation, cost)

        overran = seconds > family.ceiling_seconds
        answers.append(
            Answered(
                instance=instance,
                answer=reply.text,
                seconds=seconds,
                score=0.0 if overran else family.score(instance, reply.text),
                overran=overran,
            )
        )

    return Attempt(arm=arm, family=family, instances=instances, answers=tuple(answers), cost=spent)


def load(path: Path) -> Arm:
    """Read one arm's config file and hash it. The whole file, so nothing sits outside.

    The name comes from the filename, exactly as a playbook's role does, so there is no key a
    config could set to two different things and no way to have two arms with one name in one
    directory.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArmError(f"cannot read arm config {path}: {exc}") from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ArmError(f"{path} is not a valid arm config: {exc}") from exc

    unknown = set(raw) - KNOWN_KEYS
    if unknown:
        raise ArmError(f"{path}: unknown setting {', '.join(sorted(unknown))}")
    missing = {"kind", "model", "system", "max_tokens"} - set(raw)
    if missing:
        raise ArmError(f"{path}: an arm config must set {', '.join(sorted(missing))}")

    return Arm(
        name=path.stem,
        kind=str(raw["kind"]),
        model=str(raw["model"]),
        system=str(raw["system"]),
        max_tokens=int(raw["max_tokens"]),
        tuning_joules=float(raw.get("tuning_joules", 0.0)),
        tuning_note=str(raw.get("tuning_note", "")),
    )


def baselines(root: Path = BASELINES) -> tuple[Arm, ...]:
    """Every shipped baseline config, in filename order. Empty where the directory is not."""
    try:
        found = sorted(root.glob("*.toml"))
    except OSError:
        return ()
    return tuple(load(path) for path in found)
