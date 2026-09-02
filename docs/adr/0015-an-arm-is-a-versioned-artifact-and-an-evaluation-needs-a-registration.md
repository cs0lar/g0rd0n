# ADR 0015 — An arm is a versioned artifact, and an evaluation needs a registration

- **Status:** Accepted
- **Date:** 2026-09-02
- **Phase:** 8c (The arms and the protocol)

## Context

Phase 8 splits three ways. 8a built the score half — the chartered families, their checkers,
and `cap` over a curve. 8b built the energy half — instruments, calibration, `Joules`, and the
`Result` that pairs a `cap` with the budget it was measured at. Neither ran anything.

8c is what runs. It is the phase where three claims that have so far been enforced by
convention become enforced by types:

- **"No spend without a Wager."** The Ledger has always required a `Reservation`, but nothing
  connected a reservation to a *registered* wager at the point where the money is actually
  spent. ADR 0010 recorded this as the open gap: "nothing yet proves a wager was registered
  before the experiment physically ran — Phase 8's Bench closes that by taking the
  `Registration` as an argument."
- **"Baseline configs are versioned artifacts."** AGENTS.md §Phase 8, one line, and the
  failure it prevents is a control arm that was quietly improved between two comparisons.
- **"An honestly-tuned transformer control arm."** `CHARTER.md` §Question. Protocol step 2
  gives it teeth: tune the control arm *first*, with at least as much energy as the candidate,
  and record both figures in the result.

`CHARTER.md` §Matched-capability protocol has six numbered steps. This module is those steps,
and the decisions below are the places where they are precise about *what* and silent about
*how*.

## Decision

### 1. An arm is a subject, not a Cell — so it commits nothing

`cells/runtime.py` interns a transcript and commits a `plays` edge for every run, because a
cell doing g0rd0n's work is work g0rd0n should have to answer for. An arm answering 120
instances is not that: it is the *subject* of the experiment.

Reusing `runtime.run` would have put 240 transcripts and 240 `plays` edges into the argument
graph per evaluation, which is the experimental subject's output filling the record of what
g0rd0n believes. The Charter asks for the per-instance records in the **result** (step 4), and
`Attempt` holds every `Answered` for exactly that reason. The argument graph gets one
`measures`.

`cells/arm.py` therefore lives in `cells/` — it calls a model, so it is that layer — but
shares no code with the runtime beyond the `Model` seam and `Turn`.

### 2. `attempt` takes a `Reservation`; `evaluate` takes a `Registration`

The chain is now unbroken by construction, with no string in it a caller could have typed:

```
model call  ←  attempt(reservation=…)
            ←  Reservation, minted only by Ledger.reserve
            ←  cortex.wager.reserve(registration=…)
            ←  Registration, minted only by cortex.wager.register
            ←  a wager that passed the falsifiability gate, under a question the kernel holds
```

`evaluate` is the only thing that makes an `Evaluation`, and `settle` is the only thing that
records one. This is ADR 0010's gap closed. What it does **not** prove is that the wall-clock
of registration preceded the wall-clock of the run — an operator with a Python prompt can do
anything — but it does mean there is no path through this code that produces a result without
a registration in hand first.

### 3. A hand-built `Registration` gets you an `Evaluation` and no further

`Registration` is a frozen dataclass and can be constructed. That is deliberate and it is the
same shape as `Reservation`: the type carries the claim, and `cortex.wager.record` re-checks
it against the kernel before committing. So a hand-built registration builds an `Evaluation`,
runs the protocol's refusals, and then fails at `settle` with `NotPreregistered`.

The upside is that most of `tests/test_protocol.py` runs with no `knk` at all, which is the
same trade `cortex/allocator.py` made in 7b and for the same reason.

### 4. A failed model call fails the attempt; it does not score zero

A refused or wrong instance is the arm failing. A dead endpoint is *g0rd0n* failing, and
scoring it against the arm would attribute an infrastructure problem to the system under test
— permanently, in a result. So `attempt` raises, and `evaluate` settles in a `finally`.

Nothing is retried, for the reason `cells/runtime.py` gives: a retry storm is a spending
decision made by nobody.

### 5. The control arm runs first

Protocol step 2 puts the *tuning* first. The same logic carries over to the running: if the
budget runs out midway, the arm that got measured should be the one that would otherwise be
quietly dropped. A `BudgetExhausted` mid-evaluation leaves a control attempt and no
comparison, which is the failure that admits it happened.

One reservation covers both arms, because the wager pre-registered one price for finding this
out. Two reservations would let the second half be re-priced after seeing the first.

### 6. `separated` requires the margin **and** both arms inside the budget

`margin` bootstraps `cap` from the scores, because scores are what a resample can draw. That
leaves a seam: an arm that outscored the control by spending a thousand times the joules
produces a **positive margin** and a `cap` of `None`. Without a budget clause the evaluation
would report a separation while the `Result` for the winning arm reported no capability at all.

Step 5 says "at equal `B`, `P`, and `N`", and `Evaluation.within_budget` is that phrase. The
failure was found by writing the test, not by reading the Charter.

### 7. The resampled `cap` uses the mean alone

`Point.clears` asks for the mean *and* the interval, because a single curve's `cap` must not
move when somebody reruns the same instances. A bootstrap over `cap` measures exactly that
movement, directly — so applying both would count the same uncertainty twice, and it would do
so as a bootstrap inside a bootstrap: four million resamples for a number that does not get
better.

An undefined `cap` counts as zero **only** inside `margin`. A margin needs a number, and
"below every size on this curve" is ordinally below all of them. Everywhere else `None` stays
`None`.

### 8. `W` is applied per instance, and it is honest about what it timed

An instance answered outside `Family.ceiling_seconds` scores zero rather than being allowed to
run on, per §Resource held fixed: "a paradigm that stays inside `B` by taking a year per
instance is not a result about anything anyone can use." The answer is still kept, and
`Attempt.overran` counts them, so a run that failed entirely on the clock is distinguishable
from a run that failed on the task.

For an arm behind an HTTP API that clock includes the network and somebody else's queue. See
the failure modes.

### 9. `solved` means correct, not nearly correct

T3's checker gives partial credit by F1. `J_solved` is joules per *correct answer*, so a 0.8
is not solved and counting it would report an efficiency for work that did not finish.
Partial credit belongs on the curve, where it moves the mean and therefore `cap`.

### 10. No CLI command runs an evaluation

All four `bench` actions read. Running two arms over a pre-registered instance set spends on
240 model calls, and AGENTS.md §Do Not Do Yet names unattended spend above a declared cap.
The first thing to start an evaluation should be a wager somebody registered, through
`cortex.protocol.evaluate`, not a shell command somebody typed. `bench baselines` exists so
the control arm's hash is readable without running anything.

## Failure modes

- **`W` on a hosted arm times the round trip, not the computation.** Network latency, the
  provider's queue, and a retry inside somebody else's load balancer all land inside
  `Family.ceiling_seconds`. This makes `W` a weaker instrument than the Charter's prose
  implies for any arm g0rd0n reaches over HTTP, and it cuts the wrong way: a slow network
  scores the arm as failing. Recorded rather than patched, because the fix is a local arm and
  there is no local arm to write.
- **The margin's seeding is not covered by a test, and cannot be.** Replacing the content-hash
  seed with a bare `random.Random()` leaves the whole suite green. `cap` is an *ordinal*, so
  the resampled difference takes a handful of distinct values and a 2.5% quantile over 2000
  draws lands in the same mass every time; a sweep over sixteen near-threshold curve pairs
  found no configuration where an unseeded RNG changed the endpoints. 8a's
  `the_interval_is_the_same_in_a_second_process` catches the equivalent bug because *its*
  statistic is a continuous mean. The seed is still right — an exactly reproducible margin is
  the point, and the robustness that hides the bug would not survive a smaller `RESAMPLES` or
  a finer size ladder — but it is defended by review rather than by a verdict, and a test
  tuned to be flaky enough to notice would be worse than saying so.
- **A candidate significantly *behind* the control arm reports `inconclusive`.** Step 5 says a
  separation may be claimed when the margin excludes zero, and "anything else is
  `inconclusive`". Read literally that covers a candidate the control arm beat decisively,
  which looks like a refutation and is worded as neither. `verdict` follows the Charter; the
  alternative — mapping a negative margin to `refutes` — would put a stronger claim into the
  argument graph than the protocol licenses. **This is a criticism a superseding Charter could
  quote**, in the same form as the ones that retired `charter-329c9f00e917`.
- **Tuning parity is a declared number, not a measured one.** `tuning_joules` is inside the
  arm's version, so it cannot be edited after a run without changing the arm — but nothing
  checks that the figure is true. It is a commitment, in the same sense a wager's price is one.
- **The wager-names-the-family check is a substring test.** `Evaluation` refuses when the
  family's version does not appear in `wager.task_family`, which is free text. A wager naming
  two families passes for either. Tightening it means a structured field on `Wager`, which
  would change every wager's hash.
- **`Attempt` holds every answer in memory.** 120 instances of T3 at size 8192 is a few
  megabytes and fine; a Charter that adds a family with large instances would need to think
  about it. Not a problem today and not worth solving today.

## What this does not decide

- **Nothing has been run.** There is no API key on this machine, and — per ADR 0014 — no
  primary energy instrument either, so the first real evaluation is still ahead. Everything
  here is exercised against a scripted model, which is the same seam `tests/test_cells.py`
  uses and for the same reason: a test asserting on what a model says is a test of the model.
- **No energy model for a hosted transformer.** `Measurement` takes its `Joules` from the
  operator, so g0rd0n never invents an energy figure. An arm behind an API has its joules in
  somebody else's building, so accounting for it means an analytic estimate with a real
  source — and shipping a placeholder number in `bench/baselines/` would be exactly the
  unsourced claim the Evidence Channel exists to refuse. The config declares what the arm
  *is*; how its joules were accounted belongs to the session that ran it.
- **Protocol step 6, sweeping `B` to recover S3.** "The smallest `B` at which each arm reaches
  `(T, n, θ_T)`" is a reading off several evaluations at different budgets, and the Charter is
  right that it is a corollary rather than a second experiment. It is a loop over `evaluate`
  and nobody has needed it yet.
- **Promotion.** A `measures` edge lands as a `Hypothesis` like everything else the bridge
  writes. Turning a result into something g0rd0n believes is Phase 10's referee and its three
  keys.

## How it is tested

`tests/test_protocol.py`, twenty-five tests. Two need a real `knk` — the round trip that
registers, runs, records and reads the `measures` edge back, and the one that proves a
hand-built registration cannot be settled. The rest run with no kernel, no network, no model
and no meter.

The family under test is a toy, not one of the three chartered ones: these tests are about the
protocol, and a protocol test that has to solve S₅ compositions to shape a curve is a test of
`tasks.py` wearing the wrong name. `tests/test_bench.py` checks the real families against a
second implementation.

`baseline_arm_runs_on_every_evaluation` lands here, which completes Phase 8's four minimum
tests: `energy_measurement_reports_an_error_bar`,
`measured_and_estimated_energy_are_never_compared_without_a_flag` and
`result_carries_its_config_hash_and_instrument` arrived in 8b.

Twenty-three deliberate breaks were applied one at a time — an arm's version ignoring its
tuning record, an overrunning instance keeping its score, the control arm not having to be a
transformer, the two arms answering different instance sets, a candidate tuned harder than the
control, a separation claimed on two `cap` numbers that differ, an overspending arm winning
one, the mixed flag hard-wired off, the config hashes dropped from the finding, the candidate
running first, the reservation not settled on failure, and the shipped control arm not being
told the answer format. **Twenty-two of twenty-three turned a test red.** The survivor is the
margin's seeding, and it is the second failure mode above: it was investigated, proved
unobservable from the function's output, and written down rather than papered over.
