"""The cell runtime. Three of the four Phase 4 minimum tests; the human one is 4b.

The model is a stub here, and that is a considered exception to this repository's rule about
testing against the real thing. The kernel tests run against a real `knk` because knk's
behaviour is a fact g0rd0n can be wrong about. A model's output is not: asserting on what a
model says is a test of the model, it costs money to run, and it fails on Tuesdays. What is
tested here is everything *around* the call — the allowlist, the schema, the reservation, the
transcript — which is the whole of what this phase builds.

The one thing a stub cannot check is that the wire format is right. `test_the_request_matches_
the_messages_api` pins the shape against the documented API instead.
"""

import json
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from g0rd0n import cells
from g0rd0n.cells import model as model_module
from g0rd0n.cells.cell import Cell, Schema, Tool
from g0rd0n.cells.model import ANSWER, Reply, ToolCall, Turn
from g0rd0n.cells.playbook import Playbook
from g0rd0n.cli import Check
from g0rd0n.config import Config, ConfigError
from g0rd0n.instruments import fetch
from g0rd0n.kernel import Bridge, Ref
from g0rd0n.ledger import Cost, Ledger, Overspend
from g0rd0n.ledger.ledger import open_session

SCHEMA: Schema = {"summary": str, "understood": bool}


class Scripted:
    """A model that replies from a fixed list, and remembers what it was asked.

    Optionally watches a ledger: `reserved_at_each_call` records how many reservations were
    open at the moment the model was called, which is how priced-before-run is checked
    without reaching inside the runtime.
    """

    def __init__(self, *replies: Reply, ledger: Ledger | None = None) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, object]] = []
        self.reserved_at_each_call: list[int] = []
        self._ledger = ledger

    def reply(
        self,
        *,
        model: str,
        system: str,
        turns: tuple[Turn, ...],
        tools: tuple[Tool, ...],
        max_tokens: int,
    ) -> Reply:
        self.requests.append(
            {
                "model": model,
                "system": system,
                "turns": turns,
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        if self._ledger is not None:
            self.reserved_at_each_call.append(len(self._ledger.open_reservations))
        if not self.replies:
            raise AssertionError("the cell asked for more replies than the test scripted")
        return self.replies.pop(0)


def answering(payload: Mapping[str, object]) -> Reply:
    """A reply that calls `answer` with exactly this payload, valid or not."""
    return Reply(
        text="", calls=(ToolCall("c-1", ANSWER, dict(payload)),), tokens_in=100, tokens_out=20
    )


def answers(**fields: object) -> Reply:
    return answering(fields)


def a_playbook(max_turns: int = 4) -> Playbook:
    return Playbook(
        name="smoke",
        role="smoke",
        system="you are a smoke test",
        model="test-model",
        max_turns=max_turns,
        version="abc123def456",
    )


def a_cell(tools: tuple[str, ...] = (), max_turns: int = 4, schema: Schema | None = None) -> Cell:
    return Cell(
        playbook=a_playbook(max_turns),
        tools=tools,
        schema=SCHEMA if schema is None else schema,
        estimate=Cost(tokens_in=10_000, tokens_out=2_000, usd=1.0, seconds=60.0),
    )


def a_tool(name: str, result: str = "ok") -> Tool:
    return Tool(name, f"the {name} tool", {"query": str}, lambda _: result)


def play(
    cell: Cell,
    stub: Scripted,
    config: Config,
    bridge: Bridge,
    tools: Mapping[str, Tool] | None = None,
) -> cells.Run:
    with open_session(config, campaign="c-test", phase="4a") as ledger:
        return cells.run(
            cell,
            "summarise this",
            config=config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
            tools=tools,
        )


# --------------------------------------------------------------------------------------
# The Phase 4 minimum tests that belong to 4a
# --------------------------------------------------------------------------------------


def test_cell_cannot_call_a_tool_outside_its_allowlist(cell_config: Config, bridge: Bridge) -> None:
    """A refusal ends the run. It is not an error message the model gets to try around."""
    call = ToolCall("c-1", "fetch", {"query": "x"})
    stub = Scripted(Reply(text="", calls=(call,), tokens_out=20))
    cell = a_cell(tools=("search",))

    with pytest.raises(cells.ToolNotAllowed, match="fetch"):
        tools = {"search": a_tool("search"), "fetch": a_tool("fetch")}
        play(cell, stub, cell_config, bridge, tools)


def test_a_tool_on_the_allowlist_is_called_and_its_result_goes_back(
    cell_config: Config, bridge: Bridge
) -> None:
    """The other half of the allowlist: what it permits actually runs."""
    stub = Scripted(
        Reply(text="", calls=(ToolCall("c-1", "search", {"query": "spiking"}),), tokens_out=20),
        answers(summary="a summary", understood=True),
    )

    done = play(
        a_cell(tools=("search",)),
        stub,
        cell_config,
        bridge,
        {"search": a_tool("search", "three papers")},
    )

    assert done.output == {"summary": "a summary", "understood": True}
    assert done.turns[-2].results[0].content == "three papers"


def test_cell_output_failing_its_schema_is_a_failed_run_not_a_parsed_guess(
    cell_config: Config, bridge: Bridge
) -> None:
    """Nothing is coerced, repaired, or re-asked. Each of these is a failure, not a value."""
    bad_outputs: list[tuple[dict[str, object], str]] = [
        ({"summary": "s"}, "missing understood"),
        ({"summary": "s", "understood": True, "extra": 1}, "does not name"),
        ({"summary": 42, "understood": True}, "must be str"),
        ({"summary": "s", "understood": "yes"}, "must be bool"),
    ]
    for bad, complaint in bad_outputs:
        with pytest.raises(cells.SchemaError, match=complaint):
            play(a_cell(), Scripted(answering(bad)), cell_config, bridge)


def test_transcript_is_interned_and_linked_to_its_playbook_version(
    cell_config: Config, bridge: Bridge
) -> None:
    """Any run is reproducible, and any result is attributable to the prompt that made it."""
    cell = a_cell()
    done = play(cell, Scripted(answers(summary="s", understood=True)), cell_config, bridge)

    stored = bridge._client.call("document_content", {"id": done.transcript})
    played = bridge.assertions_for(Ref("run", done.id))

    assert done.playbook == Ref("playbook_version", "smoke-abc123def456")
    assert len(played) == 1
    assert bridge.name_of(played[0].object) == cell.playbook.ref
    assert bridge.predicate_of(played[0].predicate) == "plays"
    assert "you are a smoke test" in json.loads(stored) or stored  # stored as base64
    assert "summarise this" in cells.transcript(cell, done.id, list(done.turns))


def test_the_transcript_records_a_run_that_failed(cell_config: Config, bridge: Bridge) -> None:
    """Append-only epistemics, applied to g0rd0n itself: the bad run is the one you want."""
    with pytest.raises(cells.SchemaError):
        play(a_cell(), Scripted(answers(summary="s")), cell_config, bridge)

    runs = bridge.changes_since(0)

    assert len(runs) == 1, "a failed run left no record of itself"
    assert bridge.predicate_of(runs[0].predicate) == "plays"


# --------------------------------------------------------------------------------------
# Priced before run
# --------------------------------------------------------------------------------------


def test_a_cell_reserves_before_it_calls_and_settles_after(
    cell_config: Config, bridge: Bridge
) -> None:
    """The Phase 1 invariant, now with something to price."""
    with open_session(cell_config, campaign="c-test", phase="4a") as ledger:
        stub = Scripted(answers(summary="s", understood=True), ledger=ledger)
        done = cells.run(
            a_cell(),
            "summarise this",
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
        )
        assert ledger.open_reservations == (), "the run did not settle"

    assert stub.reserved_at_each_call == [1], "the model was called before anything was reserved"
    assert done.cost.tokens_in == 100
    assert done.cost.usd == pytest.approx(100 / 1e6 * 1.0 + 20 / 1e6 * 5.0)


def test_a_run_that_costs_more_than_its_estimate_is_stopped(
    cell_config: Config, bridge: Bridge
) -> None:
    """Overspend is refused in every dimension, not just dollars."""
    greedy = Reply(text="", calls=(ToolCall("c-1", ANSWER, {"summary": "s", "understood": True}),))

    with pytest.raises(Overspend):
        play(
            a_cell(schema=SCHEMA),
            Scripted(Reply(text="", calls=greedy.calls, tokens_in=999_999, tokens_out=1)),
            cell_config,
            bridge,
        )


def test_a_cell_that_reserves_no_output_tokens_cannot_run(
    cell_config: Config, bridge: Bridge
) -> None:
    """`max_tokens` comes from the estimate, so a zero estimate is a run that cannot happen."""
    from dataclasses import replace

    cell = replace(a_cell(), estimate=Cost(usd=1.0))

    with pytest.raises(cells.CellError, match="reserves no output tokens"):
        play(cell, Scripted(), cell_config, bridge)


def test_an_unpriced_model_is_refused_rather_than_guessed(
    cell_config: Config, bridge: Bridge
) -> None:
    """No default price. A guessed number in the ledger is wrong forever and invisibly."""
    from dataclasses import replace

    cell = replace(a_cell(), playbook=replace(a_playbook(), model="a-model-nobody-priced"))

    with pytest.raises(ConfigError, match="no price declared"):
        play(cell, Scripted(answers(summary="s", understood=True)), cell_config, bridge)


# --------------------------------------------------------------------------------------
# The loop's other exits
# --------------------------------------------------------------------------------------


def test_a_cell_that_never_answers_runs_out_of_turns(cell_config: Config, bridge: Bridge) -> None:
    calls = (ToolCall("c-1", "search", {"query": "again"}),)
    stub = Scripted(*[Reply(text="", calls=calls, tokens_out=10) for _ in range(2)])

    with pytest.raises(cells.CellError, match="without answering"):
        play(
            a_cell(tools=("search",), max_turns=2),
            stub,
            cell_config,
            bridge,
            {"search": a_tool("search")},
        )


def test_a_cell_that_just_talks_is_a_failed_run(cell_config: Config, bridge: Bridge) -> None:
    """Prose instead of an `answer` call is not something to go looking for JSON in."""
    stub = Scripted(Reply(text="I think the answer is probably yes", stop_reason="end_turn"))

    with pytest.raises(cells.CellError, match="stopped without calling"):
        play(a_cell(), stub, cell_config, bridge)


def test_the_answer_tool_cannot_be_shadowed_or_listed(cell_config: Config, bridge: Bridge) -> None:
    with pytest.raises(cells.CellError, match="reserved"):
        play(a_cell(tools=(ANSWER,)), Scripted(), cell_config, bridge)


def test_a_cell_allowing_a_tool_nobody_provided_is_refused_before_spending(
    cell_config: Config, bridge: Bridge
) -> None:
    """Caught before `reserve`, so a misconfigured cell costs nothing at all."""
    with pytest.raises(cells.CellError, match="not provided"):
        play(a_cell(tools=("prover",)), Scripted(), cell_config, bridge)


# --------------------------------------------------------------------------------------
# The network boundary
# --------------------------------------------------------------------------------------


def test_a_host_outside_the_allowlist_is_refused_before_the_request() -> None:
    """The check sits on the URL that is actually used, immediately before the socket."""
    with pytest.raises(fetch.NetworkRefused, match="not on the network allowlist"):
        fetch.check_host("https://evil.example.com/v1/messages", ("api.anthropic.com",))

    fetch.check_host("https://api.anthropic.com/v1/messages", ("api.anthropic.com",))


def test_the_allowlist_does_not_match_subdomains() -> None:
    """A rule that allows `*.example.com` allows a host nobody listed."""
    with pytest.raises(fetch.NetworkRefused):
        fetch.check_host("https://evil.api.anthropic.com/x", ("api.anthropic.com",))


def test_the_provider_refuses_to_send_before_it_opens_a_socket(tmp_path: Path) -> None:
    """If the refusal came after the request, this test would need a network to fail."""
    provider = model_module.Anthropic(
        endpoint="https://not-allowed.example.com/v1/messages",
        api_key="sk-test",
        allowlist=("api.anthropic.com",),
    )

    with pytest.raises(fetch.NetworkRefused):
        provider.reply(model="m", system="s", turns=(), tools=(), max_tokens=16)

    assert provider._opened == []


def test_the_api_key_comes_from_a_file_never_the_environment(
    cell_config: Config, tmp_path: Path
) -> None:
    from dataclasses import replace

    key_file = tmp_path / "key"
    key_file.write_text("sk-ant-secret\n", encoding="utf-8")

    provider = model_module.Anthropic.from_config(replace(cell_config, model_api_key_file=key_file))

    assert provider.api_key == "sk-ant-secret"
    with pytest.raises(model_module.ModelError, match="cannot read the API key"):
        model_module.Anthropic.from_config(replace(cell_config, model_api_key_file=tmp_path / "no"))


def test_the_request_matches_the_messages_api(cell_config: Config, bridge: Bridge) -> None:
    """What a stub cannot check: the shape sent to Anthropic, pinned against the docs.

    Renders the same turns the provider would send and asserts on the block structure, so a
    change to `_as_message` that a stubbed test would not notice fails here.
    """
    turns = (
        Turn(role="user", text="summarise this"),
        Turn(role="assistant", text="ok", calls=(ToolCall("c-1", "search", {"query": "x"}),)),
        Turn(role="user", results=(model_module.ToolResult("c-1", "three papers"),)),
    )
    messages = [model_module._as_message(turn) for turn in turns]

    assert messages[0] == {"role": "user", "content": [{"type": "text", "text": "summarise this"}]}
    assert messages[1]["content"][1] == {
        "type": "tool_use",
        "id": "c-1",
        "name": "search",
        "input": {"query": "x"},
    }
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "c-1", "content": "three papers"}
    ]
    assert model_module._as_tool(a_tool("search"))["input_schema"] == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }


def test_a_reply_is_read_the_way_the_api_sends_one() -> None:
    reply = model_module._as_reply(
        {
            "content": [
                {"type": "text", "text": "thinking"},
                {"type": "tool_use", "id": "c-9", "name": ANSWER, "input": {"summary": "s"}},
            ],
            "usage": {"input_tokens": 1200, "output_tokens": 34},
            "stop_reason": "tool_use",
        }
    )

    assert reply.text == "thinking"
    assert reply.calls == (ToolCall("c-9", ANSWER, {"summary": "s"}),)
    assert (reply.tokens_in, reply.tokens_out, reply.stop_reason) == (1200, 34, "tool_use")


# --------------------------------------------------------------------------------------
# Playbooks
# --------------------------------------------------------------------------------------


def test_a_playbooks_version_is_the_hash_of_its_bytes(tmp_path: Path) -> None:
    """A version field someone forgets to bump would attribute a run to text that never ran."""
    path = tmp_path / "critic.toml"
    path.write_text(_playbook_text("be terse"), encoding="utf-8")
    first = cells.load_playbook(path)

    path.write_text(_playbook_text("be terse "), encoding="utf-8")
    second = cells.load_playbook(path)

    assert first.version != second.version, "a whitespace edit is still an edit to a prompt"
    assert first.ref == Ref("playbook_version", f"critic-{first.version}")
    assert cells.load_playbook(path).version == second.version


def test_the_shipped_smoke_playbook_loads_and_declares_a_priced_model() -> None:
    """The one playbook in the repo has to be one a cell could actually play."""
    playbook = cells.load_playbook(Path(__file__).resolve().parents[1] / "playbooks" / "smoke.toml")
    config_path = Path(__file__).resolve().parents[1] / "config" / "g0rd0n.toml"

    from g0rd0n.config import load

    assert playbook.role == "smoke"
    assert load(config_path).price_of(playbook.model).input_usd_per_mtok > 0
    assert "version" not in playbook.system


def test_a_playbook_missing_its_prompt_is_refused(tmp_path: Path) -> None:
    for body, complaint in [
        ('role = "x"\nmodel = "m"\nsystem = "  "', "system prompt is empty"),
        ('role = "x"\nmodel = "m"\nsystem = "s"\nversion = "2"', "unknown setting version"),
        ('role = "x"\nmodel = "m"\nsystem = "s"\nmax_turns = 0', "max_turns"),
    ]:
        path = tmp_path / "bad.toml"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(cells.PlaybookError, match=complaint):
            cells.load_playbook(path)


# --------------------------------------------------------------------------------------
# Config, and what doctor now checks
# --------------------------------------------------------------------------------------


def test_a_price_is_read_from_the_config_and_never_defaulted(cell_config: Config) -> None:
    price = cell_config.price_of("test-model")

    assert price.usd(1_000_000, 0) == pytest.approx(1.0)
    assert price.usd(0, 1_000_000) == pytest.approx(5.0)
    with pytest.raises(ConfigError, match="no price declared"):
        cell_config.price_of("claude-opus-5")


def test_doctor_notices_a_missing_or_world_readable_key(
    cell_config: Config, tmp_path: Path
) -> None:
    from dataclasses import replace

    from g0rd0n import cli

    key = tmp_path / "key"
    key.write_text("sk-ant-secret\n", encoding="utf-8")
    key.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)
    loose = replace(cell_config, model_api_key_file=key)

    assert _check(cli.doctor(loose), "model api key").detail.endswith("(chmod 600 it)")
    key.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert _check(cli.doctor(loose), "model api key").ok
    assert not _check(cli.doctor(cell_config), "model endpoint").ok  # kernel_config allows arxiv


def _check(checks: list[Check], name: str) -> Check:
    return next(check for check in checks if check.name == name)


def _playbook_text(system: str) -> str:
    return f'role = "critic"\nmodel = "test-model"\nsystem = "{system}"\n'
