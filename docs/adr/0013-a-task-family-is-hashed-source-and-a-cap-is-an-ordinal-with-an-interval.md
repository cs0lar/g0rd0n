# ADR 0013 — A task family is hashed source, and a cap is an ordinal with an interval

- **Status:** Accepted
- **Date:** 2026-09-01
- **Phase:** 8a (The task suite and the capability metric)

## Context

AGENTS.md §Phase 8 opens with a warning rather than a requirement:

> This is the phase most likely to be over-built. Keep it small enough that one person can
> verify it is not lying.

The Bench is the empirical arbiter — the thing that decides which paradigm wins — and it is
the one component whose output nobody else can check by inspection. A wrong number from the
ledger shows up as a total that does not reconcile. A wrong number from the bench shows up as
a research result.

`CHARTER.md` and `docs/charter/definitions.md` already fix what a family, a checker, and a
`cap` are, in more detail than most of the Charter. This phase implements those definitions,
and the decisions below are the places where the definitions are precise about *what* and
silent about *how*.

Phase 8 is split. **8a is this: the questions and what a score means.** 8b is the energy
instrument, the arms, and the matched-capability protocol that commits `measures`. The split
falls here because everything in 8a runs on a laptop with no meter, no model, no network and
no `knk` — which is exactly the half a reviewer can check unaided.

## Decision

### 1. A family's version covers its two functions *and* the whole file

definitions.md §Checker asks for a checker "versioned by the hash of its source". Both obvious
readings are wrong, and the first draft of this module shipped one of them.

Hashing the two `def`s alone leaves out everything they *call*: `t3_check` delegates to
`_t3_occurrences`, and `REACH` is a module constant. Rewrite the helper and the version does
not move — a checker that changed without saying so.

Hashing the file alone leaves out which callables a `Family` value actually names. Two
`Family` values can point at different functions while the file is byte-identical. The first
version of `Family.spec` did precisely this and versioned a family with a stub checker
identically to the real one; `a_task_familys_version_covers_the_source_of_its_checker` caught
it on its first run.

So the spec carries both: each function's module-qualified name and `inspect.getsource`, plus
the whole module. The cost is that editing T3 re-versions T1 and T2, which is conservative in
the only direction that is safe — it can refuse a comparison that was actually fine, and it
cannot accept one that was not.

### 2. An instance set is versioned by its instances, never by its recipe

`InstanceSet.version` hashes the rendered instances, not `(sizes, count, seed)`.

The recipe is the tempting choice — it is shorter and it is what a wager would naturally
pre-register. It is also stable across a generator rewrite, and a generator rewrite is exactly
the case where two runs quoting "seed 11" saw different questions. `random.Random`'s output is
not a documented contract across Python versions either, so a set identified by its seed is a
set identified by an implementation detail of the standard library.

Protocol step 3 asks both arms to run on "the identical instance set". Hashing the instances
is what makes that sentence checkable.

### 3. A curve refuses a single size

`CHARTER.md` §Capability metric:

> Reported as a curve — score against size — never as a single accuracy. A system that solves
> everything to `n = 5` and one that solves everything to `n = 50` report the same accuracy on
> a mixed set if the mixture is chosen right, and the difference between them is the entire
> question.

The refusal lives in `curve()` rather than in a reporting layer because by the time a number
reaches a report it has lost the shape it came from. One size is an accuracy wearing a curve's
name, and there is no later point at which anyone can tell.

### 4. Forty instances per size, derived rather than chosen

A 95% percentile interval puts 2.5% in each tail. Below `1 / 0.025 = 40` observations that
tail is less than one instance wide, so the interval's endpoint stops being a quantile and
becomes the most extreme thing that happened. `MINIMUM = 40` is that arithmetic and not a
taste.

It has a price, and the price is the point: a capability claim now costs forty instances per
size per arm. A `cap` certified from five instances is a `cap` certified by luck, and the
cheapest way to stop reporting those is to make them impossible to construct.

### 5. `cap` needs the interval to clear, not just the mean

definitions.md §Capability at a budget asks for both, and its worked example turns on the
difference: a system scoring 0.91 at `n = 16` with a 95% interval of [0.86, 0.95] has a `cap`
of 12, not 16. A `cap` that took the point estimate alone would move when somebody reran the
same instances, and a capability that moves under a rerun is not measuring the system.

The bootstrap is seeded from a content hash of the scores themselves. Not a clock, not a
global, and not `hash()` — Python randomises string hashing per process, so a `hash()`-derived
seed would be reproducible inside one interpreter and different in the next.
`the_interval_is_the_same_in_a_second_process` re-runs it under three `PYTHONHASHSEED`s, the
same trap and the same cure as the vault's projection test.

### 6. `cap` refuses a curve measured against another version of the checker

The failure this prevents is silent. A checker edited between the control arm's run and the
candidate's produces two curves that compare perfectly, in the same units, with the same
shape, and mean nothing. Nothing downstream could notice, so the check goes where the two
curves first meet.

### 7. A checker is total, and a contract is a contract

Every `check` here scores prose, empty strings, control characters and numbers-where-a-
permutation-was-asked-for as **wrong**, never as an error. definitions.md §Checker:

> a checker that raises on a malformed answer is a checker that scores some wrong answers as
> "error" rather than as wrong, and the difference between those two categories is where a
> generous evaluation hides.

Totality is enforced by a test rather than by a `try/except` in `score`, which would convert a
genuinely broken checker into a silent stream of zeroes.

The stricter half is the same rule: a *correct* answer with an explanation appended scores
zero. A checker that skipped tokens it did not understand would let an arm hedge — append a
second guess, keep most of the credit. This one was not caught by the first draft of the test
suite, which only checked that a malformed answer stayed inside `[0, 1]`; a skip-junk checker
satisfies that happily. `an_answer_with_anything_but_the_answer_in_it_is_wrong` is the fix.

### 8. `question` and `data` are two fields, and the checker reads `data`

An `Instance` carries what the arm is shown and, separately, the canonical form the checker
recomputes from. T2 forces the split: its change points are *unannounced*, so the arm cannot
see where the regime changed and the checker has to. A checker reading the prose it happened
to show the arm is one edit away from scoring against a hint.

## Failure modes

- **Non-monotone curves.** `cap` is "the largest size that clears", exactly as definitions.md
  words it. On a noisy non-monotone curve that can be a fluke at a large size sitting above
  several sizes that failed. The definition is inside the hash `CHARTER.md` names, so
  tightening it to "the largest size such that every smaller size also clears" is a
  superseding Charter and not a code change. Recorded here as a criticism a new Charter could
  quote.
- **A comment re-versions three families.** Editing a docstring in `tasks.py` changes all
  three family versions and therefore invalidates every pre-registered instance set against
  them. Loud, conservative, and annoying. The alternative leaks silent changes, which is
  worse.
- **T2's rule family is stated in the prompt.** The regime is a rotation and the question says
  so, because a mapping with no stated structure cannot be inferred at all from evidence about
  other cues. That makes T2 a two-step inference rather than an open-ended adaptation problem,
  and it is a weaker task than the Charter's prose suggests.
- **T3's occurrences are planted at a fixed rate.** At `DENSITY` alone, an 80-token stream
  produces roughly one A-B pair inside `REACH` by luck, which makes the family a single-needle
  hunt and F1 nearly binary. Planting one occurrence per `PLANT` tokens keeps the occurrence
  density fixed as the stream lengthens — which is what "size is stream length at fixed event
  density" has to mean if size is the only thing varying — but it does mean the ground truth
  is partly constructed rather than wholly emergent.
- **`inspect.getsource` needs source on disk.** A family whose functions came from a REPL
  cannot be versioned. It raises a `TaskError` saying so rather than falling back to a weaker
  identity.

## What this does not decide

- **Nothing here measures a joule or a second.** `cap` as the Charter defines it also requires
  every instance to have been answered inside `B` and inside `W`, on a system prepared inside
  `P` for a declared `N`. What this module computes is the score half, and quoting it alone
  would be quoting a capability with no budget beside it — which §Capability metric says is
  not a result. The type that pairs them arrives in 8b.
- **No arm exists yet.** There is no transformer control arm, no tuning, and no run loop. All
  four of Phase 8's minimum tests are 8b's, and 8b is where `baseline_arm_runs_on_every_
  evaluation` and `measured_and_estimated_energy_are_never_compared_without_a_flag` land.
- **The definitions file's T1 worked example does not compose.** It gives `5 1 3 4 2` for
  `(1 2)(3 4)(1 5)`; the answer is `5 1 4 3 2` under the convention the rest of the example
  fixes, and no reading of "compose these" reproduces the published one — it leaves positions
  3 and 4 exactly as it found them, which is `(3 4)` having had no effect. That file is inside
  the hash `CHARTER.md` names, so correcting it supersedes the Charter and costs a fresh
  signature. `the_definitions_worked_example_for_t1_does_not_compose` pins the arithmetic so
  that nobody reconciles the two by changing the code instead.

## How it is tested

`tests/test_bench.py`, thirty tests, none of which needs `knk`, a network, or a model.

- `a_task_familys_version_covers_the_source_of_its_checker` — swapping the checker for a stub
  changes the version. This failed on its first run against the real implementation.
- `an_instance_set_is_reproducible_from_its_seed` and
  `an_instance_sets_version_is_the_instances_not_the_recipe`.
- `a_single_size_is_an_accuracy_not_a_curve`,
  `a_curve_refuses_a_size_measured_on_too_few_instances`.
- `a_cap_needs_its_interval_to_clear_not_just_its_mean`,
  `a_cap_is_none_when_nothing_clears_rather_than_zero`,
  `a_curve_measured_against_another_version_of_the_checker_is_refused`.
- `the_interval_is_the_same_in_a_second_process` — three `PYTHONHASHSEED`s, three subprocesses.
- `a_checker_scores_a_malformed_answer_as_wrong_rather_than_raising` and
  `an_answer_with_anything_but_the_answer_in_it_is_wrong`, over all three families.
- `a_reference_answer_scores_one_and_a_wrong_one_does_not` solves each family by a **second
  implementation** written in the test file. A test that asked the checker for the answer and
  fed it back would pass against a checker that scores everything 1.0.
- `t2_withholds_the_queried_cue_since_the_last_change_point` — answering from memory is
  answering from before the change, and is wrong.

Eighteen deliberate breaks were applied to `tasks.py` and `capability.py` in turn; sixteen
were caught on the first pass. The two survivors were the skip-junk checker (§7, now covered)
and a patch of mine that turned out to be a no-op.

`g0rd0n bench families` and `g0rd0n bench sample --family T1 --size 4 --seed 3 --answer ...`
exist for the same reason: the cheapest way to check a checker is to read one instance and
grade it by hand. All three families were verified that way before this was committed.
