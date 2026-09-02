# Charter

## Question

Fix a per-instance inference energy budget `B` and a preparation energy budget `P` amortised
over a declared deployment population `N`, all measured in joules at the wall. For a
chartered task family `T` with a machine-checkable checker: **is there a computable paradigm
that, prepared within `P` and answering within `B`, attains a capability on `T` that no
honestly-tuned transformer control arm attains within the same `P`, `B`, and `N` — and does
its advantage survive as `B` is raised?**

The seed framing asked for a paradigm "provably more powerful than transformers". That is not
made well-posed by finding a better word for *powerful*. Two Turing-complete systems cannot be
separated on what they can compute, and every candidate worth the name is Turing-complete, so
the seed's own §The Turing trap is right that the question must name a resource and hold it
fixed. This Charter names energy, and the reason is one sentence: **the Turing trap exists
only because nobody was charging for the tape.** An unbounded chain of thought buys depth by
spending serial steps, and a serial step costs joules. Price the steps and the trap closes.

The second half of the seed — "energy profiles approximating or improving on a brain's, ~20 W
continuous" — is not a separate question. It is the budget. A watt figure with no task and no
capability threshold beside it is satisfied by any system that does nothing at 20 W.

## Separation shape

**S4, a defended fourth: capability at a matched energy budget.** Hold the joules fixed and
measure the capability, rather than holding the capability fixed and measuring the joules.

Why not S1 (expressivity at fixed resource): S1 separations are statements about circuit
classes, and the ones that would bite here are contingent on open problems (`TC⁰ ≠ NC¹` and
friends). An S1 result is admissible as evidence and is recorded with its contingent
assumptions attached, permanently (Phase 9). It is not the thing that settles a wager, because
a question that can only be settled by resolving an open problem in complexity theory is a
question this instrument cannot spend against.

Why not S2 (learnability) as a separate shape: an S2 claim is a claim about the preparation
budget, and S4 already holds that fixed as `P`. A paradigm that can represent something nobody
can train it to represent fails S4 automatically, because its preparation budget is unbounded.
S2 is therefore inside S4 rather than beside it.

Why S4 rather than S3 (joules at matched capability), which the seed offers: S3 requires the
candidate to first reach the control arm's capability, and every candidate in the seed's own
portfolio is behind. A charter built on S3 cannot take its first measurement. S4 can be
measured on day one, at any budget, on any candidate, and gets more informative as the budget
grows.

Nothing is lost by the swap. Sweeping `B` recovers S3 exactly: the smallest `B` at which each
arm reaches `(T, n, θ_T)` is the matched-capability energy figure, read off a curve this
protocol already produces. S3 is a corollary of a swept S4, not a rival to it.

## Resource held fixed

**Energy, in joules measured at the wall, in two separately declared budgets.**

`B`, the inference budget: the energy attributable to answering one instance, averaged over
instances attempted, covering every serial step between the instance arriving and the answer
being emitted — prompt processing, chain-of-thought tokens, sampling, decoding, and tool
calls. Idle-subtracted, with the un-subtracted total, the idle baseline, and the duration
reported alongside.

`P`, the preparation budget, with `N`, the deployment population: every joule spent before the
first instance is answered, amortised as `P/N` and reported beside `B` with `N` stated. Split
from `B` rather than folded into it because a transformer's inference is cheap and its
training is not, while a brain has no separate training phase; without the split, any
comparison to 20 W is a choice of accounting wearing the costume of a result.

Wall-clock is a secondary fixed resource. Each family declares a ceiling `W` per instance; a
system that exceeds it is scored as failing that instance rather than being allowed to run on,
because a paradigm that stays inside `B` by taking a year per instance is not a result about
anything anyone can use.

Why energy and not parameters, FLOPs, depth, or serial steps: each of those is a proxy that a
different substrate games in a different currency, and none is commensurable across them — a
spike, a matmul, and an analog settling event have no common unit except joules. Joules are
the only resource a brain and an accelerator both spend, and the task statement is already
denominated in watts.

This is `target_energy` throughout, never `operating_cost`. What `g0rd0n` spends to run these
measurements is priced by the Ledger, against a Wager, and never appears in `B`, `P`, or any
result.

## Task families

Three families are chartered, each an instance generator, a size parameter, and a
machine-executable checker, all versioned by content hash. Each ships a seed set that is
pre-registered with the wager that uses it.

`T1` — state tracking under composition. Compose `n` elements of S₅ and report the resulting
permutation. Size is `n`; the checker is exact match. Chartered because the control arm's
believed limitation is depth: fixed-depth, log-precision transformers are thought to sit
inside uniform `TC⁰` (a seed claim, unverified — Phase 6 must corroborate or retract it), and
chain of thought buys the depth back by spending serial steps. Under this Charter those steps
have a price, so the family turns the seed's own complexity anchor into a bill.

`T2` — online adaptation with no training phase. A stream whose generating distribution
changes at unannounced points; the system must reach a declared accuracy on the post-change
distribution within a declared number of instances, using only the inference budget. Size is
the number of distinct regimes; the checker scores each instance and reports recovery time
after each change point. Chartered because the brain's 20 W includes its learning, and a
paradigm claiming a brain-like profile must not be allowed to hide its adaptation in `P`.

`T3` — sparse event streams. Detect a rare, temporally-defined pattern in a long and mostly
empty stream. Size is stream length at fixed event density; the checker scores reported event
indices by F1 against ground truth. Chartered because this is where event-driven and analog
substrates should show their largest advantage, so it is the cheapest place to find out that
they do not.

Families are added by superseding this Charter, never by appending to a list at run time. A
result on a family nobody chartered is a result nobody pre-registered.

## Capability metric

A size `n` *clears* when the system's mean checker score over the family's pre-registered
instance set is at least the family's threshold `θ_T`, the lower bound of a 95% bootstrap
confidence interval is also at or above `θ_T`, every instance was answered inside `B` and
inside `W`, and the system was prepared inside `P` for the declared `N`. Thresholds:
`θ_T = 0.9` for `T1` and `T3`, `0.8` for `T2`.

`cap(system, T, B, P, N)`: the largest measured instance size `n` such that `n` and every
measured size below it clears. Undefined, not zero, when the smallest measured size does not
clear. The prefix is what makes `cap` an ordinal rather than a maximum: capability on these
families falls away as size grows, so a size that clears above one that failed is evidence
about the instance set rather than about the system, and reporting it as the capability is
the reading that flatters.

Reported as a curve — score against size — never as a single accuracy. A system that solves
everything to `n = 5` and one that solves everything to `n = 50` report the same accuracy on
a mixed set if the mixture is chosen right, and the difference between them is the entire
question.

Raw accuracy alone is not a result under this Charter, and neither is `cap` without the
budget it was measured at.

## Energy metric

`J_solved = E / k`: idle-subtracted run energy over the number of instances the checker scored
correct. Reported with `E_load`, the idle baseline and duration whose product was subtracted,
`k`, the number attempted, and the instrument's error bar for that session.

The budget test and the efficiency report use different denominators, deliberately. The budget
test is per instance *attempted* — `E / attempted ≤ B` — so a system cannot buy its way inside
the budget by declining the instances it expects to fail. The efficiency report is per
instance *solved*, so a system that answers fast and wrong is charged for the answers it got
wrong. A run with `k = 0` reports "0 solved at `E` joules" and has no `J_solved`.

`J_solved` replaces the seed's "joules per unit of task-relevant information", which named no
instrument. Task-relevant information is the quantity we would rather have; joules per solved
instance is the one a meter can read, and a metric that cannot be read is a hope.

## Energy instrument

Primary: a **wall-plug power meter sampling the whole machine at 1 Hz or faster**, logged
across the entire run, with the idle baseline measured immediately before and immediately
after under the same ambient conditions and reported.

Secondary, always reported alongside and never alone: on-die counters — RAPL for CPU package
and DRAM, NVML for the accelerator — with the ratio `wall / counters` stated for the run.
Counters are secondary because they miss DRAM on some parts, and miss fans, PSU losses, the
host, and the network entirely, which is precisely where a comparison against 20 W is won or
lost.

Calibration: before each measurement session the meter reads a known resistive load for 60
seconds, and the deviation from its nominal draw is the stated error bar for that session. A
session with no calibration record produces no energy result — not a result with a wide bar, a
refusal.

Substrates that cannot be run on this bench produce analytic estimates only, labelled
`estimated` in the result assertion, carrying their model, its assumptions, and its source. An
estimate is never compared with a measurement unless the comparison is flagged as mixed on the
face of the comparison (Phase 8).

## Matched-capability protocol

1. Pre-register, before anything runs (Phase 7): family, size, `B`, `P`, `N`, `W`, the
   instance seed set, the checker version, the control arm's full config, and the
   kill-criterion.
2. Tune the control arm **first**, spending at least as much energy on it as will be spent
   tuning the candidate, and record both figures in the result. A separation measured against
   a baseline nobody tried to make good is not a separation.
3. Run both arms on the identical instance set, in the same session, on the same machine
   where both can run, with the meter across both.
4. Report `cap` and `J_solved` for both arms with confidence intervals, plus the per-instance
   records, the config hashes, and the instrument's calibration.
5. Claim a separation only when the candidate's `cap` exceeds the control arm's by a margin
   whose 95% confidence interval excludes zero, at equal `B`, `P`, and `N`. Anything else is
   `inconclusive`, which is a verdict and is recorded as one.
6. Recover matched capability, when it is wanted, by sweeping `B`: the smallest `B` at which
   each arm reaches `(T, n, θ_T)`. That is the S3 number, and it is a reading off this
   protocol rather than a second experiment.

A candidate that cannot be run on this bench at all is evaluated by analytic estimate under
the same protocol, and every comparison it appears in is flagged as mixed.

## Definitions

fb20f37ee47f

## Supersedes

charter-329c9f00e917

## Criticisms

- Its definitions file gave the wrong answer for its own worked example of a task family:
  `(1 2)(3 4)(1 5)` was said to compose to `5 1 3 4 2`, which is the composition with `(3 4)`
  having had no effect. The correct answer is `5 1 4 3 2`. A charter whose one worked example
  of what a task family *is* does not compute is a charter whose central artifact nobody
  checked, and it was found by implementing the family rather than by reading the file.
- The same worked example left the composition convention unstated — "recomposes the
  sequence" does not distinguish exchanging positions from exchanging values, or left-to-right
  from right-to-left, and the four readings give three different answers. That ambiguity is
  why the arithmetic error survived: there was no stated rule for the example to be checked
  against, so an implementer had to guess and could not have known they were guessing.
- Its §Task family definition said `generate` "draws `n` elements of the symmetric group S₅
  and emits them as a sequence of transpositions", which describes neither the example beside
  it nor any generator that yields `n` transpositions — decomposing `n` group elements gives
  a sequence whose length nobody controls, so `size` would not have ordered instances by the
  quantity it claimed to.
- Its `cap` was "the largest size `n` at which" the thresholds are met, which reports a size
  that clears standing above a size that failed. On families where capability falls away as
  size grows, such a point is evidence about the instance set rather than about the system,
  and taking the maximum is the reading that flatters. `cap` is now the largest size such
  that it and every measured size below it clear.

## Signed-off-by


Cristiano Solarino <cs0lar>, 2026-09-02, charter-8fb7f2095506
