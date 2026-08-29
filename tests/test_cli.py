"""What the three Phase 0 commands do, and what they refuse to do."""

from pathlib import Path

import pytest

from g0rd0n import __version__, cli
from g0rd0n.config import Config


def config_for(tmp_path: Path) -> Config:
    return Config(
        kernel_storage_root=tmp_path / "kernel",
        kernel_mcp_server=tmp_path / "mcp_server",
        vault_root=tmp_path / "vault",
        session_usd=5.0,
        campaign_usd=50.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org",),
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

[budget]
session_usd = 5.0
campaign_usd = 50.0
standing_usd = 500.0

[network]
allowlist = ["arxiv.org"]
""",
        encoding="utf-8",
    )
    return path


def test_doctor_reports_missing_kernel_and_vault_without_crashing(tmp_path: Path) -> None:
    """Phase 0 must be runnable on a machine where nothing has been set up yet."""
    checks = cli.doctor(config_for(tmp_path))

    assert [check.name for check in checks] == ["kernel storage", "knk mcp_server", "vault"]
    assert not any(check.ok for check in checks)
    assert all(check.detail for check in checks), "a failing check must say what to do"


def test_doctor_passes_when_everything_is_where_the_config_says(tmp_path: Path) -> None:
    (tmp_path / "kernel").mkdir()
    (tmp_path / "vault").mkdir()
    server = tmp_path / "mcp_server"
    server.write_text("#!/bin/sh\n", encoding="utf-8")
    server.chmod(0o755)

    assert all(check.ok for check in cli.doctor(config_for(tmp_path)))


def test_doctor_fails_a_kernel_binary_that_is_not_executable(tmp_path: Path) -> None:
    (tmp_path / "kernel").mkdir()
    (tmp_path / "vault").mkdir()
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


def test_the_cli_does_nothing_yet_loudly_and_correctly() -> None:
    """Phase 0's review checklist, as a test. Phase 1 changes this line deliberately."""
    assert set(cli.COMMANDS) == {"version", "doctor", "config"}


def test_no_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2
