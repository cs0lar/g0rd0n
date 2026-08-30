"""What the three Phase 0 commands do, and what they refuse to do."""

from pathlib import Path

import pytest
from test_charter import signed, written

from g0rd0n import __version__, cli
from g0rd0n.cells.playbook import version_of
from g0rd0n.config import Config, load
from g0rd0n.cortex import charter
from g0rd0n.ledger import Cost, open_session


def config_for(tmp_path: Path) -> Config:
    return Config(
        kernel_storage_root=tmp_path / "kernel",
        kernel_mcp_server=tmp_path / "mcp_server",
        vault_root=tmp_path / "vault",
        ledger_journal=tmp_path / "ledger" / "ledger.jsonl",
        session_usd=5.0,
        campaign_usd=50.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org", "api.anthropic.com"),
        model_endpoint="https://api.anthropic.com/v1/messages",
        model_api_key_file=tmp_path / "anthropic-key",
        model_prices=(),
        human_queue=tmp_path / "human-queue",
        charter_path=tmp_path / "CHARTER.md",
        charter_definitions=tmp_path / "definitions.md",
    )


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "g0rd0n.toml"
    path.write_text(
        f"""
[kernel]
storage_root = "{tmp_path / "kernel"}"
mcp_server = "{tmp_path / "mcp_server"}"

[vault]
root = "{tmp_path / "vault"}"

[ledger]
journal = "{tmp_path / "ledger" / "ledger.jsonl"}"

[budget]
session_usd = 5.0
campaign_usd = 50.0
standing_usd = 500.0

[network]
allowlist = ["arxiv.org", "api.anthropic.com"]

[model]
endpoint = "https://api.anthropic.com/v1/messages"
api_key_file = "{tmp_path}/anthropic-key"
prices = [{{ model = "test-model", input_usd_per_mtok = 1.0, output_usd_per_mtok = 5.0 }}]

[human]
queue = "{tmp_path / "human-queue"}"

[charter]
path = "{tmp_path / "CHARTER.md"}"
definitions = "{tmp_path / "definitions.md"}"
""",
        encoding="utf-8",
    )
    return path


def _named(checks: list[cli.Check], name: str) -> cli.Check:
    return next(check for check in checks if check.name == name)


def _set_up(tmp_path: Path) -> None:
    """Everything `doctor` looks for, so a test about one check is not about the others.

    The allowlist in `write_config` carries the endpoint's host, so the network check passes
    and only the thing under test can fail.
    """
    for directory in ("kernel", "vault", "ledger", "human-queue"):
        (tmp_path / directory).mkdir(exist_ok=True)
    key = tmp_path / "anthropic-key"
    key.write_text("sk-ant-test\n", encoding="utf-8")
    key.chmod(0o600)
    _write_charter(tmp_path, sign=True)


def _write_charter(tmp_path: Path, *, sign: bool) -> None:
    """A charter and its definitions, in the two places the config points at."""
    definitions = tmp_path / "definitions.md"
    definitions.write_text(
        f"## Joule\n\nThe SI unit of energy.\n\n{charter.WORKED_EXAMPLE} 20 W for 1 s is 20 J.\n",
        encoding="utf-8",
    )
    text = written(definitions=version_of(definitions.read_bytes()))
    (tmp_path / "CHARTER.md").write_text(signed(text) if sign else text, encoding="utf-8")


def test_doctor_reports_missing_kernel_and_vault_without_crashing(tmp_path: Path) -> None:
    """Phase 0 must be runnable on a machine where nothing has been set up yet."""
    checks = cli.doctor(config_for(tmp_path))

    assert [check.name for check in checks] == [
        "kernel storage",
        "knk mcp_server",
        "vault",
        "ledger",
        "human queue",
        "model api key",
        "model endpoint",
        "charter",
    ]
    on_this_machine = [check for check in checks if check.name != "model endpoint"]

    assert not any(check.ok for check in on_this_machine)
    assert all(check.detail for check in checks), "a failing check must say what to do"
    # The endpoint check reads only the config, so it is the one thing that can pass before
    # anything exists. That is the point of it: a misspelled host is findable without a kernel.
    assert _named(checks, "model endpoint").ok


def test_doctor_passes_when_everything_is_where_the_config_says(tmp_path: Path) -> None:
    _set_up(tmp_path)
    server = tmp_path / "mcp_server"
    server.write_text("#!/bin/sh\n", encoding="utf-8")
    server.chmod(0o755)

    assert all(check.ok for check in cli.doctor(config_for(tmp_path)))


def test_doctor_fails_a_kernel_binary_that_is_not_executable(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "mcp_server").write_text("", encoding="utf-8")

    failed = [check for check in cli.doctor(config_for(tmp_path)) if not check.ok]

    assert [check.name for check in failed] == ["knk mcp_server"]
    assert "not executable" in failed[0].detail


def test_doctor_exits_nonzero_when_something_is_missing(tmp_path: Path) -> None:
    assert cli.main(["--config", str(write_config(tmp_path)), "doctor"]) == 1


def test_an_unreadable_config_is_an_error_message_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", str(tmp_path / "nowhere.toml"), "doctor"]) == 1
    assert "config:" in capsys.readouterr().err


def test_version_prints_the_installed_version_without_a_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`version` must work on a machine with no config file at all."""
    assert cli.main(["--config", str(tmp_path / "nowhere.toml"), "version"]) == 0
    assert capsys.readouterr().out.strip() == f"g0rd0n {__version__}"


def test_config_prints_what_was_actually_loaded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", str(write_config(tmp_path)), "config"]) == 0

    out = capsys.readouterr().out
    assert str(tmp_path / "vault") in out
    assert "arxiv.org" in out
    assert "session 5 / campaign 50 / standing 500" in out


def test_cost_answers_before_anything_has_been_spent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Phase 1's review checklist: one command, answerable before the system has run."""
    assert cli.main(["--config", str(write_config(tmp_path)), "cost"]) == 0
    assert "nothing has been spent" in capsys.readouterr().out.lower()


def test_cost_reports_what_a_session_spent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    with open_session(load(config_path), campaign="c-1", phase="1") as ledger:
        ledger.spend(ledger.reserve("w-001", Cost(usd=2.0), "referee"), Cost(usd=1.25))

    assert cli.main(["--config", str(config_path), "cost"]) == 0

    out = capsys.readouterr().out
    assert "w-001" in out
    assert "$1.250" in out


def test_cost_groups_by_what_it_is_asked_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    with open_session(load(config_path), campaign="c-1", phase="1") as ledger:
        ledger.spend(ledger.reserve("w-001", Cost(usd=2.0), "referee"), Cost(usd=1.25))

    assert cli.main(["--config", str(config_path), "cost", "--by", "agent"]) == 0
    assert "referee" in capsys.readouterr().out


def test_cost_refuses_a_grouping_it_does_not_have() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["cost", "--by", "vibes"])

    assert exit_info.value.code == 2


def test_a_damaged_journal_is_an_error_message_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    journal = load(config_path).ledger_journal
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("{not json\n", encoding="utf-8")

    assert cli.main(["--config", str(config_path), "cost"]) == 1
    assert "ledger:" in capsys.readouterr().err


def test_dry_run_is_accepted_and_changes_nothing_yet(tmp_path: Path) -> None:
    """The flag exists and is honest: no command spends, so today it is a no-op."""
    assert cli.main(["--config", str(write_config(tmp_path)), "--dry-run", "cost"]) == 0


def test_the_cli_surface_is_exactly_what_this_phase_declares() -> None:
    """Phase 0's review checklist, still asked. Each phase widens this line deliberately."""
    assert set(cli.COMMANDS) == {"version", "doctor", "config", "cost", "vault", "charter"}
    assert cli.VAULT_ACTIONS == ("rebuild",)
    assert cli.CHARTER_ACTIONS == ("show", "commit")


def test_doctor_fails_an_unsigned_charter(tmp_path: Path) -> None:
    """AGENTS.md §Phase 5 makes the signature a gate, so `doctor` reports a shut gate as shut."""
    _set_up(tmp_path)
    (tmp_path / "mcp_server").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "mcp_server").chmod(0o755)
    _write_charter(tmp_path, sign=False)

    failed = [check for check in cli.doctor(config_for(tmp_path)) if not check.ok]

    assert [check.name for check in failed] == ["charter"]
    assert "unsigned" in failed[0].detail


def test_charter_show_prints_what_the_question_fixes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    _write_charter(tmp_path, sign=True)

    assert cli.main(["--config", str(config_path), "charter", "show"]) == 0

    out = capsys.readouterr().out
    assert all(f"## {heading}" in out for heading in charter.ELEMENTS)
    assert "signed by A Reviewer" in out


def test_charter_show_says_so_when_nobody_has_signed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    _write_charter(tmp_path, sign=False)

    assert cli.main(["--config", str(config_path), "charter", "show"]) == 0
    assert "UNSIGNED" in capsys.readouterr().out


def test_charter_commit_is_priced_by_nobody_and_dry_run_touches_no_kernel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` answers "would this be accepted?" without a running kernel."""
    config_path = write_config(tmp_path)
    _write_charter(tmp_path, sign=True)

    assert cli.main(["--config", str(config_path), "--dry-run", "charter", "commit"]) == 0
    assert "would commit" in capsys.readouterr().out


def test_a_broken_charter_is_an_error_message_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path)
    _write_charter(tmp_path, sign=True)
    (tmp_path / "CHARTER.md").write_text("# Charter\n\n## Question\n\nWhat?\n", encoding="utf-8")

    assert cli.main(["--config", str(config_path), "charter", "show"]) == 1
    assert "charter:" in capsys.readouterr().err


def test_no_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2
