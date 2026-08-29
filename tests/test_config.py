"""What the config loader accepts, and what it refuses."""

from pathlib import Path

import pytest

from g0rd0n.config import Config, ConfigError, load

GOOD = """
[kernel]
storage_root = "~/kernel"
mcp_server = "~/knk/build/mcp_server"

[vault]
root = "~/vault"

[budget]
session_usd = 5.0
campaign_usd = 50.0
standing_usd = 500.0

[network]
allowlist = ["arxiv.org"]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "g0rd0n.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_complete_config_loads_and_expands_paths(tmp_path: Path) -> None:
    config = load(write(tmp_path, GOOD))

    assert config == Config(
        kernel_storage_root=Path("~/kernel").expanduser(),
        kernel_mcp_server=Path("~/knk/build/mcp_server").expanduser(),
        vault_root=Path("~/vault").expanduser(),
        session_usd=5.0,
        campaign_usd=50.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org",),
    )
    assert not str(config.vault_root).startswith("~")


def test_a_missing_config_file_names_itself(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere.toml"

    with pytest.raises(ConfigError, match=r"nowhere\.toml"):
        load(missing)


def test_a_missing_setting_is_named(tmp_path: Path) -> None:
    text = GOOD.replace("standing_usd = 500.0\n", "")

    with pytest.raises(ConfigError, match=r"budget\.standing_usd"):
        load(write(tmp_path, text))


def test_an_unknown_setting_is_rejected_not_ignored(tmp_path: Path) -> None:
    """A mistyped cap that silently does nothing is a spending decision made by nobody."""
    text = GOOD.replace("standing_usd", "standng_usd")

    with pytest.raises(ConfigError, match=r"budget\.standng_usd"):
        load(write(tmp_path, text))


def test_an_unknown_section_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[llm\]"):
        load(write(tmp_path, GOOD + '\n[llm]\nmodel = "whatever"\n'))


def test_a_non_positive_cap_is_rejected(tmp_path: Path) -> None:
    text = GOOD.replace("session_usd = 5.0", "session_usd = 0")

    with pytest.raises(ConfigError, match="session_usd must be positive"):
        load(write(tmp_path, text))


def test_caps_must_nest(tmp_path: Path) -> None:
    """A session cap above the standing cap means one of them is not a cap."""
    text = GOOD.replace("session_usd = 5.0", "session_usd = 5000.0")

    with pytest.raises(ConfigError, match="must nest"):
        load(write(tmp_path, text))


def test_a_setting_of_the_wrong_type_is_rejected(tmp_path: Path) -> None:
    text = GOOD.replace('allowlist = ["arxiv.org"]', 'allowlist = "arxiv.org"')

    with pytest.raises(ConfigError, match=r"network\.allowlist"):
        load(write(tmp_path, text))


def test_malformed_toml_is_reported_as_config_not_as_a_traceback(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(write(tmp_path, "[kernel\n"))


def test_the_committed_config_loads() -> None:
    """The config in the repo is a real config, not an example that has drifted."""
    committed = Path(__file__).resolve().parents[1] / "config" / "g0rd0n.toml"

    assert load(committed).network_allowlist
