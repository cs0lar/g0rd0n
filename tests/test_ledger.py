"""The Ledger: reserve, spend, settle, and the caps that stop them.

Four of the five Phase 1 minimum tests live here; the fifth
(`costs_attributed_to_a_wager_sum_to_the_session_total`) is in `test_report.py`, where the
thing that does the attributing lives. `no_priced_call_without_a_reservation` and
`costs_attributed_to_a_wager_sum_to_the_session_total` are permanent CI invariants and no
later phase may delete them (AGENTS.md, Testing Requirements).
"""

import inspect
import json
from pathlib import Path

import pytest

from g0rd0n.config import Config
from g0rd0n.ledger import (
    ZERO,
    BudgetExhausted,
    Cost,
    Ledger,
    LedgerError,
    Overspend,
    Reservation,
    open_session,
)
from g0rd0n.ledger import journal as journal_module


def config_for(
    tmp_path: Path, *, session: float = 5.0, campaign: float = 50.0, standing: float = 500.0
) -> Config:
    return Config(
        kernel_storage_root=tmp_path / "kernel",
        kernel_mcp_server=tmp_path / "mcp_server",
        vault_root=tmp_path / "vault",
        ledger_journal=tmp_path / "ledger.jsonl",
        session_usd=session,
        campaign_usd=campaign,
        standing_usd=standing,
        network_allowlist=("arxiv.org",),
        model_endpoint="https://api.anthropic.com/v1/messages",
        model_api_key_file=tmp_path / "anthropic-key",
        model_prices=(),
        human_queue=tmp_path / "human-queue",
        charter_path=tmp_path / "CHARTER.md",
        charter_definitions=tmp_path / "definitions.md",
    )


def ledger_for(tmp_path: Path, **caps: float) -> Ledger:
    return Ledger(config_for(tmp_path, **caps), session="s-1", campaign="c-1", phase="1")


def test_no_priced_call_without_a_reservation(tmp_path: Path) -> None:
    """The priced-before-run invariant, enforced by the shape of the API.

    `spend` and `settle` take a `Reservation`, and `reserve` is the only thing that makes
    one. There is no overload taking a wager id and a cost, so a call that was never priced
    cannot be recorded — not "must not be", cannot be. This test pins that surface: a fourth
    operation, or a `spend` that accepts a bare wager id, has to break it on the way in.
    """
    operations = {
        name: inspect.signature(getattr(Ledger, name))
        for name, member in vars(Ledger).items()
        if callable(member) and not name.startswith("_")
    }

    assert set(operations) == {"reserve", "spend", "settle"}
    for name in ("spend", "settle"):
        parameters = operations[name].parameters
        assert list(parameters)[1] == "reservation"
        assert parameters["reservation"].annotation is Reservation


def test_overspend_against_a_reservation_raises(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path)
    reservation = ledger.reserve("w-1", Cost(usd=1.0, tokens_in=100), agent="cell-a")

    ledger.spend(reservation, Cost(usd=0.6, tokens_in=60))

    with pytest.raises(Overspend, match="usd"):
        ledger.spend(reservation, Cost(usd=0.6))


def test_an_overspend_records_nothing(tmp_path: Path) -> None:
    """A refused spend leaves the journal exactly as it was. It never half-succeeds."""
    config = config_for(tmp_path)
    ledger = Ledger(config, session="s-1", campaign="c-1", phase="1")
    reservation = ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")
    before = config.ledger_journal.read_text(encoding="utf-8")

    with pytest.raises(Overspend):
        ledger.spend(reservation, Cost(usd=2.0))

    assert config.ledger_journal.read_text(encoding="utf-8") == before
    assert ledger.settle(reservation) == ZERO


def test_overspend_is_caught_in_any_dimension_not_just_dollars(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path)
    reservation = ledger.reserve("w-1", Cost(usd=1.0, human_seconds=60.0), agent="a-person")

    with pytest.raises(Overspend, match="human_seconds"):
        ledger.spend(reservation, Cost(usd=0.1, human_seconds=90.0))


def test_spending_exactly_the_estimate_is_allowed(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path)
    reservation = ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")

    assert ledger.spend(reservation, Cost(usd=1.0)) == Cost(usd=1.0)


def test_a_reservation_beyond_the_session_cap_raises_budget_exhausted(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path, session=5.0)
    ledger.reserve("w-1", Cost(usd=4.0), agent="cell-a")

    with pytest.raises(BudgetExhausted, match="session cap"):
        ledger.reserve("w-2", Cost(usd=1.5), agent="cell-b")


def test_each_of_the_three_caps_bites(tmp_path: Path) -> None:
    """Session, campaign, standing. A cap that is never checked is not a cap."""
    for scope, caps in (
        ("session", {"session": 1.0, "campaign": 50.0, "standing": 500.0}),
        ("campaign", {"session": 50.0, "campaign": 1.0, "standing": 500.0}),
        ("standing", {"session": 50.0, "campaign": 50.0, "standing": 1.0}),
    ):
        ledger = ledger_for(tmp_path / scope, **caps)

        with pytest.raises(BudgetExhausted, match=f"{scope} cap"):
            ledger.reserve("w-1", Cost(usd=2.0), agent="cell-a")


def test_caps_are_checked_against_money_committed_not_money_spent(tmp_path: Path) -> None:
    """An open reservation nobody has drawn on is still money promised to a claim."""
    ledger = ledger_for(tmp_path, session=5.0)
    ledger.reserve("w-1", Cost(usd=5.0), agent="cell-a")

    with pytest.raises(BudgetExhausted):
        ledger.reserve("w-2", Cost(usd=0.5), agent="cell-b")


def test_settling_under_the_estimate_hands_the_difference_back(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path, session=5.0)
    first = ledger.reserve("w-1", Cost(usd=5.0), agent="cell-a")
    ledger.spend(first, Cost(usd=1.0))
    ledger.settle(first)

    assert ledger.reserve("w-2", Cost(usd=3.0), agent="cell-b").estimate == Cost(usd=3.0)


def test_budget_exhaustion_settles_cleanly_and_loses_no_records(tmp_path: Path) -> None:
    """Exhaustion stops the session where it said it would, and keeps everything it learned.

    The exception escapes `open_session` — the CLI is the one place that catches it — but on
    the way out every open reservation is settled, so the journal is left consistent and a
    later process replays exactly what happened.
    """
    config = config_for(tmp_path, session=5.0)

    with (
        pytest.raises(BudgetExhausted),
        open_session(config, session="s-1", campaign="c-1", phase="1") as ledger,
    ):
        first = ledger.reserve("w-1", Cost(usd=3.0, tokens_in=1000), agent="cell-a")
        ledger.spend(first, Cost(usd=2.5, tokens_in=900))
        ledger.reserve("w-2", Cost(usd=4.0), agent="cell-b")

    replayed = journal_module.replay(config.ledger_journal)
    assert [entry.settled for entry in replayed.values()] == [True]
    assert replayed[first.id].spent == Cost(usd=2.5, tokens_in=900)


def test_an_ordinary_session_settles_what_it_forgot_to(tmp_path: Path) -> None:
    config = config_for(tmp_path)

    with open_session(config, session="s-1", campaign="c-1", phase="1") as ledger:
        reservation = ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")
        ledger.spend(reservation, Cost(usd=0.4))

    entries = journal_module.replay(config.ledger_journal)
    assert entries[reservation.id].settled
    assert entries[reservation.id].spent == Cost(usd=0.4)


def test_a_crashing_session_still_settles(tmp_path: Path) -> None:
    """Clean settlement is in the `finally`, so it does not depend on how the session ends."""
    config = config_for(tmp_path)

    with (
        pytest.raises(ZeroDivisionError),
        open_session(config, session="s-1", campaign="c-1", phase="1") as ledger,
    ):
        ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")
        raise ZeroDivisionError

    assert all(entry.settled for entry in journal_module.replay(config.ledger_journal).values())


def test_dry_run_produces_a_cost_estimate_and_makes_no_calls(tmp_path: Path) -> None:
    """A dry run prices the whole plan and leaves no trace that it asked.

    "Makes no calls" is only half-testable at Phase 1, because nothing calls anything yet:
    what is checked here is that it writes nothing and still answers the question. The other
    half — that no priced call is made — becomes testable with the cell runtime in Phase 4,
    where the reservation is what a cell needs in order to run at all.
    """
    config = config_for(tmp_path)

    with open_session(config, campaign="c-1", phase="1", dry_run=True) as ledger:
        first = ledger.reserve("w-1", Cost(usd=2.0, tokens_in=1000), agent="cell-a")
        second = ledger.reserve("w-2", Cost(usd=1.5), agent="cell-b")
        priced = first.estimate + second.estimate

    assert priced == Cost(usd=3.5, tokens_in=1000)
    assert not config.ledger_journal.exists()


def test_a_dry_run_still_refuses_a_plan_that_would_bust_a_cap(tmp_path: Path) -> None:
    """Pricing a plan is only useful if it tells you the plan is unaffordable."""
    config = config_for(tmp_path, session=5.0)

    with (
        pytest.raises(BudgetExhausted),
        open_session(config, campaign="c-1", phase="1", dry_run=True) as ledger,
    ):
        ledger.reserve("w-1", Cost(usd=4.0), agent="cell-a")
        ledger.reserve("w-2", Cost(usd=4.0), agent="cell-b")

    assert not config.ledger_journal.exists()


def test_a_dry_run_prices_against_what_was_really_spent_before_it(tmp_path: Path) -> None:
    """The plan is priced against the real ledger, not against an empty one."""
    config = config_for(tmp_path, session=50.0, campaign=50.0, standing=5.0)
    with open_session(config, campaign="c-1", phase="1") as ledger:
        ledger.spend(ledger.reserve("w-1", Cost(usd=4.0), agent="cell-a"), Cost(usd=4.0))

    with (
        pytest.raises(BudgetExhausted, match="standing cap"),
        open_session(config, campaign="c-2", phase="1", dry_run=True) as ledger,
    ):
        ledger.reserve("w-2", Cost(usd=2.0), agent="cell-b")


def test_settling_twice_raises(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path)
    reservation = ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")
    ledger.settle(reservation)

    with pytest.raises(LedgerError, match="already settled"):
        ledger.settle(reservation)


def test_spending_against_an_unknown_reservation_raises(tmp_path: Path) -> None:
    ledger = ledger_for(tmp_path)
    forged = Reservation("r-nope", "w-1", "cell-a", Cost(usd=1.0))

    with pytest.raises(LedgerError, match="no such reservation"):
        ledger.spend(forged, Cost(usd=0.1))


def test_the_journal_is_written_before_the_total_is_believed(tmp_path: Path) -> None:
    """Durable-before-visible, applied to money: a total that exists is one on disk."""
    config = config_for(tmp_path)
    ledger = Ledger(config, session="s-1", campaign="c-1", phase="1")
    reservation = ledger.reserve("w-1", Cost(usd=1.0), agent="cell-a")
    ledger.spend(reservation, Cost(usd=0.25))

    events = [
        json.loads(line)["event"]
        for line in config.ledger_journal.read_text(encoding="utf-8").splitlines()
    ]
    assert events == ["reserve", "spend"]


def test_a_second_process_sees_what_the_first_one_spent(tmp_path: Path) -> None:
    config = config_for(tmp_path, session=50.0, campaign=50.0, standing=5.0)
    with open_session(config, campaign="c-1", phase="1") as first:
        first.spend(first.reserve("w-1", Cost(usd=4.5), agent="cell-a"), Cost(usd=4.5))

    with (
        pytest.raises(BudgetExhausted, match="standing cap"),
        open_session(config, campaign="c-2", phase="1") as second,
    ):
        second.reserve("w-2", Cost(usd=1.0), agent="cell-b")
