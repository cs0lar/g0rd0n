"""The Ledger: reserve, spend, settle. Three operations, and no others.

The priced-before-run invariant lives here, and it is enforced by the shape of the API
rather than by a rule anyone has to remember: `spend` takes a `Reservation`, and the only
way to obtain one is `reserve`. There is no overload that accepts a wager id and a cost. A
call that has not been priced cannot be recorded, so it cannot happen.

    reservation = ledger.reserve(wager_id, estimate, agent)
    result = cell.run(...)
    ledger.settle(reservation)

Deletion criterion: this module holds the wager that every dollar maps to exactly one claim,
before it is spent rather than after. Delete it and `no_priced_call_without_a_reservation`
and `costs_attributed_to_a_wager_sum_to_the_session_total` both lose their verdicts, and
"what did this session buy?" goes back to being a question you answer by remembering.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from g0rd0n.config import Config
from g0rd0n.ledger import journal
from g0rd0n.ledger.cost import Cost
from g0rd0n.ledger.journal import Entry

WagerId = str
ReservationId = str

#: Cap comparisons are made to the tenth of a cent. Costs are floats, per AGENTS.md's Core
#: Types, so a total accumulated in a different order can land a few machine-epsilons either
#: side of a cap; refusing a reservation over float dust would be a bug that only appears in
#: production. Whether money should be a Decimal is deferred, and recorded in ADR 0002.
TOLERANCE_USD = 1e-4


class LedgerError(Exception):
    """The ledger was asked for something that would make its record untrue."""


class BudgetExhausted(LedgerError):
    """A reservation would take spend past a declared cap.

    Not a crash and not a verdict. Caught at exactly one place — the CLI's error boundary —
    where it settles what is open and stops. Running out of money says nothing about the
    world, and must never be recorded as one of `Verdict`'s outcomes.
    """


class Overspend(LedgerError):
    """Work cost more than was reserved for it. Never silently allowed."""


@dataclass(frozen=True)
class Reservation:
    """Permission to spend a stated amount against exactly one claim.

    Hold one of these and you may spend; there is no other way to get one than `reserve`,
    and no way to spend without one. That is the whole enforcement mechanism.
    """

    id: ReservationId
    wager_id: WagerId
    agent: str
    estimate: Cost


class Ledger:
    """Money committed to claims, and the caps that stop it.

    Not constructed directly in normal use — see `open_session`, which guarantees that
    whatever is open when the session ends gets settled.
    """

    def __init__(
        self,
        config: Config,
        *,
        session: str,
        campaign: str,
        phase: str,
        dry_run: bool = False,
    ) -> None:
        self._config = config
        self._session = session
        self._campaign = campaign
        self._phase = phase
        self._dry_run = dry_run
        self._entries: dict[ReservationId, Entry] = journal.replay(config.ledger_journal)

    @property
    def open_reservations(self) -> tuple[Reservation, ...]:
        """Everything reserved in this session and not yet settled, oldest first."""
        return tuple(
            Reservation(entry.id, entry.wager_id, entry.agent, entry.estimate)
            for entry in self._entries.values()
            if not entry.settled and entry.session == self._session
        )

    def reserve(self, wager_id: WagerId, estimate: Cost, agent: str) -> Reservation:
        """Set money aside for one claim, before any of the work is done.

        Raises `BudgetExhausted` if the estimate would take committed spend past the
        session, campaign, or standing cap. The check is made against money *committed* —
        settled actuals plus the estimates of everything still open — not money already
        spent, because a reservation nobody has drawn on yet is still money that is not
        available to another claim.
        """
        self._check_caps(estimate)
        reservation = Reservation(
            id=f"r-{uuid.uuid4().hex[:12]}",
            wager_id=wager_id,
            agent=agent,
            estimate=estimate,
        )
        record = {
            "event": "reserve",
            "at": journal.now().isoformat(),
            "session": self._session,
            "campaign": self._campaign,
            "phase": self._phase,
            "reservation": reservation.id,
            "wager": wager_id,
            "agent": agent,
            "estimate": estimate.as_dict(),
        }
        self._append(record)
        self._entries[reservation.id] = Entry(
            id=reservation.id,
            wager_id=wager_id,
            agent=agent,
            session=self._session,
            campaign=self._campaign,
            phase=self._phase,
            at=journal.now(),
            estimate=estimate,
        )
        return reservation

    def spend(self, reservation: Reservation, actual: Cost) -> Cost:
        """Record what a piece of work actually took. Returns the running total.

        Raises `Overspend` if this would take the reservation past its estimate in any
        dimension, and records nothing when it does: the estimate was wrong, and the caller
        finds out by being stopped rather than by reading it later.
        """
        entry = self._must_be_open(reservation)
        total = entry.spent + actual
        over = total.exceeds(reservation.estimate)
        if over:
            raise Overspend(
                f"{reservation.id} ({reservation.wager_id}) is over its estimate "
                f"in {', '.join(over)}"
            )
        self._append(
            {
                "event": "spend",
                "at": journal.now().isoformat(),
                "reservation": reservation.id,
                "actual": actual.as_dict(),
            }
        )
        entry.spent = total
        return total

    def settle(self, reservation: Reservation) -> Cost:
        """Close a reservation and hand back what was not spent. Returns the actual cost."""
        entry = self._must_be_open(reservation)
        self._append(
            {
                "event": "settle",
                "at": journal.now().isoformat(),
                "reservation": reservation.id,
                "total": entry.spent.as_dict(),
            }
        )
        entry.settled = True
        return entry.spent

    def _append(self, record: journal.Record) -> None:
        """Write first, then believe it.

        The in-memory total is updated by the caller only after this returns, so a total
        that exists is a total the journal already agrees with. knk's durable-before-visible
        rule, applied to money.

        A dry run keeps the state and skips the write: it can tell you what a plan would
        cost and whether it would bust a cap, and leaves no trace that it asked.
        """
        if not self._dry_run:
            journal.append(self._config.ledger_journal, record)

    def _must_be_open(self, reservation: Reservation) -> Entry:
        entry = self._entries.get(reservation.id)
        if entry is None:
            raise LedgerError(f"no such reservation: {reservation.id}")
        if entry.settled:
            raise LedgerError(f"reservation {reservation.id} has already settled")
        return entry

    def _check_caps(self, estimate: Cost) -> None:
        scopes = (
            ("session", self._config.session_usd, self._committed(session=self._session)),
            ("campaign", self._config.campaign_usd, self._committed(campaign=self._campaign)),
            ("standing", self._config.standing_usd, self._committed()),
        )
        for name, cap, committed in scopes:
            if committed + estimate.usd > cap + TOLERANCE_USD:
                raise BudgetExhausted(
                    f"the {name} cap of ${cap:.2f} would be exceeded: ${committed:.2f} is "
                    f"already committed and this reservation asks for ${estimate.usd:.2f}"
                )

    def _committed(self, *, session: str | None = None, campaign: str | None = None) -> float:
        return sum(
            entry.committed.usd
            for entry in self._entries.values()
            if (session is None or entry.session == session)
            and (campaign is None or entry.campaign == campaign)
        )


@contextmanager
def open_session(
    config: Config,
    *,
    session: str | None = None,
    campaign: str,
    phase: str,
    dry_run: bool = False,
) -> Iterator[Ledger]:
    """Run a session against the ledger, settling whatever is still open when it ends.

    Clean settlement is in the `finally`, so it happens on the way out however the session
    ends: normally, on `BudgetExhausted`, or on any other exception. A reservation that is
    never settled is money the ledger believes is still promised to a claim nobody is
    working on, which would quietly shrink every subsequent budget.
    """
    ledger = Ledger(
        config,
        session=session or f"s-{uuid.uuid4().hex[:12]}",
        campaign=campaign,
        phase=phase,
        dry_run=dry_run,
    )
    try:
        yield ledger
    finally:
        for reservation in ledger.open_reservations:
            ledger.settle(reservation)
