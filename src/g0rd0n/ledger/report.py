"""The cost report: a derived view over the journal. Reads, never writes.

The same relationship the vault will have to the kernel. Every number here is recomputed by
replaying the journal, so the report cannot drift from the record — there is no stored total
for it to disagree with.

This is the module that answers the question AGENTS.md says keeps the system honest: what
did this session cost, and what did it buy? The "what did it buy" half is the grouping key.

Deletion criterion: this module holds the wager that a human can answer "what did this cost
and what did it buy" from one command. Delete it and the journal is still true and still
unreadable, which loses the verdict on the Phase 1 review checklist and on
`costs_attributed_to_a_wager_sum_to_the_session_total` — the test that the parts add up to
the whole is only meaningful if something adds them up.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from g0rd0n.ledger import journal
from g0rd0n.ledger.cost import ZERO, Cost
from g0rd0n.ledger.journal import Entry

#: What spend can be grouped by. AGENTS.md, Phase 1: "by wager, by phase, by agent, by day".
BY = ("wager", "phase", "agent", "day")


@dataclass(frozen=True)
class Row:
    """One group of reservations, and what it came to."""

    key: str
    reservations: int
    reserved: Cost
    spent: Cost


def rows(entries: Iterable[Entry], by: str) -> list[Row]:
    """Group reservations and total them. Largest spend first, ties broken by key."""
    if by not in BY:
        raise ValueError(f"cannot group by {by!r}; try one of {', '.join(BY)}")

    grouped: dict[str, Row] = {}
    for entry in entries:
        key = _key(entry, by)
        row = grouped.get(key) or Row(key, 0, ZERO, ZERO)
        grouped[key] = Row(
            key=key,
            reservations=row.reservations + 1,
            reserved=row.reserved + entry.estimate,
            spent=row.spent + entry.spent,
        )
    return sorted(grouped.values(), key=lambda row: (-row.spent.usd, row.key))


def render(rows_: list[Row], by: str) -> str:
    """Format a report for a terminal, with the total last so it is the last thing read."""
    if not rows_:
        return "Nothing has been reserved yet, so nothing has been spent."

    total = Row(
        key="TOTAL",
        reservations=sum(row.reservations for row in rows_),
        reserved=sum((row.reserved for row in rows_), ZERO),
        spent=sum((row.spent for row in rows_), ZERO),
    )
    width = max(len(by), *(len(row.key) for row in rows_), len(total.key))
    lines = [f"{by:<{width}}  {'n':>3}  {'reserved':>10}  {'spent':>10}  {'tokens':>15}"]
    lines += [_line(row, width) for row in rows_]
    lines.append("-" * len(lines[0]))
    lines.append(_line(total, width))
    return "\n".join(lines)


def read(path: Path, by: str) -> str:
    """Replay the journal and render it. The whole of `g0rd0n cost`."""
    return render(rows(journal.replay(path).values(), by), by)


def _key(entry: Entry, by: str) -> str:
    if by == "wager":
        return entry.wager_id
    if by == "phase":
        return entry.phase
    if by == "agent":
        return entry.agent
    return entry.at.date().isoformat()


def _line(row: Row, width: int) -> str:
    tokens = f"{row.spent.tokens_in}→{row.spent.tokens_out}"
    return (
        f"{row.key:<{width}}  {row.reservations:>3}  "
        f"{'$' + format(row.reserved.usd, '.3f'):>10}  "
        f"{'$' + format(row.spent.usd, '.3f'):>10}  {tokens:>15}"
    )
