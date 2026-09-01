"""Phase 8a: the chartered task families, and the capability metric over their scores.

Nothing here needs `knk`, a network, or a model. That is the point of the split: the half of
the Bench that decides what a question is and what a score means should be checkable by one
person on a laptop, and the half that decides what a joule is arrives with a meter.
"""

import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from g0rd0n.instruments import capability, tasks
from g0rd0n.instruments.capability import MINIMUM, Point, cap, curve, interval
from g0rd0n.instruments.tasks import CUES, LABELS, REACH, Family, Instance, TaskError

T1 = tasks.family("T1")
T2 = tasks.family("T2")
T3 = tasks.family("T3")


def solve(family: Family, instance: Instance) -> str:
    """A reference answer, recomputed independently of the checker.

    Deliberately a second implementation. A test that asked the checker for the answer and
    then fed it back would pass against any checker whatsoever, including one that scores
    everything 1.0.
    """
    if family.slug == "T1":
        state = [1, 2, 3, 4, 5]
        for step in instance.data.split():
            left, right = (int(part) - 1 for part in step.split("-"))
            state[left], state[right] = state[right], state[left]
        return " ".join(str(entry) for entry in state)
    if family.slug == "T2":
        stream, _, query = instance.data.rpartition(" ? ")
        cue, _, label = stream.rsplit(" / ", 1)[-1].split()[0].partition("=")
        offset = (LABELS.index(label) - CUES.index(cue)) % len(LABELS)
        return LABELS[(CUES.index(query) + offset) % len(LABELS)]
    hits = []
    for index, token in enumerate(instance.data):
        if token != "B":
            continue
        window = instance.data[max(0, index - REACH) : index]
        if "A" in window and window.rindex("A") > (window.rindex("C") if "C" in window else -1):
            hits.append(index)
    return " ".join(str(index) for index in hits)


def scores(size: int, correct: int, wrong: int) -> Point:
    """A point with a known mean, for testing the metric rather than the tasks."""
    return Point(size=size, scores=(1.0,) * correct + (0.0,) * wrong)


# --- the families ------------------------------------------------------------------------


def test_the_charters_three_families_are_the_ones_that_exist() -> None:
    """CHARTER.md §Task families charters T1, T2 and T3, and a fourth is a new Charter."""
    assert [family.slug for family in tasks.FAMILIES] == ["T1", "T2", "T3"]
    assert [family.threshold for family in tasks.FAMILIES] == [0.9, 0.8, 0.9]
    with pytest.raises(TaskError, match="not a chartered task family"):
        tasks.family("T4")


@pytest.mark.parametrize("family", tasks.FAMILIES, ids=lambda family: family.slug)
def test_a_reference_answer_scores_one_and_a_wrong_one_does_not(family: Family) -> None:
    """The floor under everything else: the checkers can tell right from wrong."""
    for seed in range(20):
        instance = family.instance(12, seed)
        assert family.score(instance, solve(family, instance)) == 1.0
        assert family.score(instance, "0") < 1.0


@pytest.mark.parametrize("family", tasks.FAMILIES, ids=lambda family: family.slug)
def test_a_checker_scores_a_malformed_answer_as_wrong_rather_than_raising(
    family: Family,
) -> None:
    """definitions.md §Checker: totality.

    A checker that raises on a malformed answer has invented a third category between right
    and wrong, and whoever aggregates the run gets to decide what it means. Every one of these
    is a wrong answer, and every one of them scores as one.
    """
    instance = family.instance(9, 3)
    for answer in ("", "   ", "I think it is 5 1 3 4 2", "\x00", "nan", "-1", "1.5", "ü" * 300):
        assert 0.0 <= family.score(instance, answer) <= 1.0


@pytest.mark.parametrize("family", tasks.FAMILIES, ids=lambda family: family.slug)
def test_an_answer_with_anything_but_the_answer_in_it_is_wrong(family: Family) -> None:
    """definitions.md §Checker: the contract says the answer and nothing else.

    A checker that skipped the tokens it did not understand would let an arm hedge — a right
    answer with an explanation appended, or with a second guess, would keep most of its
    credit. Scoring the whole answer wrong is what makes the contract a contract, and it is
    the difference between "we measured the arm" and "we measured the arm plus whatever the
    scoring script felt like forgiving".
    """
    instance = family.instance(9, 3)
    right = solve(family, instance)
    assert family.score(instance, right) == 1.0
    assert family.score(instance, f"{right} (I am fairly confident)") == 0.0
    assert family.score(instance, f"The answer is {right}") == 0.0


def test_t3_scores_a_stream_with_nothing_in_it_only_for_reporting_nothing() -> None:
    """The degenerate case the generator never produces, and the checker still has to get.

    `check` is total over every `Instance`, not only the ones `generate` makes, and "nothing
    to find, nothing reported" is a perfect answer rather than a divide by zero. Reporting an
    occurrence that is not there is still wrong.
    """
    empty = Instance(family="T3", size=16, seed=0, question="", data="." * 16)
    assert T3.score(empty, "") == 1.0
    assert T3.score(empty, "3") == 0.0


def test_the_definitions_worked_example_for_t1_does_not_compose() -> None:
    """docs/charter/definitions.md §Task family gives `5 1 3 4 2` for `(1 2)(3 4)(1 5)`.

    It does not compose to that under any reading. Applying the transpositions in order as
    position swaps gives `5 1 4 3 2`; as value swaps, `2 5 4 3 1`; right to left, `2 5 4 3 1`
    and `5 1 4 3 2` respectively. The published answer leaves positions 3 and 4 as it found
    them, which is `(3 4)` having had no effect.

    Pinned as a test rather than fixed in the file, because that file is inside the hash
    `CHARTER.md` names: correcting it supersedes the Charter and costs a fresh signature. This
    is here so that nobody later reconciles the two by changing the code.
    """
    instance = Instance(family="T1", size=3, seed=0, question="", data="1-2 3-4 1-5")
    assert T1.score(instance, "5 1 4 3 2") == 1.0
    assert T1.score(instance, "5 1 3 4 2") == 0.0


def test_t2_withholds_the_queried_cue_since_the_last_change_point() -> None:
    """The family measures adaptation, so it must not be solvable by memory alone.

    An arm that answers with the label the queried cue carried the last time it appeared is
    answering from before the change. The generator withholds that cue from the current
    regime's run precisely so that strategy is wrong, and here it is being wrong.
    """
    stale = 0
    for seed in range(40):
        instance = T2.instance(3, seed)
        stream, _, query = instance.data.rpartition(" ? ")
        runs = stream.split(" / ")
        assert all(not item.startswith(f"{query}=") for item in runs[-1].split())
        remembered = [
            item for run in runs[:-1] for item in run.split() if item.startswith(f"{query}=")
        ]
        if remembered:
            answer = remembered[-1].partition("=")[2]
            stale += 1 if T2.score(instance, answer) == 0.0 else 0
    assert stale > 30, "answering from memory should almost always be answering from before"


def test_t3_always_plants_an_occurrence_so_that_finding_none_is_wrong() -> None:
    """An empty ground truth would score an empty answer 1.0, which is a free point."""
    for seed in range(30):
        instance = T3.instance(64, seed)
        assert solve(T3, instance), "no occurrence to find"
        assert T3.score(instance, "") == 0.0


def test_t3_scores_a_partial_answer_between_zero_and_one() -> None:
    """F1, not exact match: half the occurrences found is worth more than none."""
    instance = T3.instance(200, 7)
    found = solve(T3, instance).split()
    assert len(found) >= 2, "need an instance with room to be partly right"
    partial = T3.score(instance, " ".join(found[: len(found) // 2]))
    assert 0.0 < partial < 1.0
    assert T3.score(instance, " ".join([*found, "999"])) < 1.0


# --- versions and instance sets ------------------------------------------------------------


def test_a_task_familys_version_covers_the_source_of_its_checker() -> None:
    """definitions.md §Checker: versioned by the hash of its source.

    A checker whose behaviour changed and whose version did not is the failure this prevents,
    and it is silent — two arms measured either side of the edit produce curves that compare
    perfectly and mean nothing.
    """
    assert T1.version != T2.version != T3.version
    assert tasks.source() in T1.spec
    assert T1.version == tasks.family("T1").version

    edited = Family(**{**vars(T1), "check": lambda instance, answer: 1.0})
    assert edited.version != T1.version, "a different checker is a different family"


def test_an_instance_set_is_reproducible_from_its_seed() -> None:
    """The same seed builds the same questions, and its version hashes the questions."""
    built = tasks.instances(T1, sizes=(4, 8), count=5, seed=11)
    again = tasks.instances(T1, sizes=(8, 4), count=5, seed=11)
    assert built.instances == again.instances, "argument order changed the set"
    assert built.version == again.version
    assert built.sizes == (4, 8)
    assert len(built.instances) == 10
    assert len(built.at(4)) == 5
    assert len({instance.data for instance in built.at(4)}) == 5, "instances repeat"

    assert tasks.instances(T1, sizes=(4, 8), count=5, seed=12).version != built.version


def test_an_instance_sets_version_is_the_instances_not_the_recipe() -> None:
    """ "The same seed" is only the same set while the generator has not changed.

    A set version derived from `(sizes, count, seed)` would be stable across a generator
    rewrite, which is exactly the case where the two runs quoting it saw different questions.
    """
    built = tasks.instances(T1, sizes=(4, 8), count=3, seed=1)
    tampered = tasks.instances(T1, sizes=(4, 8), count=3, seed=1)
    swapped = tuple(
        Instance(**{**vars(instance), "question": "something else"})
        for instance in tampered.instances
    )
    assert built.version != tasks.InstanceSet(**{**vars(tampered), "instances": swapped}).version


def test_an_instance_set_refuses_what_could_not_be_measured() -> None:
    for sizes, count, why in (((), 5, "no sizes"), ((4, 4), 5, "repeat"), ((4,), 0, "not a")):
        with pytest.raises(TaskError, match=why):
            tasks.instances(T1, sizes=sizes, count=count, seed=1)


def test_a_family_refuses_to_score_another_familys_instance() -> None:
    """A checker pointed at the wrong stream would score it, and the score would be a number."""
    with pytest.raises(TaskError, match="cannot score an instance of"):
        T1.score(T3.instance(64, 1), "5 1 4 3 2")


def test_a_checker_that_returns_a_non_score_is_refused() -> None:
    """A checker returning 1.5 inflates every mean it enters, and inflation looks like skill."""
    generous = Family(**{**vars(T1), "check": lambda instance, answer: 1.5})
    with pytest.raises(TaskError, match="not a score"):
        generous.score(generous.instance(3, 0), "anything")


# --- the capability metric ----------------------------------------------------------------


def test_a_single_size_is_an_accuracy_not_a_curve() -> None:
    """CHARTER.md §Capability metric: raw accuracy alone is not a result under this Charter."""
    with pytest.raises(TaskError, match="is an accuracy, not a curve"):
        curve(T1, (scores(4, MINIMUM, 0),))


def test_a_curve_refuses_a_size_measured_on_too_few_instances() -> None:
    """Below 1/0.025 instances the interval's tail is under one instance wide."""
    with pytest.raises(TaskError, match=f"at least {MINIMUM}"):
        curve(T1, (scores(4, MINIMUM, 0), scores(8, MINIMUM - 1, 0)))


def test_a_cap_needs_its_interval_to_clear_not_just_its_mean() -> None:
    """definitions.md §Capability at a budget, and its worked example.

    The point estimate at the larger size clears 0.9 and the interval does not, so `cap` is
    the smaller size. A `cap` that took the mean alone would move when somebody reran the same
    instances, and a capability that moves under a rerun is not measuring the system.
    """
    measured = curve(T1, (scores(8, 60, 0), scores(12, 55, 5)))
    assert measured.points[1].mean == pytest.approx(55 / 60)
    assert measured.points[1].interval[0] < 0.9
    assert not measured.points[1].clears(0.9)
    assert cap(T1, measured) == 8


def test_a_cap_is_none_when_nothing_clears_rather_than_zero() -> None:
    """Zero is a size somebody measured. `None` is "not at any size we looked at"."""
    assert cap(T1, curve(T1, (scores(4, 30, 30), scores(8, 10, 50)))) is None


def test_a_curve_measured_against_another_version_of_the_checker_is_refused() -> None:
    """Two arms measured either side of a checker edit compare perfectly and mean nothing."""
    measured = curve(T1, (scores(4, MINIMUM, 0), scores(8, MINIMUM, 0)))
    stale = capability.Curve(**{**vars(measured), "family_version": "0123456789ab"})
    with pytest.raises(TaskError, match="another version of the checker"):
        cap(T1, stale)
    with pytest.raises(TaskError, match="another version of the checker"):
        cap(T3, measured)


def test_the_interval_does_not_depend_on_the_global_random_state() -> None:
    """Seeded from the scores' content, so it survives anything else touching `random`."""
    sample = tuple(random.Random(4).choice((0.0, 1.0)) for _ in range(MINIMUM * 2))
    first = interval(sample)
    interval.cache_clear()
    random.seed(99)
    assert interval(tuple(sample)) == first


def test_the_interval_is_the_same_in_a_second_process() -> None:
    """The determinism failure a same-process test cannot see.

    A seed derived from `hash()` or from set iteration would be reproducible inside one
    interpreter and different in the next, so a `cap` would move between two runs of the same
    suite. Same trap the vault has `the_projection_does_not_depend_on_python_hash_ordering`
    for, and the same cure: run it again under a different `PYTHONHASHSEED`.
    """
    intervals = {_interval_under(seed) for seed in ("0", "1", "12345")}

    assert len(intervals) == 1, "the interval depends on per-process hash ordering"
    assert intervals == {repr(interval(BOOTSTRAP_SAMPLE))}


#: A mixed set of scores, wide enough that the two endpoints are not both 1.0.
BOOTSTRAP_SAMPLE = (1.0,) * 55 + (0.0,) * 5

INTERVAL_IN_A_FRESH_PROCESS = (
    "from g0rd0n.instruments.capability import interval\n"
    f"print(repr(interval({BOOTSTRAP_SAMPLE!r})))"
)


def _interval_under(hash_seed: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", INTERVAL_IN_A_FRESH_PROCESS],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    ).stdout.strip()


def test_the_interval_narrows_as_instances_are_added() -> None:
    """A sanity check on the statistics rather than on the code around them."""
    narrow = interval((1.0,) * 190 + (0.0,) * 10)
    wide = interval((1.0,) * 38 + (0.0,) * 2)
    assert wide[1] - wide[0] > narrow[1] - narrow[0] > 0.0


def test_the_bench_reads_only_its_own_source_and_no_configuration() -> None:
    """A family version derived from anything ambient would differ between two machines."""
    module = Path(tasks.__file__)
    assert tasks.source() == module.read_text(encoding="utf-8")
