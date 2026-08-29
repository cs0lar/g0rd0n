"""The journal: append-only, replayable, and loud when it is damaged."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from g0rd0n.ledger import Cost, JournalError
from g0rd0n.ledger import journal as journal_module


def reserve_record(reservation: str = "r-1", **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "event": "reserve",
        "at": "2026-08-29T10:00:00+00:00",
        "session": "s-1",
        "campaign": "c-1",
        "phase": "1",
        "reservation": reservation,
        "wager": "w-1",
        "agent": "cell-a",
        "estimate": Cost(usd=1.0).as_dict(),
    }
    return record | overrides


def spend_record(usd: float, reservation: str = "r-1") -> dict[str, object]:
    return {
        "event": "spend",
        "at": "2026-08-29T10:01:00+00:00",
        "reservation": reservation,
        "actual": Cost(usd=usd).as_dict(),
    }


def settle_record(usd: float, reservation: str = "r-1") -> dict[str, object]:
    return {
        "event": "settle",
        "at": "2026-08-29T10:02:00+00:00",
        "reservation": reservation,
        "total": Cost(usd=usd).as_dict(),
    }


def test_an_absent_journal_is_an_empty_history_not_an_error(tmp_path: Path) -> None:
    """g0rd0n must be able to report that it has spent nothing before it has spent anything."""
    assert journal_module.replay(tmp_path / "never-written.jsonl") == {}


def test_replay_folds_records_into_one_entry_per_reservation(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, reserve_record())
    journal_module.append(path, spend_record(0.3))
    journal_module.append(path, spend_record(0.2))

    entry = journal_module.replay(path)["r-1"]

    assert entry.spent == Cost(usd=0.5)
    assert not entry.settled
    assert entry.wager_id == "w-1"


def test_an_open_reservation_commits_its_estimate_and_a_settled_one_its_actual(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, reserve_record())
    assert journal_module.replay(path)["r-1"].committed == Cost(usd=1.0)

    journal_module.append(path, settle_record(0.4))
    assert journal_module.replay(path)["r-1"].committed == Cost(usd=0.4)


def test_a_damaged_journal_is_an_error_not_a_shrug(tmp_path: Path) -> None:
    """Skipping a line it cannot parse is how a ledger starts lying."""
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, reserve_record())
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    with pytest.raises(JournalError, match=r"ledger\.jsonl:2 is not valid JSON"):
        journal_module.replay(path)


def test_a_record_that_cannot_be_true_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, spend_record(1.0, reservation="r-ghost"))

    with pytest.raises(JournalError, match="unknown reservation"):
        journal_module.replay(path)


def test_a_reservation_cannot_be_opened_twice(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, reserve_record())
    journal_module.append(path, reserve_record())

    with pytest.raises(JournalError, match="opened twice"):
        journal_module.replay(path)


def test_an_event_the_journal_does_not_recognise_is_refused(tmp_path: Path) -> None:
    with pytest.raises(JournalError, match="not a journal event"):
        journal_module.append(tmp_path / "ledger.jsonl", {"event": "refund", "reservation": "r-1"})


def test_the_journal_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    journal_module.append(path, reserve_record("r-1"))
    first = path.read_text(encoding="utf-8")
    journal_module.append(path, reserve_record("r-2"))

    assert path.read_text(encoding="utf-8").startswith(first)


def test_the_journal_creates_its_directory(tmp_path: Path) -> None:
    path = tmp_path / "not" / "yet" / "ledger.jsonl"
    journal_module.append(path, reserve_record())

    assert json.loads(path.read_text(encoding="utf-8"))["wager"] == "w-1"


def test_timestamps_are_utc() -> None:
    """A journal in local time is a journal that lies twice a year."""
    assert journal_module.now().utcoffset() == timedelta(0)
