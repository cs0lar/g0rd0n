"""What the config loader accepts, and what it refuses."""

from pathlib import Path

import pytest

from g0rd0n.config import Config, ConfigError, Price, load

GOOD = """
[kernel]
storage_root = "~/kernel"
mcp_server = "~/knk/build/mcp_server"

[vault]
root = "~/vault"

[ledger]
journal = "~/ledger.jsonl"

[budget]
session_usd = 5.0
campaign_usd = 50.0
standing_usd = 500.0

[network]
allowlist = ["arxiv.org", "api.anthropic.com"]

[model]
endpoint = "https://api.anthropic.com/v1/messages"
api_key_file = "~/anthropic-key"
prices = [{ model = "claude-opus-5", input_usd_per_mtok = 15.0, output_usd_per_mtok = 75.0 }]

[human]
queue = "~/human-queue"
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
        ledger_journal=Path("~/ledger.jsonl").expanduser(),
        session_usd=5.0,
        campaign_usd=50.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org", "api.anthropic.com"),
        model_endpoint="https://api.anthropic.com/v1/messages",
        model_api_key_file=Path("~/anthropic-key").expanduser(),
        model_prices=(Price("claude-opus-5", 15.0, 75.0),),
        human_queue=Path("~/human-queue").expanduser(),
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
    text = GOOD.replace('allowlist = ["arxiv.org", "api.anthropic.com"]', 'allowlist = "arxiv.org"')

    with pytest.raises(ConfigError, match=r"network\.allowlist"):
        load(write(tmp_path, text))


def test_malformed_toml_is_reported_as_config_not_as_a_traceback(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(write(tmp_path, "[kernel\n"))


def test_the_committed_config_loads() -> None:
    """The config in the repo is a real config, not an example that has drifted."""
    committed = Path(__file__).resolve().parents[1] / "config" / "g0rd0n.toml"

    assert load(committed).network_allowlist


def test_a_price_table_is_checked_key_by_key(tmp_path: Path) -> None:
    """The same closed-vocabulary rule as the sections, one level down.

    A mistyped price key that silently does nothing would put a wrong number in every cost
    report derived from it, which is the failure the whole config loader exists to prevent.
    """
    for bad, complaint in [
        ('{ model = "m", input_usd_per_mtok = 1.0, out_usd_per_mtok = 5.0 }', "unknown setting"),
        ('{ model = "m", input_usd_per_mtok = 1.0 }', "missing output_usd_per_mtok"),
        (
            '{ model = "m", input_usd_per_mtok = "free", output_usd_per_mtok = 5.0 }',
            "must be a number",
        ),
        (
            '{ model = "m", input_usd_per_mtok = -1.0, output_usd_per_mtok = 5.0 }',
            "not be negative",
        ),
        ("{ model = 7, input_usd_per_mtok = 1.0, output_usd_per_mtok = 5.0 }", "must be a string"),
    ]:
        original = GOOD[GOOD.index("prices = [") :].strip()
        with pytest.raises(ConfigError, match=complaint):
            load(write(tmp_path, GOOD.replace(original, f"prices = [{bad}]")))


def test_a_model_with_no_declared_price_cannot_be_run(tmp_path: Path) -> None:
    config = load(write(tmp_path, GOOD))

    assert config.price_of("claude-opus-5").usd(1_000_000, 1_000_000) == 90.0
    with pytest.raises(ConfigError, match="no price declared"):
        config.price_of("claude-sonnet-5")
