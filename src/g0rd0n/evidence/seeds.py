"""The seed numbers AGENTS.md asserts without a source, and the audit of them.

AGENTS.md §The Question states five things and says so plainly: "Numbers in this section are
unverified seeds. They enter the kernel as `Hypothesis` with provenance 'AGENTS.md seed,
unverified', and Phase 6 must either corroborate them against primary sources or retract them.
An agent that cites them as established fact has violated the provenance rule."

So they are here as data rather than as prose, committed at a low confidence with the seed
document named as their source, and `AUDIT` is what a primary source was actually found to say
about each. Both halves are in the repository and reviewable in a diff, which is the point: an
audit whose inputs live only in somebody's session is an audit nobody can check.

**What the audit found, in one line each** — the full argument is in `docs/seed-audit.md`:

- Landauer's floor and the transformer circuit-class bound are corroborated by primary
  sources, both retrievable from the allowlist.
- The three neuroscience figures are **not corroborated and not retracted**. Their primary
  literature is journal work on hosts nobody allowlisted, and arXiv is the wrong corpus for
  them. Failing to find a source is not the same as finding one that disagrees, so they keep
  their seed provenance and their low confidence, and `UNVERIFIED` says why.

That last outcome is the honest one and it is load-bearing: `CHARTER.md` denominates the whole
question in watts against a brain, and the brain figure is currently the least supported claim
in the kernel.

Deletion criterion: this module holds the wager that g0rd0n's own founding document gets no
exemption from the provenance rule. Delete it and `seed_claims_enter_as_unverified_hypotheses`
loses its verdict, the numbers in AGENTS.md §The Question become facts by repetition, and the
one thing Phase 6 was told to do first stops being checkable.
"""

from dataclasses import dataclass

from g0rd0n.evidence.channel import Finding, Ingested, belief, ingest, sources_for
from g0rd0n.evidence.citation import arxiv
from g0rd0n.instruments.fetch import Fetcher
from g0rd0n.kernel import Bridge, Claim, Provenance, Ref
from g0rd0n.ledger import Cost, Ledger

#: The question the seed framing asked, superseded by `CHARTER.md` in Phase 5 and still the
#: parent of every claim the seed made about the world.
SEED_QUESTION = Ref("question", "agents-md-seed-framing")

SEED_SOURCE = Ref("source", "agents-md-seed")

SEED_METHOD = "AGENTS.md §The Question, stated without a citation and marked unverified"

#: What an unsourced claim from the project's own constitution is worth before anyone checks
#: it. Low, deliberately: it is a claim somebody made, which is more than nothing and much less
#: than evidence. Corroboration from a real source lifts it; nothing else does.
SEED_CONFIDENCE = 0.3

#: What a primary source that states a result outright is worth. Not 1.0 — a paper's abstract
#: is a paper's own account of itself, and `CEILING` exists so that no pile of these reaches
#: belief without Phase 10's three keys.
SOURCED_CONFIDENCE = 0.9

#: What the audit reserves against its wager. Wall-clock only: the channel fetches, and
#: fetching costs time rather than money. Generous enough for five sources on a slow day, and
#: `spend` raises rather than silently overrunning if it is not.
AUDIT_ESTIMATE = Cost(seconds=120.0)


@dataclass(frozen=True)
class Seed:
    """One thing AGENTS.md asserts, as an entity the kernel can hold an opinion about."""

    hypothesis: Ref
    says: str

    @property
    def claim(self) -> Claim:
        return Claim(SEED_QUESTION, "hypothesises", self.hypothesis, SEED_CONFIDENCE)


LANDAUER = Seed(
    Ref("hypothesis", "landauer-floor-is-3e-21-j-per-bit-at-300k"),
    "Landauer's floor is about 3e-21 J per irreversible bit at 300 K.",
)
BRAIN_POWER = Seed(
    Ref("hypothesis", "brain-runs-at-about-20-w"),
    "A human brain runs on about 20 W, continuously.",
)
SYNAPSE_COUNT = Seed(
    Ref("hypothesis", "brain-has-1e14-to-1e15-synapses"),
    "A human brain has about 1e14 to 1e15 synapses.",
)
SYNAPTIC_EVENT = Seed(
    Ref("hypothesis", "synaptic-event-costs-about-1e-14-j"),
    "A synaptic event costs something like 1e-14 J, many orders above Landauer.",
)
TRANSFORMER_CLASS = Seed(
    Ref("hypothesis", "log-precision-transformers-sit-in-uniform-tc0"),
    "Fixed-depth, log-precision transformers sit inside uniform TC0.",
)

SEEDS: tuple[Seed, ...] = (
    LANDAUER,
    BRAIN_POWER,
    SYNAPSE_COUNT,
    SYNAPTIC_EVENT,
    TRANSFORMER_CLASS,
)

#: What a retrieved primary source was found to say. Each `method` states the extraction
#: precisely enough to repeat — which sentence of which abstract, and any arithmetic done on
#: top of it, because "the paper says so" is not a method.
AUDIT: tuple[Finding, ...] = (
    Finding(
        claim=Claim(SEED_QUESTION, "hypothesises", LANDAUER.hypothesis, SOURCED_CONFIDENCE),
        cites=LANDAUER.hypothesis,
        citation=arxiv("1411.6730v1"),
        method=(
            "abstract states Landauer's bound as 'at least kT ln(2) of heat must be "
            "dissipated' and reports measured dissipation consistent with it; evaluated at "
            "T = 300 K with the SI-defined Boltzmann constant 1.380649e-23 J/K, kT ln 2 = "
            "2.87e-21 J, which the seed's 'about 3e-21 J' matches"
        ),
    ),
    Finding(
        claim=Claim(
            SEED_QUESTION, "hypothesises", TRANSFORMER_CLASS.hypothesis, SOURCED_CONFIDENCE
        ),
        cites=TRANSFORMER_CLASS.hypothesis,
        citation=arxiv("2207.00729v4"),
        method=(
            "abstract states 'We prove that transformers whose arithmetic precision is "
            "logarithmic in the number of input tokens (and whose feedforward nets are "
            "computable using space linear in their input) can be simulated by constant-depth "
            "logspace-uniform threshold circuits'; note this is stronger than the seed's "
            "'believed' and narrower than its unqualified 'uniform', being logspace-uniform "
            "and carrying the feedforward-net condition"
        ),
    ),
    Finding(
        claim=Claim(
            SEED_QUESTION, "hypothesises", TRANSFORMER_CLASS.hypothesis, SOURCED_CONFIDENCE
        ),
        cites=TRANSFORMER_CLASS.hypothesis,
        citation=arxiv("2210.02671v7"),
        method=(
            "abstract states 'We prove that any log-precision transformer can be equivalently "
            "expressed as a first-order logic sentence that ... may also contain majority-vote "
            "quantifiers' and calls it 'the tightest known upper bound'; a second, independent "
            "upper bound on the same class"
        ),
    ),
)

#: Seeds no primary source on the allowlist could be found for, and why. Not retracted:
#: failing to find a source is not finding one that disagrees, and an evidence channel that
#: conflated the two would delete every claim it happened not to look hard enough for.
UNVERIFIED: tuple[tuple[Seed, str], ...] = (
    (
        BRAIN_POWER,
        "the primary literature for whole-brain power is journal work (Kety; Attwell and "
        "Laughlin) on hosts that are not on the allowlist; arXiv returns only papers citing "
        "it, which are secondary summaries the Phase 6 preference rules out",
    ),
    (
        SYNAPSE_COUNT,
        "same: the anatomical counts are journal work, and arXiv's stereology literature is "
        "not the primary record for them",
    ),
    (
        SYNAPTIC_EVENT,
        "not merely unsourced but possibly a category error. The nearest primary figure on "
        "the allowlist, arXiv:1204.3928v1, gives 'about (7±2)e3 glucose molecules per second' "
        "for a typical primate cortical synapse — a power, not an energy per event. The two "
        "agree only if the average firing rate is about 1 Hz, which the seed asserts and does "
        "not source",
    ),
)


@dataclass(frozen=True)
class Audited:
    """What one run of the audit did, and where every seed stands after it."""

    seeded: tuple[int, ...]
    ingested: Ingested
    standing: tuple[tuple[Seed, float], ...]
    unverified: tuple[tuple[Seed, str], ...] = UNVERIFIED


def audit(
    *,
    bridge: Bridge,
    fetcher: Fetcher,
    ledger: Ledger,
    wager_id: str,
    estimate: Cost = AUDIT_ESTIMATE,
) -> Audited:
    """Commit the seeds if they are not there, then ingest what the sources say.

    Re-runnable. The seeds are idempotent, and ingestion skips a claim whose source already
    supports it, so running this twice does not turn two readings of one paper into two papers
    agreeing. Every citation is resolved before anything is committed, so a source that has
    gone off the network fails the audit rather than half-applying it.
    """
    seeded = commit(bridge)
    ingested = ingest(
        AUDIT, bridge=bridge, fetcher=fetcher, ledger=ledger, wager_id=wager_id, estimate=estimate
    )
    return Audited(
        seeded=seeded,
        ingested=ingested,
        standing=tuple((seed, belief(seed.claim, bridge=bridge)) for seed in SEEDS),
    )


def provenance() -> Provenance:
    """Where a seed came from: g0rd0n's own constitution, saying it has no source."""
    return Provenance(source=SEED_SOURCE, method=SEED_METHOD)


def commit(bridge: Bridge) -> tuple[int, ...]:
    """Put the unverified seeds into the kernel, skipping any already there.

    Idempotent, so `g0rd0n evidence seed` twice does not double-count the constitution as two
    sources agreeing with itself. The check asks whether `SEED_SOURCE` already supports this
    exact claim — not whether the hypothesis entity exists. A seed's hypothesis is the *object*
    of its claim, so "does the kernel know this entity" would be answered by any edge pointing
    at it, including a `cites` edge the audit added, and the two seeds with sources would skip
    while the three without would silently re-commit.
    """
    committed = []
    for seed in SEEDS:
        if SEED_SOURCE in sources_for(seed.claim, bridge=bridge):
            continue
        committed.append(bridge.hypothesise(seed.claim, provenance()))
    return tuple(committed)
