# ADR 0012 — Cheapest falsifier first, and what exhaustion means

- **Status:** Accepted
- **Date:** 2026-08-31
- **Phase:** 7b (The portfolio, the allocator, and the stopping rules)

## Context

AGENTS.md §Phase 7 states the allocation policy in one line:

> Rank open Wagers by `P(verdict flips the leading candidate) × value(flip) / price`, and run
> the one that could kill the current leader for the least money. Popper as a budget function.

It leaves four things undecided, and each of them is a place where a plausible choice would
quietly turn the policy into something else: what "flips" means arithmetically, what a flip is
*worth*, what `price` is when a `Cost` has six dimensions, and when to stop.

## Decision

### 1. P(flip) is asymmetric, and its zero is the point

The leader is the live family with the highest belief.

- **A wager on the leader** flips the lead by *losing*. `P(flip) = 1 - prior`.
- **A wager on a challenger** flips the lead by winning, and only if winning would put it in
  front. Post-corroboration belief is modelled with `evidence.channel.combine` — the Evidence
  Channel's own capped noisy-OR — so the arithmetic that ranks the wager and the arithmetic
  that will actually move the belief if it is run are the same function.
  `P(flip) = prior` when `combine(belief, prior) > lead`, and **0.0** otherwise.

That zero is the whole defence against a failure mode ADR 0001 named:

> **Wager inflation.** Slicing work into many small Wagers to make each look cheap. The
> allocator ranks by `P(flip) × value(flip) / price`, so a Wager that cannot flip anything
> ranks last however cheap it is.

Cheapness is a divisor and never a reason. A free wager that cannot change what the programme
believes scores exactly zero, and no price makes it worth running.

### 2. value(flip) is how far the programme's best candidate moves

Both branches measure the same thing, so they are comparable:

- leader refuted: `lead - runner_up` — how far the field falls back when the best candidate
  goes.
- challenger corroborated: `combine(belief, prior) - lead` — the margin the new leader wins by.

A consequence worth stating because it is not obvious: killing a leader that towers over the
field is worth more than killing one in a dead heat. That is correct. In a dead heat the
programme's next move barely changes when the leader dies, so learning that it dies buys less.

### 3. Price is denominated in dollars and human attention, and is refused otherwise

`price_of` = `usd + human_seconds × HUMAN_USD_PER_HOUR / 3600`. Wall-clock is excluded because
waiting is not scarce here. GPU-seconds are excluded because they are bought with dollars, and
a wager that spends them should say so in dollars.

`HUMAN_USD_PER_HOUR` is a **ranking weight, not a price**. It never enters a `Cost`, never
reaches the journal, and no reservation is ever made from it. It exists because a wager
costing forty hours of somebody's reading and no dollars is not free, and a ranking that
treated it as free would put it first every time.

A wager priced in neither dimension **raises** rather than being guessed at or ranked as free.
Same discipline as `Config.price_of`, which refuses to run an unpriced model rather than
inventing a number that would sit in the ledger forever. Here the invented number would sit in
a ranking instead, which is cheaper to be wrong about and still not free.

### 4. Read once, then rank purely

`read` makes one pass over the kernel — `changes_since(0)`, the same enumeration path the vault
uses — and returns a `Board`. `rank`, `score`, `allocate` and `criticisms` are functions of
that value and touch nothing. This is the split `vault.note.render` gets, for the same reason:
the ranking is checkable by calling a function twice, and most of `tests/test_allocator.py`
runs with no `knk` at all.

Reading *everything* rather than the wagers in hand is deliberate. `Standing.untested` has to
mean "nothing has tried to kill this", and asking only the wagers the caller happens to be
holding would answer "nothing on this list has tried" — reporting a family as never attacked
because the attack was declared in another file.

### 5. Two stopping rules are built and the third already exists

AGENTS.md asks for three.

- **Per-family patience.** `PATIENCE = 3`: a family with three settled wagers that reached no
  verdict stops being fundable. Note what it counts — *settled minus conclusive*. A family that
  lost three arguments is refuted, which is a different state; a family whose tests keep
  settling nothing is evidence about the *tests*, and the response is a criticism of the
  Charter rather than a refutation of the paradigm.
- **The question is exhausted.** `allocate` returns `Exhausted` when nothing offered scores
  above zero, either because the field is empty or because nothing could unseat the leader.
- **Per-Wager price cap.** Not built, because it already exists: the cap *is* the
  pre-registered price. `cortex.wager.reserve` reserves exactly what the wager registered and
  `Ledger.spend` raises `Overspend` past it. A second cap here would be a second way to express
  something the Wager already expresses, which The Imperative (1) forbids.

### 6. Exhaustion returns criticisms, not a best-effort wager

`Exhausted` has **no field naming a wager to run**. AGENTS.md asks that an exhausted question
trigger reformulation rather than more spending, and a result carrying a "best remaining"
wager is an invitation to spend on it anyway.

What it carries instead is `criticisms`: one sentence per family whose standing is a complaint
about the *question* rather than about the paradigm — a family refuted while the question still
ranges over it, a family whose tests keep settling nothing, and a family still standing that
nothing ever tried to kill. ADR 0007 refuses a supersession with no criticism, so an exhausted
question that produced none would be a dead end rather than a handover. A test builds a charter
document out of them and parses it, so the handover is checked end to end rather than asserted.

Exhaustion is **not** budget exhaustion. `BudgetExhausted` says something about g0rd0n's wallet
and nothing about the world. Exhaustion here says "nothing we could run could change what we
believe", which says a great deal, and the answer to it is a better question rather than a
bigger budget.

## What the shipped portfolio says today

Nine families from AGENTS.md §Candidate portfolio, each with a prior and a kill criterion that
names the chartered arena where that paradigm's advantage is *supposed* to be largest. The
kill criteria are all different, and each is denominated in the Charter's own currency — a
budget and a control arm to lose to — because a criterion naming neither is a wish. The
control arm is in the list rather than beside it, and `CONTROL_ARM` names it so a portfolio
missing one is a test failure rather than a review comment.

The cheapest falsifier available today is a **literature survey, not a bench**: `survey` builds
one wager per family out of Phase 6's machinery. Its kill criterion is the family's own,
qualified by what a survey can actually observe — *a retrievable primary source reporting* the
measurement — because a missing source is not a refutation (ADR 0009). A survey that could
refute by silence would delete every family whose literature lives on a host nobody allowlisted.

Run against a committed Charter, the allocator's first answer is **to try to kill the control
arm**, which is the highest-prior family and therefore the leader. That is the policy working:
the arm whose success would answer the question in the boring direction is the cheapest thing
to settle, and settling it early is worth more than any amount of work on a long shot.

## Failure modes

- **A low-prior family is permanently unfundable.** Five of the nine score zero at t=0 because
  one corroboration would not lift them past the leader, so they are never allocated to and
  stay untested. This is cheapest-falsifier-first behaving as specified — you do not spend on a
  candidate that cannot become the leader — and it is the sharpest consequence of the policy.
  The mitigation is not in the allocator: `Standing.untested` flags exactly these families, and
  `criticisms` turns a still-untested family into a written complaint about the question when
  the question exhausts. The two mechanisms are meant to be read together.
- **The priors are made up.** They are, and AGENTS.md says so ("priors, not endorsements").
  They are in a file, in a diff, with numbers, which is the most that can honestly be claimed
  for them. The Evidence Channel moves them; nothing else should.
- **A leader that leads only because nobody has attacked it.** The board flags it. The
  allocator does not treat it differently, which is a deliberate limit: this ADR does not
  decide whether an untested leader should be *preferred* as a target.
- **`HUMAN_USD_PER_HOUR` is one number for everybody's time.** It is, and it is wrong in
  detail. It is a divisor in a ranking and never a figure in the ledger, so the damage it can
  do is bounded by "ranked two wagers in the wrong order".
- **Patience measured in wager count rather than money.** Three cheap inconclusive surveys
  exhaust the same patience as three expensive inconclusive benches. Counting money instead
  would let a family absorb an unbounded number of cheap non-answers; counting attempts says
  the problem is that the tests do not settle anything, which is what patience is about.

## How it is tested

`tests/test_allocator.py`. Both AGENTS.md minimum tests for this half:

- `allocator_prefers_the_cheaper_of_two_equally_informative_wagers` — two wagers on the same
  family with the same prior, so `P(flip)` and `value` are identical by construction and only
  the divisor differs.
- `exhausted_question_triggers_reformulation_not_more_spending` — asserts the result carries no
  wager to run, that everything ranked scored zero, and that criticisms came back.

And, either side of them: `a_wager_that_cannot_flip_anything_ranks_last_however_cheap_it_is`,
`the_allocator_runs_what_could_kill_the_leader`,
`patience_runs_out_only_on_wagers_that_settled_nothing`,
`a_family_nothing_tried_to_kill_is_flagged_as_such`, `the_ranking_is_a_function_of_the_board`,
`a_wager_priced_in_neither_dollars_nor_attention_is_refused`,
`exhaustion_hands_back_criticisms_a_charter_could_actually_use`,
`the_board_agrees_with_the_evidence_channel_about_belief` (with a retraction, which is the case
that separates the scan from the lookup), and
`the_board_is_the_kernel_and_not_the_wagers_we_happen_to_hold`.

Nineteen invariants were verified by breaking each one on purpose and watching a test fail.

## What this ADR does not decide

What produces a verdict — the Bench is Phase 8, and until it exists a survey wager is settled
by a person calling `cortex.wager.record`. Whether the allocator should learn its priors from
settled wagers (Phase 12's meta-loop, and doing it now would be scoring an estimator against
four data points). Whether an untested leader deserves preferential targeting. And how the
`P(flip)` model should change once a family carries several results rather than one belief
number.
