"""The candidate families, their priors, and what would make us stop funding each one.

AGENTS.md §Candidate portfolio lists nine families and calls them "priors, not endorsements",
which is the whole of the design brief: a list of things somebody thought were worth looking
at, with numbers attached so the numbers can be wrong in public. They are here as data rather
than as prose for the same reason `evidence.seeds` is — a portfolio whose priors live in
somebody's session is a portfolio nobody can check.

**Every family declares what would kill it, and each one is different.** A table of nine
identically-worded kill criteria would be a table nobody wrote, so each names the chartered
task family where that paradigm's advantage is *supposed* to be largest, and says what it
would mean to lose there. Killing a family where it should be strongest is the cheapest
refutation available, which is the whole allocation policy in one sentence.

**The control arm is mandatory** (AGENTS.md §Candidate portfolio), and it is in this list
rather than beside it: sparse-conditional and mixture-routed architectures are the
"transformers, but not really" arm, and they are the one family whose *success* is bad news
for the question — if better routing wins, nobody needed a new paradigm. `CONTROL_ARM` names
it so that a portfolio missing its control arm is a test failure and not a review comment.

**The cheapest falsifier available today is a literature survey, not a bench.** `survey`
builds one wager per family out of machinery Phase 6 already shipped: search the allowlist for
a matched-capability, matched-energy measurement on the family's own strongest ground, and
resolve every citation. It costs wall-clock and somebody's reading time, which is one to three
orders of magnitude less than building an arm. If the measurement is already in the
literature, the wager settles for the price of finding it; if it is not, the verdict is
`inconclusive` and never `refuted`, because a missing source is not a refutation (ADR 0009).

Deletion criterion: this module holds the wager that g0rd0n is betting on a declared field
rather than on whatever it happened to read last. Delete it and
`the_portfolio_declares_a_kill_criterion_for_every_family`,
`the_control_arm_is_in_the_portfolio` and
`allocator_prefers_the_cheaper_of_two_equally_informative_wagers` lose the field they range
over, priors stop being numbers anybody wrote down, and "this family is still standing" stops
being distinguishable from "nobody has tried to kill this family".
"""

from dataclasses import dataclass

from g0rd0n.cortex.wager import Wager
from g0rd0n.evidence.channel import sources_for
from g0rd0n.kernel import AssertionId, Bridge, Claim, Provenance, Ref
from g0rd0n.ledger import Cost

#: Where the list came from. AGENTS.md, saying out loud that these are priors and not
#: endorsements — which is exactly the provenance a prior deserves.
SOURCE = Ref("source", "agents-md-candidate-portfolio")

METHOD = "AGENTS.md §Candidate portfolio (priors, not endorsements), transcribed"

#: The family whose success would answer the question in the boring direction. AGENTS.md makes
#: the control arm mandatory; naming it here makes "the portfolio has one" checkable.
CONTROL_ARM = "sparse-conditional-routing"

#: What one literature survey costs: an afternoon of wall-clock across the allowlist, and an
#: hour of somebody reading what comes back. Uniform across families because it is the same
#: procedure pointed at nine different literatures — which means the shipped ranking is driven
#: entirely by `P(flip) x value(flip)`, and the allocator's price term does no work until a
#: bench wager arrives to compete with these.
SURVEY_PRICE = Cost(seconds=1800.0, human_seconds=3600.0)


@dataclass(frozen=True)
class Family:
    """One candidate paradigm, its prior, and the ground it would have to lose on."""

    slug: str
    what: str
    arena: str
    prior: float
    kill: str

    @property
    def ref(self) -> Ref:
        """The hypothesis the whole family is: `hypothesis:predictive-coding`."""
        return Ref("hypothesis", self.slug)

    @property
    def killer(self) -> Ref:
        """The observation that would end it, named before anything is spent looking."""
        return Ref("observation", f"{self.slug}-kill")

    @property
    def control_arm(self) -> bool:
        return self.slug == CONTROL_ARM


#: The nine, in AGENTS.md's order. Priors are stated so that they can be wrong in public and
#: are not a distribution: the families are not mutually exclusive, several could separate, and
#: nothing here needs them to sum to anything.
FAMILIES: tuple[Family, ...] = (
    Family(
        slug="predictive-coding",
        what="predictive coding and active inference",
        arena="T2 online adaptation with no training phase",
        prior=0.20,
        kill=(
            "on T2, at every B in a swept range and with P/N matched, the best available "
            "predictive-coding implementation's cap fails to exceed the tuned control arm's "
            "by a margin whose 95% interval excludes zero. T2 is where a paradigm that "
            "learns at inference time should be furthest ahead, because the control arm has "
            "to spend P to get there and this one claims not to."
        ),
    ),
    Family(
        slug="spiking-neuromorphic",
        what="spiking and event-driven computation on neuromorphic substrates",
        arena="T3 sparse event streams",
        prior=0.25,
        kill=(
            "on T3, a wall-plug measurement (not an analytic estimate, and not a per-synop "
            "figure) shows no cap advantage over the tuned control arm at equal B — or the "
            "advantage exists only in estimates and vanishes on every substrate that can "
            "actually be metered. Sparse streams are where event-driven silicon should win "
            "by the largest margin, so this is the cheapest place to find out that it does not."
        ),
    ),
    Family(
        slug="equilibrium-propagation",
        what="equilibrium propagation and analog in-memory learning",
        arena="T2 online adaptation with no training phase",
        prior=0.15,
        kill=(
            "amortised P/N at the declared deployment population is no better than the "
            "control arm's on any chartered family once conversion, calibration drift and "
            "device yield are counted in P. This family's claim is about the cost of "
            "preparation, so it is the preparation budget that has to be beaten, and the "
            "analog-to-digital boundary is where the joules usually reappear."
        ),
    ),
    Family(
        slug="hyperdimensional-computing",
        what="hyperdimensional computing and vector-symbolic architectures",
        arena="T1 state tracking under composition",
        prior=0.15,
        kill=(
            "on T1, cap saturates at a composition depth no greater than the control arm's "
            "at equal B, or holding it requires a dimension whose energy per binding "
            "operation puts the run outside B. Binding and unbinding is this family's entire "
            "claim to compositional depth; if depth is bounded by the same B here, the claim "
            "is a re-encoding rather than a separation."
        ),
    ),
    Family(
        slug="energy-based-associative",
        what="energy-based and Hopfield-style associative models",
        arena="T1 state tracking under composition",
        prior=0.12,
        kill=(
            "on T1, the settling dynamics need more serial steps inside B than the control "
            "arm needs chain-of-thought tokens, for equal cap — i.e. the iterative depth is "
            "bought at a worse joules-per-step rate than autoregression. Modern associative "
            "models buy depth by iterating; under this Charter iterations are billed, so "
            "the comparison is a bill against a bill."
        ),
    ),
    Family(
        slug="program-synthesis-mdl",
        what="program synthesis and compression-driven induction, MDL and Solomonoff-flavoured",
        arena="T2 online adaptation with no training phase",
        prior=0.18,
        kill=(
            "on T2, recovery time after a change point is no better than the control arm's "
            "at equal B, or reaching it requires a search whose energy exceeds B per "
            "instance. Sample efficiency is this family's claim, and under S4 sample "
            "efficiency has to show up as joules: a search that finds the right program by "
            "spending a week of GPU is not adaptation, it is training with extra steps."
        ),
    ),
    Family(
        slug="neural-cellular-automata",
        what="neural cellular automata and local-update systems",
        arena="T1 state tracking under composition",
        prior=0.10,
        kill=(
            "on T1, the number of local update rounds needed to hold a composition of depth "
            "n grows at least as fast as the control arm's serial steps at equal B, so cap "
            "is bounded by the same budget. Local updates are supposed to buy global "
            "structure cheaply; if the round count tracks the depth, the locality bought "
            "nothing."
        ),
    ),
    Family(
        slug="reservoir-physical-computing",
        what="reservoir and physical computing",
        arena="T3 sparse event streams",
        prior=0.12,
        kill=(
            "on T3, cap at equal B is no better than the control arm's once the readout "
            "layer's training energy is counted in P rather than assumed free. The physical "
            "substrate being free is the claim; the readout is where the energy hides, and a "
            "reservoir whose readout costs what a transformer costs has separated nothing."
        ),
    ),
    Family(
        slug=CONTROL_ARM,
        what=(
            "sparse-conditional and mixture-routed architectures, the "
            "transformers-but-not-really arm"
        ),
        arena="T1 state tracking under composition",
        prior=0.30,
        kill=(
            "on any chartered family, cap at equal B is no better than a dense transformer "
            "control arm's — at which point routing is an implementation detail rather than "
            "a candidate. Note the asymmetry: this family *succeeding* is the worst outcome "
            "for the question, because it answers 'nobody needed a new paradigm, they needed "
            "better routing', and that is a result worth reaching cheaply and early."
        ),
    ),
)


def provenance() -> Provenance:
    return Provenance(SOURCE, METHOD)


def commit(bridge: Bridge, question: Ref) -> tuple[AssertionId, ...]:
    """Put the families and their kill criteria under a question. Idempotent.

    Two edges per family: the family as a hypothesis the question asks, at its declared prior,
    and the observation that would end it. The kill edge is committed here rather than left to
    the first wager because AGENTS.md asks for "explicit kill criteria per family" — a family
    with no stated way to lose should not be fundable even before anybody prices a test of it.

    Idempotence is keyed on `SOURCE` already supporting the claim, the same way
    `evidence.seeds.commit` is: asking whether the entity exists would be answered by any edge
    pointing at it, including the `tests` edge a wager adds.
    """
    committed: list[AssertionId] = []
    for family in FAMILIES:
        asked = Claim(question, "hypothesises", family.ref, family.prior)
        if SOURCE in sources_for(asked, bridge=bridge):
            continue
        committed.append(bridge.hypothesise(asked, provenance()))
        committed.append(
            bridge.hypothesise(
                Claim(family.ref, "kills", family.killer, 1.0),
                Provenance(SOURCE, f"{METHOD}; kill criterion for {family.slug}: {family.kill}"),
            )
        )
    return tuple(committed)


def survey(family: Family, question: Ref) -> Wager:
    """The cheapest falsifier that exists today for one family: read, do not build.

    The test is Phase 6's machinery pointed at the family's strongest ground. Its kill
    criterion is the family's own, qualified by what a survey can actually observe: *a
    retrievable primary source reporting* the measurement. Finding nothing is `inconclusive`
    and never `refuted` — a missing source is not a source that disagrees (ADR 0009), and a
    survey that could refute by silence would delete every family whose literature is on a
    host nobody allowlisted.
    """
    return Wager(
        label=f"w-survey-{family.slug}",
        question=question,
        hypothesis=family.ref,
        claim=(
            f"{family.what} attains a cap on {family.arena} that no honestly-tuned transformer "
            "control arm attains at the same B, P and N (CHARTER.md §Question)."
        ),
        resource=(
            "energy in joules at the wall: B per instance and P amortised over N, as "
            "CHARTER.md §Resource held fixed defines them. The survey reads what other "
            "people held fixed and rejects anything that held nothing fixed."
        ),
        task_family=family.arena,
        test=(
            "search the allowlist for primary reports of matched-capability, matched-energy "
            "measurements of this family on its chartered arena; resolve every citation "
            "against its bytes; read cap and J_solved for both arms, with the budgets they "
            "were measured at, and reject any report whose control arm was not tuned"
        ),
        instrument=(
            "instruments.search.Arxiv over export.arxiv.org, and evidence.citation.resolve, "
            "which refuses a citation whose retrieved bytes do not contain what it claims"
        ),
        kill=f"a retrievable primary source reports that {family.kill}",
        price=SURVEY_PRICE,
        prior=family.prior,
    )


def surveys(question: Ref) -> tuple[Wager, ...]:
    """One survey wager per family, in `FAMILIES` order."""
    return tuple(survey(family, question) for family in FAMILIES)
