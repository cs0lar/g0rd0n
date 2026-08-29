"""The Cost type: immutable, additive, serialisable."""

import pytest

from g0rd0n.ledger import ZERO, Cost
from g0rd0n.ledger.cost import DIMENSIONS


def test_costs_add_dimension_by_dimension() -> None:
    a = Cost(tokens_in=100, usd=0.5, seconds=2.0)
    b = Cost(tokens_in=50, tokens_out=10, usd=0.25, gpu_seconds=1.5)

    assert a + b == Cost(tokens_in=150, tokens_out=10, usd=0.75, seconds=2.0, gpu_seconds=1.5)


def test_addition_is_commutative_and_has_an_identity() -> None:
    """A session total must not depend on the order its parts were totalled in."""
    a = Cost(tokens_in=100, usd=0.5)
    b = Cost(tokens_out=7, human_seconds=30.0)

    assert a + b == b + a
    assert a + ZERO == a


def test_a_cost_is_immutable() -> None:
    """A cost that can be edited after the fact is not evidence."""
    cost = Cost(usd=1.0)

    with pytest.raises(AttributeError):
        cost.usd = 2.0  # type: ignore[misc]


def test_a_negative_cost_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative: usd"):
        Cost(usd=-0.01)


def test_exceeds_names_every_dimension_that_is_over() -> None:
    """Not just dollars: an estimate right about money and wrong about time is still wrong."""
    estimate = Cost(tokens_in=100, usd=1.0, seconds=10.0)
    actual = Cost(tokens_in=150, usd=0.5, seconds=30.0)

    assert actual.exceeds(estimate) == ("tokens_in", "seconds")
    assert Cost(usd=1.0).exceeds(estimate) == ()


def test_a_cost_survives_a_round_trip_through_the_journal_format() -> None:
    cost = Cost(tokens_in=1, tokens_out=2, usd=3.5, seconds=4.5, gpu_seconds=5.5, human_seconds=6.5)

    assert Cost.from_dict(cost.as_dict()) == cost


def test_every_dimension_is_serialised() -> None:
    """A dimension that is not written is a dimension that is lost on the next replay."""
    assert set(ZERO.as_dict()) == set(DIMENSIONS)
    assert len(DIMENSIONS) == 6


def test_an_unknown_dimension_from_the_journal_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown cost dimensions: eur"):
        Cost.from_dict({"usd": 1.0, "eur": 2.0})
