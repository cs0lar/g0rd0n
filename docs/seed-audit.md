# Seed audit — AGENTS.md §The Question

- **Date:** 2026-08-30
- **Phase:** 6b (search, and the seed audit)
- **Run by:** `g0rd0n evidence audit`, against the live arXiv API
- **Data:** `src/g0rd0n/evidence/seeds.py` — this file is the argument, that file is the input

AGENTS.md §The Question states five things and marks them itself:

> **Numbers in this section are unverified seeds.** They enter the kernel as `Hypothesis` with
> provenance `"AGENTS.md seed, unverified"`, and Phase 6 must either corroborate them against
> primary sources or retract them. An agent that cites them as established fact has violated
> the provenance rule.

This is what happened when they were checked.

## Result

| Seed | Standing | Source |
|---|---|---|
| Landauer's floor ≈ 3×10⁻²¹ J per irreversible bit at 300 K | **0.93 — corroborated** | arXiv:1411.6730v1 |
| Log-precision transformers sit inside uniform TC⁰ | **0.95 — corroborated twice, capped** | arXiv:2207.00729v4, arXiv:2210.02671v7 |
| A brain runs on ≈ 20 W | 0.30 — **unverified** | none on the allowlist |
| A brain has ≈ 10¹⁴–10¹⁵ synapses | 0.30 — **unverified** | none on the allowlist |
| A synaptic event costs ≈ 10⁻¹⁴ J | 0.30 — **unverified**, and suspect | see below |

**Nothing was retracted.** No source was found that disagrees with any seed. Failing to find a
source is not the same as finding one that contradicts, and a channel that conflated the two
would delete every claim it happened not to look hard enough for.

## What was corroborated

**Landauer's floor.** arXiv:1411.6730v1, *Experimental verification of Landauer's principle in
erasure of nanomagnetic memory bits*, states the bound in its abstract — "to erase one binary
bit of information from a physical memory element in contact with a heat bath at a given
temperature, at least kT ln(2) of heat must be dissipated" — and reports measured dissipation
"consistent with the Landauer limit" in single-domain magnetic thin-film islands.

The seed's *number* is one step past what the paper states. kT ln 2 at T = 300 K, with the
SI-defined Boltzmann constant 1.380649×10⁻²³ J/K, is 2.87×10⁻²¹ J. The seed's "about 3×10⁻²¹ J"
matches. That arithmetic is recorded in the provenance method rather than assumed, because
"the paper says so" would not be true: the paper gives the formula, and the evaluation at 300 K
is ours.

**The transformer circuit-class bound.** arXiv:2207.00729v4, *The Parallelism Tradeoff*, states:
"We prove that transformers whose arithmetic precision is logarithmic in the number of input
tokens (and whose feedforward nets are computable using space linear in their input) can be
simulated by constant-depth logspace-uniform threshold circuits."

Two corrections to the seed follow, and both were recorded in the provenance rather than
quietly applied:

1. **The seed understates it.** "Believed to sit inside" is the language of a conjecture. It is
   proved.
2. **The seed overstates it.** The seed says "uniform TC⁰" without qualification; the theorem
   gives *logspace*-uniform threshold circuits, which is a weaker uniformity condition, and it
   carries a side condition on the feedforward nets that the seed does not mention.

The second source, arXiv:2210.02671v7, gives an independent upper bound — log-precision
transformers expressed in first-order logic with majority-vote quantifiers, which its abstract
calls "the tightest known upper bound" — and lifted the claim to the corroboration ceiling of
0.95. It stops there by design: no quantity of citation reaches belief, and promotion needs
Phase 10's three keys.

## What could not be verified, and why it matters

The three neuroscience figures have no primary source **on this project's allowlist**. Their
primary literature is journal work — Kety on cerebral metabolic rate, Attwell and Laughlin on
the energy budget for signalling, the anatomical synapse counts — published on hosts nobody
allowlisted. arXiv returns papers *citing* those figures, which are exactly the secondary
summaries AGENTS.md §Phase 6 tells the channel to prefer primary sources over.

Searching for them is instructive in its own right. `human brain energy budget 20 watts
synapses ATP cost signaling` returns, among its first four results on relevance, two
astrophysics papers about dark energy and a CMB polarisation experiment named BRAIN. arXiv is
the wrong corpus for this question, and no amount of query tuning fixes a corpus.

**One of the three is worse than unsourced.** The seed reads:

> brain ~20 W across ~10¹⁴–10¹⁵ synapses at low average firing rates, implying something like
> 10⁻¹⁴ J per synaptic event

The nearest primary figure that *is* on the allowlist — arXiv:1204.3928v1, *Approximate
invariance of metabolic energy per synapse during development in mammalian brains* — gives
"about (7±2)·10³ glucose molecules per second" for a typical synapse in primate cerebral
cortex. That is a **power per synapse**, not an energy per event. The two quantities coincide
only if the average firing rate is about 1 Hz, which the seed asserts ("at low average firing
rates") and does not source.

So the seed is not merely uncited: it may be a category error, dividing a power by a synapse
count and reporting the result as an energy per event. It stays in the kernel at 0.30, and it
is now the claim most worth attacking.

That figure was **not** committed as evidence. It is adjacent, not corroborating, and turning
"here is a related number in different units" into support would be exactly the laundering the
channel exists to prevent.

## What this means for the Charter

`CHARTER.md` denominates the entire question in joules at the wall and sets the brain's ~20 W
as the reference the project is measured against. That figure is now, on the record, the
**least supported claim in the kernel** — a 0.30 hypothesis whose only source is the project's
own founding document.

This does not invalidate the Charter. S4 fixes an energy budget and measures capability inside
it; the budget is a number the operator declares, and the experiment runs whatever the brain
turns out to draw. But any *comparison* to a brain rests on a claim nothing has yet checked,
and the Charter should not be read as having established it.

Two ways forward, neither taken here:

- **Widen the allowlist** to the hosts the primary literature actually lives on, which is a
  deliberate act with its own review — `config/g0rd0n.toml` is the only channel by which a
  reachable host enters the process, and that is the point of it.
- **Retract the brain figure from the Charter's rhetoric** and keep it only as a budget the
  operator sets, so nothing downstream depends on a number nobody sourced.

## Reproducing this

```bash
uv run g0rd0n evidence seed     # commit the five seeds as unverified hypotheses
uv run g0rd0n evidence audit    # resolve the sources and corroborate what they state
uv run g0rd0n vault rebuild     # read the result as notes
```

`audit` is re-runnable. The seeds are idempotent, and a source that already supports a claim is
skipped — so running it twice does not turn two readings of one paper into two papers agreeing.
