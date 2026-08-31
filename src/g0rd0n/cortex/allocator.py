"""Cheapest falsifier first: which open Wager to run next, or that there is no point.

AGENTS.md §Phase 7 states the policy and this module is that sentence, arithmetically:

    rank open Wagers by  P(verdict flips the leading candidate) x value(flip) / price

Popper as a budget function. The wager worth running is not the one most likely to succeed —
it is the one that could kill what the programme currently believes, for the least money.

**Read once, then rank purely.** `read` makes one pass over the kernel and returns a `Board`;
`rank` and `allocate` are functions of that value and touch nothing. So the ranking is
deterministic, testable without a running `knk`, and cannot depend on the order two reads
happened to arrive in — the same split `vault.note.render` gets, for the same reason.

**How P(flip) is computed.** The leader is the family with the highest live belief.

- A wager *on the leader* flips the lead by being refuted, so `P(flip) = 1 - prior` and the
  flip is worth `lead - runner_up`: how far the programme falls back when its best candidate
  goes. A leader that towers over the field is worth more to kill than one in a dead heat,
  because more of what happens next is riding on it.
- A wager on a *challenger* flips the lead by being corroborated, and only if that would put
  it in front. Corroboration is modelled with the Evidence Channel's own noisy-OR, so the
  arithmetic here and the arithmetic that will actually move the belief are the same function.
  `P(flip) = prior` when `combine(belief, prior) > lead`, and **zero** otherwise, worth the
  margin it would win by.

That zero is load-bearing. ADR 0001 names wager inflation — slicing work into many small
wagers so each looks cheap — as a failure mode, and the answer is that a wager which cannot
flip anything ranks last however cheap it is. Cheapness is a divisor, never a reason.

**Price is denominated in dollars and somebody's attention**, and a wager priced in neither is
refused rather than guessed at. This mirrors `config.price_of`: there is no default model
price because a number nobody chose would sit in the ledger forever. Here it would sit in a
ranking forever, which is cheaper to be wrong about and still not free.

**Stopping rules.** AGENTS.md asks for three. Two are here — per-family patience, and the
"this question is exhausted" trigger that hands control back to the Question Engine with the
criticisms a new Charter would have to answer. The third, the per-Wager price cap, is already
the pre-registered price: `Ledger.spend` raises `Overspend` past the reservation and
`cortex.wager.reserve` reserves exactly what the wager registered. Building a second cap here
would be a second way to express something the Wager already expresses, which The Imperative
(1) forbids.

Deletion criterion: this module holds the wager that what gets spent on next is decided by
what could be killed cheapest, rather than by what is most interesting to work on. Delete it
and `allocator_prefers_the_cheaper_of_two_equally_informative_wagers` and
`exhausted_question_triggers_reformulation_not_more_spending` lose their verdicts, a family
that nothing has tried to kill stops being distinguishable from one that survived a test, and
"what should we do next" goes back to being answered by whoever is in the room.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from g0rd0n.cortex.portfolio import Family
from g0rd0n.cortex.wager import Wager
from g0rd0n.evidence.channel import DEAD, combine
from g0rd0n.kernel import Bridge, Ref
from g0rd0n.ledger import Cost

#: How many settled-but-unsettling wagers a family gets before it stops being fundable. Three
#: tries that produced no verdict is not evidence about the family — it is evidence that the
#: tests cannot settle it, which is a fact about the question and belongs in a criticism of the
#: Charter rather than in a refutation of the paradigm.
PATIENCE = 3

#: What an hour of somebody's attention is worth **to the ranking**. A weight, not a price: it
#: never enters the ledger, never appears in a `Cost`, and no reservation is ever made from it.
#: It exists because a wager costing forty hours of a person's reading and no dollars is not
#: free, and a ranking that treated it as free would put it first every time.
HUMAN_USD_PER_HOUR = 100.0

#: The dimensions the ranking is denominated in. Wall-clock is excluded because waiting is not
#: scarce here; GPU-seconds because they are bought with dollars and a wager that spends them
#: should say so in dollars.
PRICED = ("usd", "human_seconds")


class AllocationError(Exception):
    """A wager could not be ranked as described."""


@dataclass(frozen=True)
class Standing:
    """Where one candidate family stands: what it is believed at, and what has been tried."""

    family: Family
    belief: float
    attempts: int
    settled: int
    conclusive: int
    refuted: bool

    @property
    def untested(self) -> bool:
        """AGENTS.md §Phase 7: a family surviving only because nobody tried to kill it.

        The flag exists because an untested family and a family that survived three honest
        attempts look identical from the belief number alone, and they are the opposite of
        each other.
        """
        return self.attempts == 0

    @property
    def out_of_patience(self) -> bool:
        return self.settled - self.conclusive >= PATIENCE

    @property
    def live(self) -> bool:
        """Still worth spending on: not refuted, and not out of patience."""
        return not self.refuted and not self.out_of_patience


@dataclass(frozen=True)
class Board:
    """The kernel read once: every family, sorted best-believed first.

    Ties break on slug, so two families believed equally produce the same board whichever
    order the kernel handed them back in.
    """

    question: Ref
    standings: tuple[Standing, ...]

    @property
    def leader(self) -> Standing | None:
        """The live family with the highest belief, or `None` when none is left."""
        return next((standing for standing in self.standings if standing.live), None)

    @property
    def lead(self) -> float:
        leader = self.leader
        return leader.belief if leader is not None else 0.0

    @property
    def runner_up(self) -> float:
        """The belief the programme falls back to if the leader goes. Zero if nothing else."""
        live = [standing.belief for standing in self.standings if standing.live]
        return live[1] if len(live) > 1 else 0.0

    def standing_for(self, hypothesis: Ref) -> Standing | None:
        return next((s for s in self.standings if s.family.ref == hypothesis), None)


@dataclass(frozen=True)
class Ranked:
    """One wager, scored, with the arithmetic left visible.

    `flip`, `value` and `price` are kept beside the score rather than folded into it because a
    ranking nobody can argue with is a ranking nobody checked.
    """

    wager: Wager
    score: float
    flip: float
    value: float
    price: float
    why: str


@dataclass(frozen=True)
class Next:
    """What to spend on next. `run` is the wager; `ranking` is everything, for the argument."""

    run: Ranked
    ranking: tuple[Ranked, ...]


@dataclass(frozen=True)
class Exhausted:
    """Nothing left worth spending on. Control returns to the Question Engine (Phase 5).

    Deliberately has **no** field naming a wager to run. AGENTS.md §Phase 7 asks that an
    exhausted question trigger reformulation rather than more spending, and a result carrying
    a "best remaining" wager is an invitation to spend on it anyway. `ranking` is here for the
    explanation only — everything in it scored zero, which is why there is nothing to run.

    `criticisms` are sentences a superseding Charter could put under its `## Criticisms`
    heading. The Question Engine refuses a supersession without one (ADR 0007), so an
    exhausted question that produced none would be a dead end rather than a handover.
    """

    reason: str
    criticisms: tuple[str, ...]
    ranking: tuple[Ranked, ...]


def read(bridge: Bridge, question: Ref, families: Sequence[Family]) -> Board:
    """One pass over the kernel: what each family is believed at, and what has been tried.

    `changes_since(0)` is the enumeration path, as it is for the vault — every assertion ever
    recorded, whatever its status. Retracted claims and retractions are dropped; superseded
    ones are not, because a superseded attempt was still an attempt.

    Reading everything is deliberate rather than lazy. The question a family's `attempts` count
    answers is "has *anything* tried to kill this", and asking the wagers we happen to be
    holding would answer "has anything on this list tried to kill this" — which would report a
    family as untested because the wager that tested it was in another file.
    """
    names: dict[int, Ref] = {}
    predicates: dict[int, str] = {}

    def name(entity_id: int) -> Ref:
        if entity_id not in names:
            names[entity_id] = bridge.name_of(entity_id)
        return names[entity_id]

    def predicate(predicate_id: int) -> str:
        if predicate_id not in predicates:
            predicates[predicate_id] = bridge.predicate_of(predicate_id)
        return predicates[predicate_id]

    beliefs: dict[Ref, float] = {}
    tests: dict[Ref, set[Ref]] = {}
    measured: dict[Ref, set[Ref]] = {}
    argued: dict[Ref, set[Ref]] = {}
    refuted: set[Ref] = set()

    for assertion in bridge.changes_since(0):
        if assertion.status in DEAD:
            continue
        edge = predicate(assertion.predicate)
        subject, obj = name(assertion.subject), name(assertion.object)
        if edge == "hypothesises" and subject == question:
            beliefs[obj] = max(beliefs.get(obj, 0.0), assertion.confidence)
        elif edge == "tests":
            tests.setdefault(obj, set()).add(subject)
        elif edge == "measures":
            measured.setdefault(subject, set()).add(obj)
        elif edge in {"refutes", "corroborates"}:
            argued.setdefault(obj, set()).add(subject)
            if edge == "refutes":
                refuted.add(obj)

    standings = []
    for family in families:
        attempts = tests.get(family.ref, set())
        results = argued.get(family.ref, set())
        settled = [e for e in attempts if measured.get(e, set())]
        standings.append(
            Standing(
                family=family,
                belief=beliefs.get(family.ref, 0.0),
                attempts=len(attempts),
                settled=len(settled),
                conclusive=sum(1 for e in settled if measured[e] & results),
                refuted=family.ref in refuted,
            )
        )
    return Board(
        question=question,
        standings=tuple(sorted(standings, key=lambda s: (-s.belief, s.family.slug))),
    )


def price_of(wager: Wager) -> float:
    """What a wager costs, as one number, for the ranking's divisor only.

    Raises rather than guessing. A wager priced entirely in GPU-seconds is not cheap — it is a
    wager that did not say what its GPU time costs — and ranking it as free would put it first
    forever. Same discipline as `Config.price_of`, one layer up and with less at stake.
    """
    price: Cost = wager.price
    total = price.usd + price.human_seconds * HUMAN_USD_PER_HOUR / 3600.0
    if total <= 0.0:
        raise AllocationError(
            f"{wager.id} states no price in {' or '.join(PRICED)}, so it cannot be ranked "
            "against wagers that do. Price it in the currency the ranking is denominated in "
            "rather than letting the allocator invent a number for it."
        )
    return total


def score(board: Board, wager: Wager) -> Ranked:
    """`P(flip) x value(flip) / price`, with every term kept where it can be argued with."""
    price = price_of(wager)
    standing = board.standing_for(wager.hypothesis)
    if standing is None:
        return Ranked(wager, 0.0, 0.0, 0.0, price, "not a family on this board")
    if not standing.live:
        why = "refuted" if standing.refuted else f"out of patience after {standing.settled} tries"
        return Ranked(wager, 0.0, 0.0, 0.0, price, f"{standing.family.slug} is {why}")

    leader = board.leader
    if leader is not None and standing.family.ref == leader.family.ref:
        flip, value = 1.0 - wager.prior, board.lead - board.runner_up
        why = f"refuting the leader drops the field to {board.runner_up:.2f}"
    else:
        after = combine(standing.belief, wager.prior)
        flips = after > board.lead
        flip = wager.prior if flips else 0.0
        value = max(0.0, after - board.lead)
        why = (
            f"corroboration would take it to {after:.2f}, past {board.lead:.2f}"
            if flips
            else f"corroboration would reach only {after:.2f}, short of {board.lead:.2f}"
        )
    return Ranked(wager, flip * value / price, flip, value, price, why)


def rank(board: Board, wagers: Sequence[Wager]) -> tuple[Ranked, ...]:
    """Every wager, best first. Ties break on wager id, so the ranking is a function."""
    return tuple(sorted((score(board, w) for w in wagers), key=lambda r: (-r.score, r.wager.id)))


def allocate(board: Board, wagers: Sequence[Wager]) -> Next | Exhausted:
    """What to run next, or that the question is exhausted and belongs back in Phase 5.

    Exhaustion is not "we ran out of money" — that is `BudgetExhausted`, which says nothing
    about the world. It is "nothing we could afford to run could change what we believe", which
    says a great deal, and the answer to it is a better question rather than a bigger budget.
    """
    ranking = rank(board, wagers)
    best = ranking[0] if ranking else None
    if best is not None and best.score > 0.0:
        return Next(run=best, ranking=ranking)
    return Exhausted(
        reason=_why_exhausted(board, ranking), criticisms=criticisms(board), ranking=ranking
    )


def criticisms(board: Board) -> tuple[str, ...]:
    """What a superseding Charter would have to answer, read off the board.

    One sentence per family whose standing is a complaint about the *question* rather than
    about the paradigm: a family refuted, a family whose tests keep settling nothing, and a
    family still standing that nothing ever tried to kill. Each is something the current
    question failed to do, which is what a criticism is for.
    """
    found = []
    for standing in board.standings:
        family = standing.family
        if standing.refuted:
            found.append(
                f"{family.what} was refuted on {family.arena}, and this question still ranges "
                "over it; a question whose field has shrunk should say what it now asks."
            )
        elif standing.out_of_patience:
            found.append(
                f"{standing.settled} wagers on {family.what} settled without a verdict, so "
                f"{family.arena} as this question charters it cannot separate that family "
                "from the control arm — the arena or the metric is wrong, not the paradigm."
            )
        elif standing.untested:
            found.append(
                f"{family.what} still stands at {standing.belief:.2f} only because nothing "
                "tried to kill it; this question generated no affordable test for it."
            )
    return tuple(found)


def _why_exhausted(board: Board, ranking: tuple[Ranked, ...]) -> str:
    if not ranking:
        return "no wagers were offered, so there is nothing to choose between"
    if board.leader is None:
        return "every candidate family is refuted or out of patience; the field is empty"
    return (
        f"no offered wager could unseat {board.leader.family.slug} at {board.lead:.2f}; "
        "everything on the board scored zero, so more spending buys no verdict"
    )
