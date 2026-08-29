"""The cost report: what did this cost, and what did it buy?

Holds `costs_attributed_to_a_wager_sum_to_the_session_total`, a permanent CI invariant that
no later phase may delete (AGENTS.md, Testing Requirements), and the reconciliation that
AGENTS.md's Budget Discipline says a discrepancy in must fail CI.
"""

from pathlib import Path

import pytest

from g0rd0n.config import Config
from g0rd0n.ledger import Cost, open_session, report
from g0rd0n.ledger import journal as journal_module


def config_for(tmp_path: Path) -> Config:
    return Config(
        kernel_storage_root=tmp_path / "kernel",
        kernel_mcp_server=tmp_path / "mcp_server",
        vault_root=tmp_path / "vault",
        ledger_journal=tmp_path / "ledger.jsonl",
        session_usd=50.0,
        campaign_usd=100.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org",),
        model_endpoint="https://api.anthropic.com/v1/messages",
        model_api_key_file=tmp_path / "anthropic-key",
        model_prices=(),
    )


def spent_session(tmp_path: Path) -> Config:
    """Two wagers, two agents, four reservations, and one that settles under its estimate."""
    config = config_for(tmp_path)
    with open_session(config, session="s-1", campaign="c-1", phase="1") as ledger:
        first = ledger.reserve("w-001", Cost(usd=2.0, tokens_in=1000, tokens_out=200), "referee")
        ledger.spend(first, Cost(usd=1.5, tokens_in=800, tokens_out=150))
        ledger.settle(first)

        second = ledger.reserve("w-001", Cost(usd=1.0, tokens_in=500), "searcher")
        ledger.spend(second, Cost(usd=1.0, tokens_in=500))
        ledger.settle(second)

        third = ledger.reserve("w-002", Cost(usd=4.0, tokens_in=2000), "referee")
        ledger.spend(third, Cost(usd=0.25, tokens_in=100))
        ledger.settle(third)

        ledger.reserve("w-002", Cost(usd=1.0), "searcher")
    return config


def rows_for(config: Config, by: str) -> list[report.Row]:
    return report.rows(journal_module.replay(config.ledger_journal).values(), by)


def test_costs_attributed_to_a_wager_sum_to_the_session_total(tmp_path: Path) -> None:
    """Every dollar maps to exactly one claim, so the parts add up to the whole.

    Checked in every dimension, not just dollars, and against the journal rather than
    against another total the report computed — the two must not be able to agree by
    sharing a mistake.
    """
    config = spent_session(tmp_path)
    entries = journal_module.replay(config.ledger_journal).values()

    by_wager = rows_for(config, "wager")
    total = sum((row.spent for row in by_wager), Cost())
    journal_total = sum((entry.spent for entry in entries), Cost())

    assert total == journal_total
    assert total == Cost(usd=2.75, tokens_in=1400, tokens_out=150)
    assert sum(row.reservations for row in by_wager) == 4


def test_the_report_reconciles_with_the_sum_of_all_reservations(tmp_path: Path) -> None:
    """AGENTS.md, Budget Discipline: a discrepancy here fails CI."""
    config = spent_session(tmp_path)
    entries = journal_module.replay(config.ledger_journal).values()

    for by in report.BY:
        rows = rows_for(config, by)
        assert sum((row.reserved for row in rows), Cost()) == sum(
            (entry.estimate for entry in entries), Cost()
        )
        assert sum(row.reservations for row in rows) == len(list(entries))


def test_spend_groups_by_wager(tmp_path: Path) -> None:
    rows = rows_for(spent_session(tmp_path), "wager")

    assert [(row.key, row.spent.usd, row.reservations) for row in rows] == [
        ("w-001", 2.5, 2),
        ("w-002", 0.25, 2),
    ]


def test_spend_groups_by_agent(tmp_path: Path) -> None:
    rows = rows_for(spent_session(tmp_path), "agent")

    assert [(row.key, row.spent.usd) for row in rows] == [("referee", 1.75), ("searcher", 1.0)]


def test_spend_groups_by_phase_and_by_day(tmp_path: Path) -> None:
    config = spent_session(tmp_path)

    assert [row.key for row in rows_for(config, "phase")] == ["1"]
    days = [row.key for row in rows_for(config, "day")]
    assert len(days) == 1 and days[0].count("-") == 2


def test_rows_are_ordered_by_what_they_cost(tmp_path: Path) -> None:
    """The most expensive thing is the first thing read."""
    rows = rows_for(spent_session(tmp_path), "wager")

    assert [row.spent.usd for row in rows] == sorted((row.spent.usd for row in rows), reverse=True)


def test_an_unknown_grouping_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot group by 'vibes'"):
        report.rows([], "vibes")


def test_the_report_answers_before_anything_has_been_spent(tmp_path: Path) -> None:
    """The Phase 1 review checklist: one command, answerable before the system has run."""
    answer = report.read(tmp_path / "never-written.jsonl", "wager")

    assert answer == "Nothing has been reserved yet, so nothing has been spent."


def test_the_rendered_report_totals_what_it_lists(tmp_path: Path) -> None:
    rendered = report.read(spent_session(tmp_path).ledger_journal, "wager")
    lines = rendered.splitlines()

    assert lines[0].startswith("wager")
    assert "w-001" in rendered and "w-002" in rendered
    assert lines[-1].startswith("TOTAL")
    assert "$2.750" in lines[-1]
    assert "1400→150" in lines[-1]
