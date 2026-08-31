"""Cost: the six-dimensional unit of what something took.

`operating_cost` — what g0rd0n spends to do research. Not `target_energy`, which is the
energy profile of a candidate paradigm under evaluation and is a measured outcome, never a
budget. The two are both quantities about energy and are constantly confused; this type is
only ever the first (AGENTS.md, The Two Energies).

Immutable, additive, and serialisable, in that order of importance. Additive because a
session total is the sum of its parts and that sum must not depend on the order it was taken
in; immutable because a cost that can be edited after the fact is not evidence.

Deletion criterion: this module holds the wager that every dimension of what a claim cost is
recorded, not just the one that is easy to bill. Delete it and
`overspend_is_caught_in_any_dimension_not_just_dollars` and
`costs_attributed_to_a_wager_sum_to_the_session_total` lose their verdicts: `usd` becomes
the only currency, and any comparison involving wall-clock, GPU time, or human attention
goes unchecked — including the human-cell accounting that Phase 4 depends on.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any, Self


@dataclass(frozen=True)
class Cost:
    """What a piece of work took, in every currency g0rd0n spends."""

    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    seconds: float = 0.0
    gpu_seconds: float = 0.0
    human_seconds: float = 0.0

    def __post_init__(self) -> None:
        negative = [name for name in DIMENSIONS if getattr(self, name) < 0]
        if negative:
            raise ValueError(f"a cost cannot be negative: {', '.join(negative)}")

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            usd=self.usd + other.usd,
            seconds=self.seconds + other.seconds,
            gpu_seconds=self.gpu_seconds + other.gpu_seconds,
            human_seconds=self.human_seconds + other.human_seconds,
        )

    def exceeds(self, limit: "Cost") -> tuple[str, ...]:
        """The dimensions in which this cost is over `limit`, in declaration order.

        Every dimension, not just dollars: a reservation is a promise about all six, and an
        estimate that was right about money and wrong about wall-clock is still an estimate
        that was wrong. Scoring the estimator (AGENTS.md, Budget Discipline) needs to know
        which way.
        """
        return tuple(name for name in DIMENSIONS if getattr(self, name) > getattr(limit, name))

    def as_dict(self) -> dict[str, float]:
        """A plain mapping, for the journal."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Self:
        """Rebuild a cost from the journal, rejecting anything it does not recognise."""
        unknown = set(raw) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown cost dimensions: {', '.join(sorted(unknown))}")
        return cls(
            tokens_in=int(raw.get("tokens_in", 0)),
            tokens_out=int(raw.get("tokens_out", 0)),
            usd=float(raw.get("usd", 0.0)),
            seconds=float(raw.get("seconds", 0.0)),
            gpu_seconds=float(raw.get("gpu_seconds", 0.0)),
            human_seconds=float(raw.get("human_seconds", 0.0)),
        )


#: The dimensions of a Cost, in declaration order. Derived from the dataclass so the two can
#: never disagree.
DIMENSIONS: tuple[str, ...] = tuple(field.name for field in fields(Cost))

#: The identity of `Cost.__add__`, and what an unspent reservation has cost so far.
ZERO = Cost()
