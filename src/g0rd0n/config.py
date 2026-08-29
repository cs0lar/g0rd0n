"""Configuration: the one place a path, a cap, or an allowlist enters the process.

Config is read once, at the edge, from an explicit TOML file, and passed downwards as a
value. Nothing below the CLI consults a file, an environment variable, or a global to find
out how it should behave. That is what lets a test stand up a whole g0rd0n against a
throwaway kernel and a throwaway vault with no ambient state, and it is what makes "these
two runs were configured the same" a checkable statement rather than a hope.

Deletion criterion: this module holds the wager that a run's behaviour is fully determined
by one auditable file. Delete it and every component grows its own way of discovering paths
and caps, which loses the verdict on
`config_is_injected_never_read_from_env_inside_components` and, with it, any claim that two
runs priced the same were configured the same.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """A configuration file is missing, malformed, or says something impossible."""


@dataclass(frozen=True)
class Config:
    """Everything g0rd0n needs to know about where it is and what it may spend.

    Flat on purpose. Nesting these into per-section dataclasses would triple the machinery
    and buy nothing at this size.
    """

    kernel_storage_root: Path
    kernel_mcp_server: Path
    vault_root: Path
    session_usd: float
    campaign_usd: float
    standing_usd: float
    network_allowlist: tuple[str, ...]


#: The closed vocabulary of the config file. A key outside this table is an error, not a
#: silently ignored line: a mistyped budget cap that does nothing is exactly the kind of
#: unnoticed spending decision this project exists to prevent.
KNOWN_KEYS: dict[str, frozenset[str]] = {
    "kernel": frozenset({"storage_root", "mcp_server"}),
    "vault": frozenset({"root"}),
    "budget": frozenset({"session_usd", "campaign_usd", "standing_usd"}),
    "network": frozenset({"allowlist"}),
}


def load(path: Path) -> Config:
    """Read and validate a config file.

    Raises `ConfigError` with a message naming the offending setting. Never returns a
    partially populated `Config`: either the file says everything g0rd0n needs, or nothing
    starts.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    _reject_unknown(raw, path)

    config = Config(
        kernel_storage_root=_path(raw, "kernel", "storage_root"),
        kernel_mcp_server=_path(raw, "kernel", "mcp_server"),
        vault_root=_path(raw, "vault", "root"),
        session_usd=_usd(raw, "budget", "session_usd"),
        campaign_usd=_usd(raw, "budget", "campaign_usd"),
        standing_usd=_usd(raw, "budget", "standing_usd"),
        network_allowlist=_hosts(raw, "network", "allowlist"),
    )
    if not config.session_usd <= config.campaign_usd <= config.standing_usd:
        raise ConfigError(
            "budget caps must nest: session_usd <= campaign_usd <= standing_usd, got "
            f"{config.session_usd} / {config.campaign_usd} / {config.standing_usd}"
        )
    return config


def _reject_unknown(raw: dict[str, Any], path: Path) -> None:
    for section, body in raw.items():
        known = KNOWN_KEYS.get(section)
        if known is None:
            raise ConfigError(f"{path}: unknown section [{section}]")
        if not isinstance(body, dict):
            raise ConfigError(f"{path}: [{section}] must be a table")
        for key in body:
            if key not in known:
                raise ConfigError(f"{path}: unknown setting {section}.{key}")


def _require[T](raw: dict[str, Any], section: str, key: str, kind: type[T], what: str) -> T:
    """Fetch one setting, or raise a `ConfigError` that names it and says what it should be."""
    try:
        value = raw[section][key]
    except KeyError:
        raise ConfigError(f"missing required setting {section}.{key}") from None
    if not isinstance(value, kind):
        raise ConfigError(f"{section}.{key} must be {what}")
    return value


def _path(raw: dict[str, Any], section: str, key: str) -> Path:
    return Path(_require(raw, section, key, str, "a string path")).expanduser()


def _usd(raw: dict[str, Any], section: str, key: str) -> float:
    value = _require(raw, section, key, object, "a number of US dollars")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{section}.{key} must be a number of US dollars")
    if value <= 0:
        raise ConfigError(f"{section}.{key} must be positive, got {value}")
    return float(value)


def _hosts(raw: dict[str, Any], section: str, key: str) -> tuple[str, ...]:
    value = _require(raw, section, key, list, "a list of hostnames")
    hosts: list[str] = []
    for host in value:
        if not isinstance(host, str):
            raise ConfigError(f"{section}.{key} must contain only hostnames, got {host!r}")
        hosts.append(host)
    return tuple(hosts)
