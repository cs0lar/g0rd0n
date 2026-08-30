"""Shared fixtures, and the one piece of machinery the kernel tests need.

`knk` is a separate repository and a C++ build, so the tests that need a real kernel have to
find one. They are never run against a fake: a bridge verified against a mock is a bridge
verified against what its author believed knk does, which is the failure mode this project
exists to avoid.
"""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from g0rd0n.config import Config, Price
from g0rd0n.kernel import Bridge, connect

#: Where knk is checked out and built on a development machine. CI passes `--knk-mcp-server`
#: explicitly; this default is a convenience, not an assumption.
DEFAULT_SERVER = Path("~/development/c++/knk/build/mcp_server").expanduser()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--knk-mcp-server",
        default=None,
        help=(
            "path to knk's built mcp_server binary. If given and missing, the kernel tests "
            f"fail; if omitted, they are skipped unless {DEFAULT_SERVER} exists."
        ),
    )


@pytest.fixture(scope="session")
def knk_server(request: pytest.FixtureRequest) -> Path:
    """The kernel binary under test.

    An explicitly-given path that does not exist is an error, not a skip: that is CI passing
    the wrong path, and a silently skipped invariant is worse than a red build.
    """
    given = request.config.getoption("--knk-mcp-server")
    if given is not None:
        server = Path(str(given)).expanduser()
        if not server.is_file():
            pytest.fail(f"--knk-mcp-server={server} does not exist")
        return server
    if not DEFAULT_SERVER.is_file():
        pytest.skip(
            f"no knk mcp_server at {DEFAULT_SERVER}; build knk or pass --knk-mcp-server=PATH"
        )
    return DEFAULT_SERVER


@pytest.fixture
def kernel_config(knk_server: Path, tmp_path: Path) -> Config:
    """A config pointing at a throwaway kernel storage root, one per test."""
    return Config(
        kernel_storage_root=tmp_path / "kernel",
        kernel_mcp_server=knk_server,
        vault_root=tmp_path / "vault",
        ledger_journal=tmp_path / "ledger.jsonl",
        session_usd=5.0,
        campaign_usd=50.0,
        standing_usd=500.0,
        network_allowlist=("arxiv.org",),
        model_endpoint="https://api.anthropic.com/v1/messages",
        model_api_key_file=tmp_path / "anthropic-key",
        model_prices=(),
        human_queue=tmp_path / "human-queue",
        charter_path=tmp_path / "CHARTER.md",
        charter_definitions=tmp_path / "definitions.md",
    )


@pytest.fixture
def cell_config(kernel_config: Config) -> Config:
    """A kernel config that also knows what a model costs. Phase 4 onwards."""
    return replace(
        kernel_config,
        model_prices=(Price("test-model", input_usd_per_mtok=1.0, output_usd_per_mtok=5.0),),
    )


@pytest.fixture
def bridge(kernel_config: Config) -> Iterator[Bridge]:
    """A bridge to a fresh kernel, closed when the test ends."""
    with connect(kernel_config) as opened:
        yield opened
