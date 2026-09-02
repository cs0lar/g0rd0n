# ADR 0014 — A joule figure carries its basis, and a `cap` carries its budget

- **Status:** Accepted
- **Date:** 2026-09-02
- **Phase:** 8b (The meter and what it licenses)

## Context

`CHARTER.md` §Energy instrument is the most operational section of the Charter. It names a
primary instrument, demotes the one every machine already has, fixes a calibration procedure
down to its duration, and ends with a refusal:

> A session with no calibration record produces no energy result — not a result with a wide
> bar, a refusal.

AGENTS.md §Phase 8 adds the other half:

> An analytic estimate is labelled as such in the result assertion and can never be compared
> directly against a measured number without the comparison being flagged.

Both sentences describe things that are easy to write down and hard to keep true, because
both are lost by *omission* rather than by error. Nobody deliberately publishes an estimate as
a measurement; a number gets passed to a function that takes a `float`, and three calls later
the label is gone. Nobody deliberately quotes a `cap` with no budget beside it; a report
prints the headline and runs out of room.

So the decisions below are all one decision applied in four places: **make the thing that
would be omitted structurally inseparable from the thing that would be quoted.**

Phase 8 is split three ways, and this is the middle one. 8a built the score half — the
families, the checkers, and `cap` over a curve — and said in its own docstring that quoting
it alone would be quoting a capability with no budget beside it. **8b is the energy half and
the type that pairs them.** 8c is the arms and the run loop: the honestly-tuned transformer
control arm, the per-instance `W` ceiling, and the `measures` commit that takes a
`Registration` and closes ADR 0010's gap. The split falls here because everything in 8b is a
pure function of values — no arm, no model, no network, no kernel, and, as it turns out, no
meter either.

## The machine this was written on cannot measure a joule

Worth stating plainly, because it is the reason several of these refusals are load-bearing
today rather than one day:

```
$ uv run g0rd0n bench meters
rapl:package-0       secondary  unreadable: [Errno 13] Permission denied .../energy_uj
rapl:core            secondary  unreadable: [Errno 13] Permission denied .../energy_uj
wall-plug meter      primary     none configured on this machine
```

There is no wall-plug meter, and RAPL's `energy_uj` has been root-only since CVE-2020-8694.
The Charter admits counters "alongside a wall-plug meter and never instead of one", so on this
machine every energy figure the bench can produce is an analytic estimate, labelled
`estimated`, and every comparison it appears in is flagged as mixed. That is not a gap to work
around. It is the correct answer, and `bench meters` exists so that it costs one command to
find out rather than one run.

## Decision

### 1. `Joules` carries its error bar and its basis, and there is no other way to hold energy

There are two routes to a `Joules`: a `Session`, which has a `Calibration` field with no
default, and `estimated`, which refuses anything but an analytic instrument and refuses a zero
uncertainty. Every one of them carries an `Instrument`, and `Basis` is derived from the
instrument's `Role` through a table rather than set by a caller.

The alternative — passing joules as floats and carrying the label alongside — fails the same
way every time. The label is an argument, arguments get defaulted, and a default for "was this
measured?" is a lie that is true most of the time.

### 2. No calibration, no result — and the refusal has a function to happen in

The type already makes an uncalibrated measurement unconstructible. `meter.session` exists
anyway, taking `Calibration | None`, because that is the shape the failure actually arrives
in: an operator holding a run's numbers and no meter check. `None` gets a refusal with the
Charter's sentence in it.

A `Calibration` shorter than `CALIBRATION_SECONDS = 60` is refused for the same reason a
missing one is. A meter read against a known load for two seconds has measured its own
transient.

### 3. The error bar floors at the meter's least count

The Charter says the deviation from the known load is the session's error bar. Taken
literally, a meter that agrees with its calibration load to the digit it displays reports
`0 ± 0 J` — a claim of a perfect instrument, arrived at by the meter being *good*.

`Calibration.relative_error` is `max(deviation, resolution_watts) / nominal_watts`. The
smallest error a meter may claim is the smallest difference it could have shown.

### 4. A relative error passes through an idle subtraction unchanged

A calibration deviation is a **scale** error: the meter reads some percent high or low. A
scale error survives `load − idle` as the same percent, so `Joules.minus` keeps
`relative_error` and does not combine anything.

A ratio across two *different* instruments is the opposite case — two calibrations are
independent — so `Comparison.relative_error` adds them in quadrature. Both choices are stated
where they are made, because getting either backwards changes every bar the bench reports and
neither would look wrong in a table.

### 5. `minus` refuses two instruments; `compare` is where two instruments meet

`Joules.minus` raises on a mismatched instrument. That is what confines the scale-error
assumption in (4) to the case it holds for, and it is also what makes the mixed-comparison
flag unloseable: there is no arithmetic path from a measurement and an estimate to a bare
number. The only expression that takes two instruments is `compare`, and every `Comparison`
derives `mixed` from the two bases and prints it in `__str__`.

Flagged, not refused. The Charter says a candidate that cannot be run here "is evaluated by
analytic estimate under the same protocol, and every comparison it appears in is flagged as
mixed" — so a mixed comparison is admissible and the label is what makes it honest. Refusing
it would make the only available evidence about neuromorphic and analog substrates
unreportable, which is a worse failure than a flagged comparison.

### 6. A secondary instrument cannot carry a run

`expenditure` refuses a primary reading from a `SECONDARY` instrument. Counters are the
instrument a machine always has and a wall meter is the one it usually does not, so the path
of least resistance for any bench is to quote RAPL and call it the run's energy — which
reports the joules of whichever part of the machine was easiest to instrument, and misses
fans, PSU losses, the host and the network. That is precisely the territory a comparison
against 20 W is won or lost in.

### 7. Two denominators, and neither is allowed to do the other's job

`per_attempted` divides by instances *attempted*, so a system cannot come in under `B` by
declining every instance it expects to fail. `j_solved` divides by instances *solved*, so a
system that answers fast and wrong is charged for the answers it got wrong. `k = 0` gives
`None` and not zero: a run that solved nothing reports its joules and has no efficiency.

They are separate properties with the reason on each because collapsing them is the single
cheapest way to make a bench flatter an arm, and the collapsed version passes every test that
only checks units.

### 8. `Result` pairs `cap` with its budget, and a run outside its budget has no `cap`

> Raw accuracy alone is not a result under this Charter, and neither is `cap` without the
> budget it was measured at.

`Result` has `curve`, `budget`, `spent`, `config_hash` and `family`, all required, and
`render` prints every one of them. There is no field to leave out and no short form.

`Result.cap` returns `None` when the run did not stay inside `B` and `P`. A size *clears* when
the scores clear **and** the instances were answered inside the budget, so an arm that beat
the threshold while overspending has not cleared anything — it has shown what it could do with
a budget nobody gave it. `None` rather than "cap 16, with a caveat", because the caveat is the
part that gets dropped when the number is quoted somewhere else.

The budget test compares point estimates, not intervals. Letting a wide error bar argue an arm
back inside its budget would turn a worse meter into a licence to overspend.

### 9. `W` is not a field, because it is already inside the family's version

The Charter's protocol pre-registers `B`, `P`, `N` **and** `W`. `Budget` carries the first
three. `W` is `Family.ceiling_seconds`, which `Family.spec` already hashes, so a wager that
names a family version has pre-registered its wall-clock ceiling. A second copy in `Budget`
would be a second thing to disagree with (ADR 0002). Enforcing it per instance needs a run
loop and is 8c's.

## Failure modes

- **A scale error says nothing about a meter's noise.** (4) is right about the systematic and
  silent about the random. A load barely above idle gets a small difference with a
  proportionally tiny bar, which understates. The Charter names only the calibration deviation
  as the session's error bar, so widening this is a change to the Charter rather than to this
  module — recorded here as a criticism a superseding one could quote.
- **`DRIFT = 0.10` is chosen, not derived.** Unlike `MINIMUM = 40`, there is no arithmetic
  behind ten percent. It is a threshold on how far the idle baseline may move between the
  before and after readings, and it is a guess at where "the same ambient conditions" stops
  being true.
- **The idle baseline is a mean of two points.** The Charter asks for both and this subtracts
  their average times the duration, which assumes the drift between them was linear. On a run
  where the machine warmed monotonically that is roughly right and on a run with a thermal
  event in the middle it is not.
- **A `Joules` can be constructed directly.** As with `Reservation` and `Registration`, the
  dataclass is reachable and the discipline is that `Session` and `estimated` are the only
  callers. Unlike those two, there is no downstream lookup that could catch a hand-built one,
  because there is no kernel involved — the type is the whole enforcement.
- **`Instrument.covers` is prose.** Nothing checks that a wall meter's declared scope is true.
  An instrument that claims the whole machine and is plugged into one PSU rail would pass
  every test here. The mitigation is that `covers` is printed in every `render`, which puts
  the claim in front of whoever reads the result.
- **The wall/counter ratio is computed and not judged.** `ratios` reports `wall / counters`
  per secondary because the Charter asks for it to be stated. Nothing refuses a ratio below 1,
  which would mean the counters saw more than the plug did and therefore that one of them is
  wrong.

## What this does not decide

- **No arm exists yet.** There is still no transformer control arm, no tuning, and no run
  loop, so `baseline_arm_runs_on_every_evaluation` is 8c's. So is protocol step 2 — tuning the
  control arm first and spending at least as much on it as on the candidate — which is a rule
  about two runs and cannot be checked inside one.
- **Nothing is committed.** `instruments/` returns results and commits nothing (AGENTS.md §6).
  The `measures` edge carrying the full config hash is 8c's, and it is where ADR 0010's open
  gap closes: the run loop takes a `Registration` as an argument, so a result cannot physically
  be produced before the wager that pre-registered it.
- **`config_hash` is a string this module refuses to be empty.** What goes into it is the
  arm's business, and the arm is 8c's.
- **No wall-meter driver.** There is no meter on this machine to write one against, and a
  driver for a device nobody can test is speculative optimisation of the sort AGENTS.md §Do
  Not Do Yet rules out before the Bench exists. `Instrument` is the seam it will arrive
  through; `bench meters` is where its absence is reported today.
- **Protocol step 5's separation claim.** "The candidate's `cap` exceeds the control arm's by
  a margin whose 95% confidence interval excludes zero" is a statement about two curves and
  needs both arms. `Comparison.separated` does the same job for two energy figures and is not
  the same test.

## How it is tested

`tests/test_meter.py`, twenty-two tests, none of which needs `knk`, a network, a model, or a
meter. Two build a fake `sysfs` under `tmp_path`; one enumerates the real
`/sys/class/powercap` and asserts only that it does not raise, because the answer differs per
machine and the machine that cannot read it is the case the module is for.

Three of Phase 8's four minimum tests land here under their AGENTS.md names:
`energy_measurement_reports_an_error_bar`,
`measured_and_estimated_energy_are_never_compared_without_a_flag`, and
`result_carries_its_config_hash_and_instrument`.

Twenty deliberate breaks were applied to `meter.py` and `bench.py` one at a time — a joule
figure allowed to claim a perfect instrument, a missing calibration invented rather than
refused, the mixed flag hard-coded to `False`, the flag dropped from `__str__`, counters
allowed to carry a run, the two denominators swapped, `cap` reported for a run that
overspent, the budget line dropped from `render`, "no preparation phase" rendered as zero
joules — and each one turned a test red. Twenty of twenty on the first pass.
