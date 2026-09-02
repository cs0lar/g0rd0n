"""Capability at a budget: the score curve, its bootstrap interval, and the ordinal `cap`.

`CHARTER.md` §Capability metric and `docs/charter/definitions.md` §Capability at a budget: the
largest size that clears *and below which every measured size clears*, where clearing means
the mean checker score over the pre-registered instance set is at least the family's
threshold **and the lower end of a 95% bootstrap interval is too**.

Both halves of "clears" matter. The point estimate alone gives a number that moves when
somebody reruns the same instances, and a capability that moves under a rerun is not measuring
the system.

The prefix matters for a different reason. `cap` is an ordinal, and taking the largest
clearing size would report a lone high point standing above a size that failed — which, on
families whose capability falls away as size grows, is evidence about the instance set rather
than about the system. The first version of this module took the maximum, which
`charter-8fb7f2095506` criticised and replaced; `a_cap_stops_at_the_first_size_that_fails`
is that clause.

**A curve, never an accuracy.** The Charter is explicit that raw accuracy alone is not a
result: a system that solves everything to size 5 and one that solves everything to size 50
report the same accuracy on a mixed set if the mixture is chosen right, and the difference
between them is the entire question. So `curve` refuses a single size. One size is an accuracy
wearing a curve's name, and the refusal is the only place that distinction can be enforced —
by the time a number reaches a report it has lost the shape it came from.

**Forty instances per size, and the number is derived rather than chosen.** A 95% percentile
interval puts 2.5% in each tail; below `1 / 0.025 = 40` observations that tail is less than
one instance wide, so the interval's endpoint stops being a quantile and becomes the most
extreme thing that happened. A cap certified from five instances is a cap certified by luck.
This makes a capability claim cost forty instances per size per arm, deliberately.

**This is `cap` without its budget, and that is not yet a result.** The Charter's `cap` also
requires every instance to have been answered inside `B` and inside `W`, on a system prepared
inside `P` for a declared `N`. Nothing here measures a joule or a second; the energy half
arrives with the meter, and the type that pairs them is the one that may be reported. What
this module computes is the score half, and quoting it alone would be quoting a capability
with no budget beside it, which §Capability metric says is not a result.

**A separation is a `cap` margin whose interval excludes zero.** Protocol step 5 will not let
a separation be claimed on two `cap` numbers that differ, only on a difference that survives
resampling, and `margin` is that arithmetic. It is here rather than in `cortex` because it is
a fact about two curves and knows nothing about wagers.

Deletion criterion: this module holds the wager that a capability claim is an ordinal with an
interval under it rather than an average somebody liked. Delete it and
`a_single_size_is_an_accuracy_not_a_curve`, `a_cap_needs_its_interval_to_clear_not_just_its_
mean`, `a_curve_measured_against_another_version_of_the_checker_is_refused` and
`two_caps_that_differ_are_not_a_separation` lose their verdicts, and "cap 34 on T1" goes back
to meaning whatever the person quoting it meant.

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

import random
from dataclasses import dataclass
from functools import cache

from g0rd0n.content import version_of
from g0rd0n.instruments.tasks import Family, TaskError

#: The Charter's interval: 95%, two-sided.
CONFIDENCE = 0.95

#: How many bootstrap resamples. Large enough that the 2.5% tail lands on a stable index,
#: small enough that a whole curve costs milliseconds.
RESAMPLES = 2000

#: The fewest instances a point may be built from. See the module docstring: 1 / 0.025.
MINIMUM = 40


@dataclass(frozen=True)
class Point:
    """One size, and every score the arm earned at it.

    The raw scores are kept rather than a mean, because the interval is a statement about the
    scores and cannot be recovered from their average. A `Point` that stored only a mean would
    be a `Point` whose interval had to be taken on trust.
    """

    size: int
    scores: tuple[float, ...]

    @property
    def attempted(self) -> int:
        return len(self.scores)

    @property
    def mean(self) -> float:
        return sum(self.scores) / len(self.scores)

    @property
    def interval(self) -> tuple[float, float]:
        return interval(self.scores)

    def clears(self, threshold: float) -> bool:
        """Both tests the Charter asks for: the mean, and the low end of the interval."""
        return self.mean >= threshold and self.interval[0] >= threshold


@dataclass(frozen=True)
class Curve:
    """Score against size, for one arm on one version of one family.

    `family_version` travels with the numbers because a curve measured against a different
    checker is a curve about a different family, and the two are indistinguishable once the
    scores are in a table.
    """

    family: str
    family_version: str
    points: tuple[Point, ...]

    @property
    def sizes(self) -> tuple[int, ...]:
        return tuple(point.size for point in self.points)


def curve(family: Family, points: tuple[Point, ...]) -> Curve:
    """Assemble a curve, refusing anything that is not one. Points come back size-ordered."""
    if len(points) < 2:
        raise TaskError(
            f"{family.slug}: a curve over {len(points)} size(s) is an accuracy, not a curve. "
            "CHARTER.md §Capability metric: raw accuracy alone is not a result under this "
            "Charter, because a mixture of sizes can be chosen to report any of them."
        )
    sizes = [point.size for point in points]
    if len(set(sizes)) != len(sizes):
        raise TaskError(f"{family.slug}: a size appears twice, so one of them is being ignored")
    for point in points:
        if point.attempted < MINIMUM:
            raise TaskError(
                f"{family.slug}: size {point.size} was measured on {point.attempted} "
                f"instances, and a 95% interval needs at least {MINIMUM} — below that its "
                "2.5% tail is under one instance, so the endpoint is the most extreme "
                "instance rather than a quantile"
            )
    return Curve(
        family=family.slug,
        family_version=family.version,
        points=tuple(sorted(points, key=lambda point: point.size)),
    )


def cap(family: Family, measured: Curve) -> int | None:
    """The largest size that clears *and* below which every measured size clears, or `None`.

    A prefix, not a maximum. The Charter's §Capability metric asks for the largest `n` such
    that `n` and every measured size below it clears, which means the walk up the curve stops
    at the first failure and a size that clears above it is not reported. On families whose
    capability falls away as size grows, such a point is evidence about the instance set
    rather than about the system — either the failed size is unrepresentative or the high one
    is — and taking the maximum is the reading that flatters.

    `None` is a real answer — "this arm does not clear at the smallest size we measured" — and
    is not the same as zero, which would be a size somebody could have measured.

    Refuses a curve whose family version does not match. That check exists because the failure
    it prevents is silent: a checker edited between two arms' runs produces two curves that
    compare perfectly and mean nothing.
    """
    if measured.family != family.slug or measured.family_version != family.version:
        raise TaskError(
            f"this curve is {measured.family}@{measured.family_version} and the family is "
            f"{family.slug}@{family.version}; a curve measured against another version of the "
            "checker is a curve about another family"
        )
    reached: int | None = None
    for point in measured.points:  # size-ordered by `curve`
        if not point.clears(family.threshold):
            break
        reached = point.size
    return reached


def margin(family: Family, candidate: Curve, control: Curve) -> tuple[float, float]:
    """A 95% interval on `cap(candidate) - cap(control)`, by resampling both curves.

    Protocol step 5: a separation may be claimed only when this interval excludes zero. Two
    `cap` numbers that differ are not a separation — `cap` is a step function of the scores,
    so one instance flipping at the threshold size moves it by a whole size, and a difference
    that large can come out of two identical systems.

    **The resampled `cap` uses the mean alone, not the mean and the interval.** `Point.clears`
    asks for both because a single curve's `cap` must not move when somebody reruns the same
    instances; a bootstrap over `cap` measures exactly that movement, directly. Applying both
    would count the same uncertainty twice, and it would do so as a bootstrap inside a
    bootstrap — four million resamples for a number that does not get better. Stated here
    because it is a choice, not an oversight.

    **An undefined `cap` counts as zero, and only here.** `cap` returns `None` for an arm that
    does not clear the smallest measured size, which is not a size anybody measured. A margin
    needs a number, and "below every size on this curve" is ordinally below all of them, so
    zero is the reading that preserves the order. Everywhere else `None` stays `None`.
    """
    for measured in (candidate, control):
        if measured.family != family.slug or measured.family_version != family.version:
            raise TaskError(
                f"this curve is {measured.family}@{measured.family_version} and the family is "
                f"{family.slug}@{family.version}; two arms are compared on one checker"
            )
    if candidate.sizes != control.sizes:
        raise TaskError(
            f"the arms were measured at {candidate.sizes} and {control.sizes}; "
            "CHARTER.md §Matched-capability protocol step 3: the identical instance set"
        )

    left = tuple((point.size, point.scores) for point in candidate.points)
    right = tuple((point.size, point.scores) for point in control.points)
    rng = random.Random(version_of(repr((left, right)).encode("utf-8")))
    differences = sorted(
        _resampled(rng, left, family.threshold) - _resampled(rng, right, family.threshold)
        for _ in range(RESAMPLES)
    )
    tail = (1.0 - CONFIDENCE) / 2.0
    return (
        differences[int(tail * RESAMPLES)],
        differences[min(RESAMPLES - 1, int((1.0 - tail) * RESAMPLES))],
    )


def _resampled(
    rng: random.Random, points: tuple[tuple[int, tuple[float, ...]], ...], threshold: float
) -> int:
    """One bootstrap draw of a curve's `cap`, on the mean alone. Zero for undefined."""
    reached = 0
    for size, scores in points:  # size-ordered by `curve`
        drawn = [rng.choice(scores) for _ in scores]
        if sum(drawn) / len(drawn) < threshold:
            break
        reached = size
    return reached


@cache
def interval(scores: tuple[float, ...]) -> tuple[float, float]:
    """A 95% percentile bootstrap interval on the mean. Deterministic, and cached.

    Seeded from the scores themselves rather than from a clock or a global, so the same scores
    give the same interval in any process and in any order — the property that makes a `cap`
    reproducible. Python randomises string hashing per process, so the seed is a content hash
    and not `hash()`; the same trap the vault projection has a test for.
    """
    if len(scores) < MINIMUM:
        raise TaskError(f"a 95% interval needs at least {MINIMUM} scores, got {len(scores)}")
    rng = random.Random(version_of(repr(scores).encode("utf-8")))
    attempted = len(scores)
    means = sorted(
        sum(rng.choice(scores) for _ in range(attempted)) / attempted for _ in range(RESAMPLES)
    )
    tail = (1.0 - CONFIDENCE) / 2.0
    return means[int(tail * RESAMPLES)], means[min(RESAMPLES - 1, int((1.0 - tail) * RESAMPLES))]
