# Charter definitions

The terms [`CHARTER.md`](../../CHARTER.md) uses, and one worked example each. A definition
that cannot be applied to a worked example is not yet a definition, and `g0rd0n` refuses to
load this file if any term here lacks one.

This file has a version — the hash of its bytes — and the Charter names it. Editing a
definition therefore changes the Charter's version and costs it a fresh signature. That is
deliberate: a question whose terms can be redefined underneath it is a question that can be
changed without being superseded.

**The numbers in the worked examples are illustrative arithmetic, not measurements.** They
show how a definition is applied; none of them is a claim about the world, and none is
committed to the kernel. Measured numbers arrive in Phase 8 with an instrument and an error
bar attached.

## Task family

A triple `(generate, size, check)`: an instance generator taking a size parameter and a
random seed, a size parameter that orders instances by difficulty in a way the family
declares, and a checker. A family is chartered only if all three are machine-executable and
versioned by content hash, so that "the same family" is a checkable statement rather than a
name two people agree on.

A family is *not* a dataset. A fixed dataset has a largest instance, and a separation claim
that cannot be pushed to larger instances cannot be attacked by pushing it there.

**Worked example:** T1, state tracking under composition. `generate(n, seed)` draws `n`
elements of the symmetric group S₅ uniformly at random and emits them as a sequence of
transpositions; `size` is `n`; `check(instance, answer)` recomposes the sequence and returns
1 if `answer` is the resulting permutation in one-line notation and 0 otherwise. At `n = 3`
an instance might be `(1 2)(3 4)(1 5)` with the single correct answer `5 1 3 4 2`.

## Checker

A total, deterministic function from `(instance, answer)` to a score in `[0, 1]`, executable
without a network and without a model, and versioned by the hash of its source. Totality
matters: a checker that raises on a malformed answer is a checker that scores some wrong
answers as "error" rather than as wrong, and the difference between those two categories is
where a generous evaluation hides.

A checker that calls a language model is not a checker. It is another system under
evaluation, and it makes the capability metric depend on the thing being measured.

**Worked example:** T1's checker takes the instance's transposition list and the answer
string, parses the answer as a permutation of `{1..5}`, and returns 1 on an exact match. An
answer of `"I think it is 5 1 3 4 2"` scores 0, because the family's contract says the answer
is a permutation in one-line notation and nothing else. A parse failure scores 0, not an
error.

## Inference budget (B)

The energy, in joules measured at the wall, that a system may spend answering one instance,
averaged over the instances it attempts in a measured run. It covers everything between the
instance arriving and the answer being emitted: prompt processing, every serial step of any
chain of thought, sampling, decoding, and any tool call the system makes.

B is per instance *attempted*, not per instance solved. A system may not buy a better score
by declining the instances it expects to get wrong, because the budget test and the
efficiency report use different denominators on purpose (see *Joules per solved instance*).

**Worked example:** a run answers 500 instances and draws 68.4 kJ at the wall above idle.
Its measured per-instance figure is 68 400 / 500 = 136.8 J. At a chartered budget of
`B = 150 J` the run is inside budget; at `B = 100 J` it is not, and its capability result is
void rather than merely worse — a measurement taken outside the budget is a measurement of a
different experiment.

## Preparation budget (P) and deployment population (N)

`P` is every joule spent before the first instance is answered: pre-training, fine-tuning,
architecture search, distillation, calibration, and any hyperparameter sweep whose outcome
the system uses. `N` is the declared number of instances the system is claimed to be
deployed over, and `P/N` is the amortised preparation cost that every claim reports beside
`B`.

Both are declared before the run, and `N` is part of the claim rather than chosen afterwards
to make a ratio look good. Splitting the two is what stops the brain comparison from being an
accounting choice: a brain has no separate training phase, so a paradigm claiming a brain-like
profile must show a preparation budget that does not dominate.

**Worked example:** a control arm is fine-tuned for 6 GPU-hours on a 300 W accelerator, so
`P ≈ 6 × 3600 × 300 = 6.48 MJ`. Declared over `N = 10⁶` instances, `P/N = 6.48 J`, small
beside a `B` of 136.8 J. Declared over `N = 10³`, `P/N = 6480 J`, forty-seven times the
inference cost — the same system, the same measurements, and a different result, which is why
`N` is pre-registered and printed on every claim.

## Idle-subtracted energy

`E = E_load − P_idle × t`, where `E_load` is the meter's integral over a run of duration `t`
and `P_idle` is the machine's mean power over an idle interval measured immediately before
and after the run under the same ambient conditions. Both `E_load` and `P_idle` are reported
alongside `E`, always, so a reader can undo the subtraction.

Subtraction is the right convention for comparing *paradigms* — the fans, the PSU losses and
the host's own draw are properties of the bench, not of the candidate. It is the wrong
convention for comparing against a brain, which does not get to subtract its own baseline,
so the un-subtracted total is what any brain comparison uses.

**Worked example:** a 400 s run integrates to `E_load = 92 kJ`; the idle baseline measured
either side averages `P_idle = 59 W`, so the idle share is `59 × 400 = 23.6 kJ` and
`E = 68.4 kJ`. The result reports all four numbers. A claim that quoted only 68.4 kJ against
a brain's 20 W would be comparing a subtracted figure with an unsubtracted one.

## Joules per solved instance

`J_solved = E / k`, where `E` is the idle-subtracted energy of the measured run and `k` is
the number of instances the checker scored as correct. Reported with `E`, `E_load`,
`P_idle × t`, `k`, the number attempted, and the instrument's error bar.

The denominator is *solved*, not attempted, so a system that answers quickly and wrongly is
charged for the answers it got wrong. A run with `k = 0` has no `J_solved`: it is reported as
"0 solved at `E` joules", never as infinity and never as a blank.

**Worked example:** the 500-instance, 68.4 kJ run above solves 310. `J_solved = 68 400 / 310
= 220.6 J`, against a budget-test figure of 136.8 J per attempt. A second system inside the
same budget that solves 460 reports `J_solved = 148.7 J`. Both are inside `B = 150 J`; they
are not equally good, and the per-attempt figure alone would not have said so.

## Capability at a budget (cap)

`cap(system, T, B, P, N)` is the largest size `n` at which the system's mean checker score
over the family's pre-registered instance set is at least the family's threshold `θ_T`, with
the lower end of a 95% bootstrap confidence interval also at least `θ_T`, every instance
answered inside `B` and inside the family's wall-clock ceiling `W`, and the system prepared
inside `P` for the declared `N`.

An ordinal, not an accuracy. Accuracy on a set of mixed sizes reports a system that solves
everything up to `n = 5` and a system that solves everything up to `n = 50` as the same
number if the mixture is chosen right, and the difference between those two systems is the
entire question.

**Worked example:** at `θ_T = 0.9`, a system scores 1.00 at `n = 8`, 0.97 at `n = 12`, 0.91
at `n = 16` with a 95% CI of [0.86, 0.95], and 0.62 at `n = 20`. Its `cap` is 12, not 16: the
point estimate at 16 clears the threshold but the interval does not, and a `cap` that moves
when someone reruns the same instances is not measuring the system.

## Control arm

A transformer baseline, specified as a versioned config — weights, decoding parameters,
prompt, and any scaffolding — run on the identical instance set, in the same session, on the
same machine, under the same meter, inside the same `B`, `P`, and `N`.

The arm is mandatory and is tuned *first*, with at least as much energy spent tuning it as is
spent tuning the candidate, and both figures recorded. A separation measured against a
baseline nobody tried to make good is not a separation, and this is the only version of that
rule that is auditable rather than asserted.

**Worked example:** a candidate is tuned with a 40-configuration sweep costing 900 kJ. The
control arm must then be given a sweep of at least 900 kJ — say 55 decoding and prompt
configurations at 16 kJ each, 880 kJ, plus one more at 24 kJ to clear the bar — and the
result records `tuning_energy: candidate 900 kJ, control 904 kJ`. Had the control arm been
given a single default configuration, the run would produce no separation claim at all.

## Separation at a budget

A candidate `P*` separates from the control arm on family `T` at `(B, P, N)` when
`cap(P*, T, B, P, N) > cap(control, T, B, P, N)` and the 95% confidence interval on the
difference excludes zero, both arms having been measured under the matched-capability
protocol. Anything else is `inconclusive`, which is a verdict and is recorded as one.

A separation is always *at* a budget. "P* separates at every B" is the strong claim, it is
not established by any single run, and the cheapest way to attack it is to raise `B` until
the control arm catches up.

**Worked example:** at `B = 150 J`, `P = 6.48 MJ`, `N = 10⁶` on T1, the candidate reaches
`cap = 34` and the control arm `cap = 12`, difference 22 with a 95% CI of [15, 27]. That is a
separation at that budget. Rerun at `B = 15 kJ` — a hundred times the chain-of-thought — the
control arm reaches `cap = 31` and the candidate `cap = 36`, difference 5 with a CI of
[−2, 11]: inconclusive at that budget, and the pair of results is more informative than
either.

## Analytic estimate

An energy figure produced by a model of a substrate rather than by a meter attached to one,
used for hardware that cannot be run on this bench: neuromorphic silicon, analog in-memory
arrays, and anything else the project does not physically have. It carries its model, the
model's assumptions, its source, and the label `estimated`, and it is never compared with a
measured figure unless the comparison is flagged as mixed (AGENTS.md §Phase 8).

An estimate is evidence about a substrate. It is never evidence that a substrate *was*
measured, and the two are separated at the type level in the result assertion rather than by
a footnote.

**Worked example:** a spiking implementation of T3 is estimated at 8.1 μJ per instance from a
published energy-per-synaptic-event figure, a spike count from a simulator, and a stated
assumption that the count is substrate-independent. The result records
`energy: 8.1 µJ, instrument: analytic, model: <hash>, assumes: spike count is
substrate-independent`, and a table putting it beside the control arm's wall-measured 136.8 J
is flagged as mixed on the face of the table, not in a caption.
