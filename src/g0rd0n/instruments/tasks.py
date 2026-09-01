"""The chartered task families: a generator, a size, and a checker, hashed together.

`CHARTER.md` §Task families charters three, and `docs/charter/definitions.md` §Task family
says what one is: a triple `(generate, size, check)`, all three machine-executable and
versioned by content hash, so that "the same family" is a checkable statement rather than a
name two people agree on. This module is that triple, three times, and nothing else. It has no
arms, no meter, and no opinion about which paradigm wins.

**A family is not a dataset.** `generate(size, seed)` makes instances at any size, so a
separation claim can always be attacked by pushing it to larger ones — which is the attack a
fixed dataset makes impossible. `instances` freezes the seed set a wager pre-registers, and
that set's version is the hash of the instances *themselves* rather than of the seed that
produced them: "the same seed" is only the same set while the generator has not changed, and a
generator can change under a stable seed without anybody noticing.

**A checker never raises.** Every `check` here is total over its second argument: prose, an
empty string, a number where a permutation was asked for, and stray Unicode all score zero,
because a checker that raises on a malformed answer has invented a third category between
right and wrong, and that is where a generous evaluation hides. It is enforced by
`a_checker_scores_a_malformed_answer_as_wrong_rather_than_raising` rather than by a
`try/except` here, which would turn a genuinely broken checker into a silent stream of zeroes.

**And a contract is a contract.** A *correct* answer with an explanation appended also scores
zero. A checker that skipped the tokens it did not understand would let an arm hedge — append
a second guess or a sentence of reasoning and keep most of the credit — and the difference
between "we measured the arm" and "we measured the arm plus whatever the scoring script felt
like forgiving" is the whole value of the number. The first draft of the test suite missed
this, because a skip-junk checker satisfies "stays inside [0, 1]" perfectly happily;
`an_answer_with_anything_but_the_answer_in_it_is_wrong` is what catches it.

**A family's version covers its two functions and the whole file besides.** The definitions
file asks for the checker to be "versioned by the hash of its source", and that turns out to
need both halves. The functions on their own are not enough: a checker's behaviour is not
confined to its own `def` — it can call a helper three lines down or read a constant at the
top, and hashing the `def` alone leaves those outside the version, which is a checker that
changed without saying so. The file on its own is not enough either: two `Family` values can
name different callables while the file is byte-identical, and the first draft of this module
did exactly that and versioned them the same, which
`a_task_familys_version_covers_the_source_of_its_checker` now refuses. The price of the
belt-and-braces is that editing T3 re-versions T1, and it is worth paying: it errs towards
refusing a stale comparison and never towards accepting one.

**One arithmetic disagreement with the definitions file, recorded and not fixed.** Its §Task
family worked example composes `(1 2)(3 4)(1 5)` and gives `5 1 3 4 2`. Under the convention
the rest of that example fixes — each transposition swaps the entries at those two positions,
applied left to right — the answer is `5 1 4 3 2`, and no other reading of "compose these"
reproduces the published one: the doc's answer leaves positions 3 and 4 exactly as it found
them, which is `(3 4)` having no effect. This module implements the convention and
`the_definitions_worked_example_for_t1_does_not_compose` pins the arithmetic, so that nobody
later "fixes" the code to match the prose. The prose is inside the hash the Charter names, so
correcting it supersedes the Charter and costs a fresh signature; that is Phase 5's business
and a criticism a superseding charter can quote, not a drive-by edit here.

Deletion criterion: this module holds the wager that a capability claim is a claim about a
family somebody can regenerate. Delete it and `a_task_familys_version_covers_the_source_of_
its_checker`, `an_instance_set_is_reproducible_from_its_seed` and
`a_checker_scores_a_malformed_answer_as_wrong_rather_than_raising` lose their verdicts, and
"we measured cap on T1" becomes a sentence about a benchmark nobody else can build.

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

import inspect
import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from g0rd0n.content import version_of


class TaskError(Exception):
    """A family, or an instance set, is not something this bench could measure with."""


@dataclass(frozen=True)
class Instance:
    """One question, and the machine form its checker reads.

    Two strings, deliberately. `question` is exactly what an arm is shown; `data` is the
    canonical form the checker recomputes the answer from, and it may say more than the
    question does. T2 needs that: its change points are *unannounced*, so the arm cannot see
    where the regime changed and the checker has to.

    A checker that read `question` would be scoring against the prose it happened to be shown,
    which is one edit away from scoring against a hint.
    """

    family: str
    size: int
    seed: int
    question: str
    data: str

    @property
    def name(self) -> str:
        """How this instance is named in a manifest: `T1/6/17`."""
        return f"{self.family}/{self.size}/{self.seed}"


@dataclass(frozen=True)
class Family:
    """One chartered task family: what it asks, how it is sized, and how it is scored.

    `threshold` is the Charter's `θ_T`; `ceiling_seconds` is its `W`, the wall-clock ceiling
    per instance. The Charter requires each family to declare a `W` and does not fix the
    number, so the numbers here are this bench's declaration, made once and versioned with
    everything else — raising one is a new family version and therefore a new comparison.
    """

    slug: str
    what: str
    size_is: str
    answers: str
    threshold: float
    ceiling_seconds: float
    generate: Callable[[int, int], "Instance"]
    check: Callable[["Instance", str], float]

    @property
    def spec(self) -> str:
        """The canonical text the version hashes: what it asks, plus the file that answers."""
        return "\n".join(
            (
                f"family: {self.slug}",
                f"asks: {_flat(self.what)}",
                f"size: {_flat(self.size_is)}",
                f"answer: {_flat(self.answers)}",
                f"threshold: {self.threshold!r}",
                f"ceiling_seconds: {self.ceiling_seconds!r}",
                f"generate:\n{_sourced(self.generate)}",
                f"check:\n{_sourced(self.check)}",
                f"module:\n{source()}",
            )
        )

    @property
    def version(self) -> str:
        return version_of(self.spec.encode("utf-8"))

    def instance(self, size: int, seed: int) -> Instance:
        """One instance, reproducible from `(size, seed)` alone."""
        if size < 1:
            raise TaskError(f"{self.slug}: an instance of size {size} is not an instance")
        return self.generate(size, seed)

    def score(self, instance: Instance, answer: str) -> float:
        """Run the checker, and refuse a score that is not a score.

        A checker that returned 1.5 would inflate every mean it appeared in, and the inflation
        would look like capability. Cheaper to refuse it here than to find it in a curve.
        """
        if instance.family != self.slug:
            raise TaskError(f"{self.slug} cannot score an instance of {instance.family}")
        value = self.check(instance, answer)
        if not 0.0 <= value <= 1.0:
            raise TaskError(f"{self.slug}: a checker returned {value}, which is not a score")
        return value


@dataclass(frozen=True)
class InstanceSet:
    """The pre-registered seed set of a wager: fixed instances, at fixed sizes, by name.

    `version` hashes the instances rather than the recipe. Two runs quoting the same set
    version were shown the same questions, whatever generator produced them and whatever
    version of Python drew the random numbers — which is the property protocol step 3 ("run
    both arms on the identical instance set") actually needs.
    """

    family: str
    family_version: str
    sizes: tuple[int, ...]
    count: int
    seed: int
    instances: tuple[Instance, ...]

    @property
    def manifest(self) -> str:
        """Every instance, in order, in the form the version hashes."""
        return "\n".join(
            f"{instance.name}\t{_flat(instance.question)}\t{_flat(instance.data)}"
            for instance in self.instances
        )

    @property
    def version(self) -> str:
        return version_of(f"{self.family}@{self.family_version}\n{self.manifest}".encode())

    def at(self, size: int) -> tuple[Instance, ...]:
        return tuple(instance for instance in self.instances if instance.size == size)


#: Distinct instances within one size need distinct seeds, and two sets built from different
#: `seed` arguments should not silently share instances. A stride large enough that a set's
#: `count` can never reach the next set's seeds gives both.
STRIDE = 1_000_003


def instances(family: Family, sizes: tuple[int, ...], count: int, seed: int) -> InstanceSet:
    """Build the instance set a wager pre-registers. Deterministic in `(sizes, count, seed)`."""
    if not sizes:
        raise TaskError(f"{family.slug}: an instance set over no sizes is not a set")
    if len(set(sizes)) != len(sizes):
        raise TaskError(f"{family.slug}: sizes repeat, so one size would be measured twice")
    if count < 1:
        raise TaskError(f"{family.slug}: {count} instances per size is not a measurement")
    if count >= STRIDE:
        raise TaskError(f"{family.slug}: more than {STRIDE} instances per size would collide")
    built = tuple(
        family.instance(size, seed * STRIDE + index)
        for size in sorted(sizes)
        for index in range(count)
    )
    return InstanceSet(
        family=family.slug,
        family_version=family.version,
        sizes=tuple(sorted(sizes)),
        count=count,
        seed=seed,
        instances=built,
    )


# --- T1: state tracking under composition -----------------------------------------------

#: The ten transpositions of S5, the two-element swaps that generate the group.
TRANSPOSITIONS: tuple[tuple[int, int], ...] = tuple(
    (left, right) for left in range(1, 6) for right in range(left + 1, 6)
)


def t1_generate(size: int, seed: int) -> Instance:
    """`size` transpositions of S5, to be applied in order to the identity permutation."""
    rng = random.Random(f"T1/{size}/{seed}")
    picks = [rng.choice(TRANSPOSITIONS) for _ in range(size)]
    data = " ".join(f"{left}-{right}" for left, right in picks)
    shown = "".join(f"({left} {right})" for left, right in picks)
    question = (
        "Start from the permutation 1 2 3 4 5. Apply each transposition below in order, "
        "left to right; (a b) swaps whatever currently sits in position a with whatever "
        "currently sits in position b. Answer with the resulting permutation in one-line "
        "notation: the five digits separated by single spaces, and nothing else.\n\n"
        f"{shown}"
    )
    return Instance(family="T1", size=size, seed=seed, question=question, data=data)


def t1_check(instance: Instance, answer: str) -> float:
    """1.0 if the answer is the composed permutation in one-line notation, 0.0 otherwise.

    Spacing is normalised and nothing else is: "5 1 4 3 2" and "5  1 4 3 2" both pass, and
    "I think it is 5 1 4 3 2" does not. The family's contract says the answer is a permutation
    and nothing else, so an answer wrapped in prose is a wrong answer rather than a near miss.
    """
    state = [1, 2, 3, 4, 5]
    for step in instance.data.split():
        left, _, right = step.partition("-")
        first, second = int(left) - 1, int(right) - 1
        state[first], state[second] = state[second], state[first]
    return 1.0 if " ".join(answer.split()) == " ".join(str(entry) for entry in state) else 0.0


# --- T2: online adaptation with no training phase ----------------------------------------

#: The cue alphabet and the label alphabet. A regime is a rotation of the second against the
#: first by an offset the arm is never told, so **one** post-change observation identifies the
#: whole mapping. That is what makes this adaptation rather than memorisation: the queried cue
#: is deliberately absent from the current regime's run, so an arm that only remembers what
#: each cue meant last time it appeared answers with the mapping from before the change.
CUES: tuple[str, ...] = ("a", "b", "c", "d")
LABELS: tuple[str, ...] = ("w", "x", "y", "z")

#: The declared number of instances the Charter allows a system to recover in. Every run of a
#: regime is longer than this, so an arm has seen at least `GRACE` labelled items under the
#: current mapping before it is asked anything: being wrong is a failure to adapt rather than
#: a failure to have been told.
GRACE = 4

#: How long one regime lasts, in items. The lower bound is `GRACE + 2` so the grace allowance
#: is always spent inside the run rather than straddling the next change point.
RUN = (GRACE + 2, GRACE + 8)


def t2_generate(size: int, seed: int) -> Instance:
    """A stream of `cue=label` items whose mapping changes `size - 1` times, unannounced."""
    rng = random.Random(f"T2/{size}/{seed}")
    query = rng.choice(CUES)
    offsets: list[int] = []
    while len(offsets) < size:
        offset = rng.randrange(len(LABELS))
        if not offsets or offset != offsets[-1]:
            offsets.append(offset)

    runs: list[list[str]] = []
    for position, offset in enumerate(offsets):
        # The last run withholds the queried cue: the arm has to infer the new mapping from
        # the other cues and apply it to one it has not seen since the change.
        pool = tuple(cue for cue in CUES if cue != query) if position == len(offsets) - 1 else CUES
        runs.append(
            [f"{cue}={_labelled(cue, offset)}" for cue in rng.choices(pool, k=rng.randint(*RUN))]
        )

    stream = " ".join(item for run in runs for item in run)
    question = (
        "Each item below reads cue=label. Both alphabets are fixed: cues are "
        f"{' '.join(CUES)} and labels are {' '.join(LABELS)}. At any moment the mapping is the "
        "label alphabet rotated against the cue alphabet by an offset you are not told, and "
        "the offset changes at points that are not marked. Using the most recent items, "
        f"answer with the label for {query}: one letter, and nothing else.\n\n{stream}"
    )
    return Instance(
        family="T2",
        size=size,
        seed=seed,
        question=question,
        data=" / ".join(" ".join(run) for run in runs) + f" ? {query}",
    )


def t2_check(instance: Instance, answer: str) -> float:
    """1.0 if the answer is the queried cue's label under the *current* regime.

    The change points the arm could not see are in `data`, marked by `/`. The checker reads
    the last run, recovers the offset from any item in it, and applies that offset to the
    queried cue — so what is scored is the mapping in force at the end of the stream, which is
    the only thing this family is asking about.
    """
    stream, _, query = instance.data.rpartition(" ? ")
    for item in stream.rsplit(" / ", 1)[-1].split():
        cue, _, label = item.partition("=")
        if cue in CUES and label in LABELS and query in CUES:
            offset = (LABELS.index(label) - CUES.index(cue)) % len(LABELS)
            return 1.0 if " ".join(answer.split()) == _labelled(query, offset) else 0.0
    return 0.0


def _labelled(cue: str, offset: int) -> str:
    return LABELS[(CUES.index(cue) + offset) % len(LABELS)]


# --- T3: sparse event streams -------------------------------------------------------------

#: The stream alphabet. `.` is nothing happening, which is most of it.
FILLER = "."
EVENTS: tuple[str, ...] = ("A", "B", "C")

#: What counts as an occurrence: an `A`, then a `B` no more than `REACH` positions later, with
#: no `C` in between. Temporally defined, so it cannot be found by counting symbols.
REACH = 6

#: The fraction of positions carrying an event. Held fixed as the Charter requires, so that
#: size is stream length and nothing else.
DENSITY = 0.12

#: One planted occurrence per this many tokens. At `DENSITY` alone a 200-token stream produces
#: about one A-B pair inside `REACH` by luck, which makes the family a single-needle hunt and
#: F1 a coin toss: the difference between an arm that found nothing and one that found the
#: needle and six phantoms is the whole score. Planting at a rate keeps the occurrence density
#: fixed as the stream lengthens, which is what "size is stream length at fixed event density"
#: has to mean if size is to be the only thing varying.
PLANT = 64


def t3_generate(size: int, seed: int) -> Instance:
    """A stream of `size` tokens, mostly empty, with at least one planted occurrence."""
    if size < REACH + 2:
        raise TaskError(f"T3: a stream of {size} tokens is shorter than one occurrence")
    rng = random.Random(f"T3/{size}/{seed}")
    stream = [FILLER] * size
    for position in range(size):
        if rng.random() < DENSITY:
            stream[position] = rng.choice(EVENTS)

    # Occurrences are planted one per block so that an arm answering "none" is always wrong,
    # an empty ground truth never turns into a free 1.0, and the number to find grows with the
    # stream. Everything else is whatever the density happened to produce, including any extra
    # occurrences it made by accident: the checker recomputes the truth from the finished
    # stream, so nothing here has to keep a list of what it planted.
    planted = max(1, size // PLANT)
    block = size // planted
    for slot in range(planted):
        start = slot * block + rng.randrange(block - REACH - 1)
        gap = rng.randint(1, REACH)
        stream[start] = "A"
        for position in range(start + 1, start + gap):
            if stream[position] == "C":
                stream[position] = FILLER
        stream[start + gap] = "B"

    data = "".join(stream)
    question = (
        "The stream below is one token per position, indexed from 0. An occurrence is an A "
        f"followed by a B no more than {REACH} positions later with no C in between. Answer "
        "with the index of the B that completes each occurrence, ascending, separated by "
        f"single spaces, and nothing else.\n\n{data}"
    )
    return Instance(family="T3", size=size, seed=seed, question=question, data=data)


def t3_check(instance: Instance, answer: str) -> float:
    """F1 of the reported indices against the ground truth, scored to `[0, 1]`.

    Any token that is not a plain integer scores the whole answer 0.0 rather than being
    skipped. Skipping it would let an arm hedge — a list of indices with an explanation
    appended would keep most of its credit — and the family's contract says indices only.
    """
    truth = _t3_occurrences(instance.data)
    reported: set[int] = set()
    for token in answer.split():
        if not token.isdigit():
            return 0.0
        reported.add(int(token))
    if not truth and not reported:
        return 1.0
    if not truth or not reported:
        return 0.0
    hits = len(truth & reported)
    if not hits:
        return 0.0
    precision = hits / len(reported)
    recall = hits / len(truth)
    return 2.0 * precision * recall / (precision + recall)


def _t3_occurrences(stream: str) -> set[int]:
    """The index of every B that completes an occurrence."""
    found: set[int] = set()
    for index, token in enumerate(stream):
        if token != "B":
            continue
        for back in range(1, min(REACH, index) + 1):
            earlier = stream[index - back]
            if earlier == "C":
                break
            if earlier == "A":
                found.add(index)
                break
    return found


#: The three families `CHARTER.md` charters, in its order. Adding a fourth is a superseding
#: Charter, never an append here: a result on a family nobody chartered is a result nobody
#: pre-registered.
FAMILIES: tuple[Family, ...] = (
    Family(
        slug="T1",
        what=(
            "state tracking under composition: compose a sequence of transpositions of S5 and "
            "report the resulting permutation"
        ),
        size_is="the number of transpositions composed",
        answers="the permutation in one-line notation, five digits separated by single spaces",
        threshold=0.9,
        ceiling_seconds=60.0,
        generate=t1_generate,
        check=t1_check,
    ),
    Family(
        slug="T2",
        what=(
            "online adaptation with no training phase: a stream whose cue-to-label mapping "
            "changes at unannounced points, queried on a cue withheld since the last change"
        ),
        size_is="the number of distinct regimes in the stream",
        answers="one label letter",
        threshold=0.8,
        ceiling_seconds=60.0,
        generate=t2_generate,
        check=t2_check,
    ),
    Family(
        slug="T3",
        what=(
            "sparse event streams: find every A followed by a B within a fixed reach with no "
            "C in between, in a long and mostly empty stream"
        ),
        size_is="the stream length, at fixed event density",
        answers="the ascending indices of the completing Bs, separated by single spaces",
        threshold=0.9,
        ceiling_seconds=120.0,
        generate=t3_generate,
        check=t3_check,
    ),
)


def family(slug: str) -> Family:
    """The chartered family with this slug, or a `TaskError` listing the ones there are."""
    for chartered in FAMILIES:
        if chartered.slug == slug:
            return chartered
    known = ", ".join(chartered.slug for chartered in FAMILIES)
    raise TaskError(f"{slug!r} is not a chartered task family; CHARTER.md charters {known}")


@cache
def source() -> str:
    """The bytes every family in this file is versioned against. See the module docstring."""
    return Path(__file__).read_text(encoding="utf-8")


def _sourced(function: Callable[..., object]) -> str:
    """One of a family's two functions, by name and by source.

    The name is in there because two functions can share a body — `check=lambda i, a: 1.0` and
    a copy of it are the same text and not the same thing to a reader of the record. The
    source is in there because a name can be reused.
    """
    try:
        body = inspect.getsource(function)
    except (OSError, TypeError) as exc:
        raise TaskError(
            f"the source of {function!r} cannot be read, so this family cannot be versioned; "
            "definitions.md §Checker requires a checker versioned by the hash of its source"
        ) from exc
    return f"{function.__module__}.{function.__qualname__}\n{body}"


def _flat(text: str) -> str:
    """One field of a hashed rendering, with its whitespace normalised."""
    return " ".join(text.split())
