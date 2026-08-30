"""The journal: an append-only record of every reservation, spend, and settlement.

The same shape as the kernel it will later feed. Records are appended and never edited; the
running totals the Ledger enforces caps against, and the report the cockpit prints, are both
*derived* by replaying this file. Nothing else is authoritative, so a disagreement between a
total and the journal is always the total's fault.

AGENTS.md's vocabulary reserves `costs wager → cost` for settled costs. **Nothing writes that
edge yet**, so `wager_id` here is a bare string that nothing joins to a kernel entity, and the
vault's `Wagers/` and `Costs/` folders stay empty. Phase 7 mints the `WagerId`s to point at
and Phase 11's `why` is the first caller that needs the join. When it lands the edge is a
*projection* of this file — committed after the money is already durable here, never before —
because the Ledger cuts across every layer and is owned by none (AGENTS.md, Keep layers
separate), so it does not depend on the kernel bridge in either direction.

Deletion criterion: this module holds the wager that a crash costs g0rd0n nothing but time.
Delete it and the running totals live only in memory, which loses the verdict on
`budget_exhaustion_settles_cleanly_and_loses_no_records` and on every question of the form
"what did we spend last week", since there would be nothing left to ask.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from g0rd0n.ledger.cost import ZERO, Cost

#: One line of the journal.
Record = dict[str, Any]

#: The three things that ever happen to money, and the only event names the journal accepts.
EVENTS = ("reserve", "spend", "settle")


class JournalError(Exception):
    """The journal cannot be read, or says something that cannot be true."""


@dataclass
class Entry:
    """One reservation, as the journal remembers it.

    Mutable, unlike everything else here, because it *is* the replay: the accumulator that
    `replay` folds the append-only records into. It is never written anywhere.
    """

    id: str
    wager_id: str
    agent: str
    session: str
    campaign: str
    phase: str
    at: datetime
    estimate: Cost
    spent: Cost = field(default=ZERO)
    settled: bool = False

    @property
    def committed(self) -> Cost:
        """What this reservation has taken out of the budget.

        The estimate while it is open — money promised to a claim is money that cannot be
        promised to another one — and the actual once it has settled, which is how an
        honest estimate hands the difference back.
        """
        return self.spent if self.settled else self.estimate


def append(path: Path, record: Record) -> None:
    """Add one record to the journal, creating it if this is the first.

    Opened, written, and closed per record. Slow, and irrelevantly so at the rate money is
    committed; in exchange there is no buffer that can hold the last few records hostage
    when the process dies.
    """
    if record.get("event") not in EVENTS:
        raise JournalError(f"not a journal event: {record.get('event')!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def replay(path: Path) -> dict[str, Entry]:
    """Fold the journal into one `Entry` per reservation, in the order it happened.

    A journal that does not exist yet is an empty history, not an error: g0rd0n has to be
    able to report that it has spent nothing before it has spent anything. A journal that
    exists and is damaged is an error — silently skipping a line it cannot parse is how a
    ledger starts lying.
    """
    if not path.exists():
        return {}

    entries: dict[str, Entry] = {}
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalError(f"{path}:{number} is not valid JSON: {exc}") from exc
            try:
                _apply(entries, record)
            except (KeyError, TypeError, ValueError) as exc:
                raise JournalError(f"{path}:{number} is not a usable record: {exc}") from exc
    return entries


def now() -> datetime:
    """The clock, in one place, in UTC.

    A journal in local time is a journal that lies twice a year.
    """
    return datetime.now(UTC)


def _apply(entries: dict[str, Entry], record: Record) -> None:
    event = record["event"]
    reservation = record["reservation"]

    if event == "reserve":
        if reservation in entries:
            raise ValueError(f"reservation {reservation} was opened twice")
        entries[reservation] = Entry(
            id=reservation,
            wager_id=record["wager"],
            agent=record["agent"],
            session=record["session"],
            campaign=record["campaign"],
            phase=record["phase"],
            at=datetime.fromisoformat(record["at"]),
            estimate=Cost.from_dict(record["estimate"]),
        )
        return

    entry = entries.get(reservation)
    if entry is None:
        raise ValueError(f"{event} against unknown reservation {reservation}")
    if entry.settled:
        raise ValueError(f"{event} against settled reservation {reservation}")

    if event == "spend":
        entry.spent = entry.spent + Cost.from_dict(record["actual"])
    else:
        entry.spent = Cost.from_dict(record["total"])
        entry.settled = True
