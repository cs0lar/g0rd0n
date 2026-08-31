"""The Ledger: what g0rd0n spent, on which claim, and whether it was allowed to.

Four modules, one mechanism each: `cost` is the unit, `journal` is the append-only record,
`ledger` is the three operations and the caps, `report` is the derived view. The Ledger cuts
across every layer of the system and is owned by none of them (AGENTS.md, Keep layers
separate), so it depends on `config` and nothing else in g0rd0n.

Deletion criterion: this module holds the wager that the price of a claim is one import
away from anywhere in the system. Delete it and `no_priced_call_without_a_reservation` — a
test over `Ledger`'s public surface, reached through this package — loses the boundary it
is asked about: callers reach into `g0rd0n.ledger.ledger.Ledger`, coupling every layer to a
file layout rather than to the three operations, which is the first step towards a fourth
one appearing.
"""

from g0rd0n.ledger.cost import DIMENSIONS, ZERO, Cost
from g0rd0n.ledger.journal import Entry, JournalError
from g0rd0n.ledger.ledger import (
    BudgetExhausted,
    Ledger,
    LedgerError,
    Overspend,
    Reservation,
    open_session,
)

__all__ = [
    "DIMENSIONS",
    "ZERO",
    "BudgetExhausted",
    "Cost",
    "Entry",
    "JournalError",
    "Ledger",
    "LedgerError",
    "Overspend",
    "Reservation",
    "open_session",
]
