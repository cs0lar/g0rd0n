"""The model seam, and the one provider behind it.

Two things live here: a neutral description of a conversation (`Turn`, `ToolCall`,
`ToolResult`, `Reply`) that the runtime speaks, and an `Anthropic` provider that translates
it to the Messages API and back.

**Hand-rolled over `urllib`, with no SDK.** Phase 2 did the same for MCP, for the same two
reasons. The first is that a dependency is a thing that changes underneath a record that is
supposed to be reproducible. The second is the one that decides it: AGENTS.md §Phase 4 says
every tool call passes through the network allowlist, and an allowlist enforced somewhere
above an SDK is decoration — the SDK opens the socket, so it decides where the bytes go.
Here the host check sits immediately before the request, on the URL that is actually used.

**No retries.** AGENTS.md §Budget Discipline: rate limits and quotas are costs, not errors to
retry through, because a retry storm is a spending decision made by nobody. A failed call is
a failed run, and the reservation settles with what was actually spent.

The API key is read from a file named in the config, never from the environment. The config
file is the only channel by which anything enters this process, and a key in an environment
variable is exactly the ambient state that makes two runs differ invisibly.

Deletion criterion: this module holds the wager that g0rd0n cannot reach a host nobody
allowed, and cannot spend on a call nobody priced. Delete it and
`a_host_outside_the_allowlist_is_refused_before_the_request` loses its verdict, and the
egress point moves inside a library where no test of ours can see it.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from g0rd0n.cells.cell import Schema, Tool, as_json_schema
from g0rd0n.config import Config

API_VERSION = "2023-06-01"
TIMEOUT_SECONDS = 120


class ModelError(Exception):
    """A model call could not be made, or did not come back usable."""


class NetworkRefused(ModelError):
    """The call would have gone to a host the config does not allow. Nothing was sent."""


class ModelUnavailable(ModelError):
    """The endpoint could not be reached, or answered with an error."""


@dataclass(frozen=True)
class ToolCall:
    """The model asking for an instrument, by name, with arguments."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """What an instrument returned, on its way back to the model."""

    call_id: str
    content: str


@dataclass(frozen=True)
class Turn:
    """One exchange, in a form no provider owns.

    Also the unit the transcript is rendered from, so the record a human reads and the
    messages the model saw are the same list.
    """

    role: str
    text: str = ""
    calls: tuple[ToolCall, ...] = ()
    results: tuple[ToolResult, ...] = ()


@dataclass(frozen=True)
class Reply:
    """What came back: prose, tool requests, and what it cost in tokens."""

    text: str
    calls: tuple[ToolCall, ...] = ()
    tokens_in: int = 0
    tokens_out: int = 0
    stop_reason: str = ""


class Model(Protocol):
    """Anything that can answer a conversation. The seam tests replace.

    Not because a real call is undesirable — the kernel tests deliberately run against a real
    `knk` — but because a model's output is not a fact about g0rd0n. A test asserting on what
    a model says is a test of the model, and it fails on Tuesdays.
    """

    def reply(
        self,
        *,
        model: str,
        system: str,
        turns: tuple[Turn, ...],
        tools: tuple[Tool, ...],
        max_tokens: int,
    ) -> Reply: ...


@dataclass
class Anthropic:
    """The Messages API, over `urllib`, with the allowlist checked on the way out."""

    endpoint: str
    api_key: str
    allowlist: tuple[str, ...]
    _opened: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: Config) -> "Anthropic":
        """Build a provider, reading the key from the file the config names."""
        try:
            key = config.model_api_key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ModelError(
                f"cannot read the API key from {config.model_api_key_file}: {exc}. "
                "Set model.api_key_file in the config to a file containing the key."
            ) from exc
        if not key:
            raise ModelError(f"{config.model_api_key_file} is empty")
        return cls(config.model_endpoint, key, config.network_allowlist)

    def reply(
        self,
        *,
        model: str,
        system: str,
        turns: tuple[Turn, ...],
        tools: tuple[Tool, ...],
        max_tokens: int,
    ) -> Reply:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [_as_message(turn) for turn in turns],
            "tools": [_as_tool(tool) for tool in tools],
        }
        return _as_reply(self._post(body))

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        check_host(self.endpoint, self.allowlist)
        self._opened.append(self.endpoint)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ModelUnavailable(f"{self.endpoint} answered {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"{self.endpoint} did not answer usably: {exc}") from exc
        if not isinstance(payload, dict):
            raise ModelUnavailable(f"{self.endpoint} answered with a {type(payload).__name__}")
        return payload


def check_host(url: str, allowlist: tuple[str, ...]) -> None:
    """Raise `NetworkRefused` unless `url`'s host is on the allowlist. Called before sending.

    Exact hostname match, with no subdomain wildcards: a rule that allows `*.example.com`
    allows a host nobody listed, and this is the boundary where "nobody decided that" is
    most expensive.
    """
    host = urllib.parse.urlparse(url).hostname
    if host is None:
        raise NetworkRefused(f"{url!r} names no host")
    if host not in allowlist:
        allowed = ", ".join(allowlist) or "(nothing)"
        raise NetworkRefused(
            f"{host} is not on the network allowlist, which has {allowed}; nothing was sent"
        )


def _as_message(turn: Turn) -> dict[str, Any]:
    """One `Turn` as the Messages API wants it."""
    blocks: list[dict[str, Any]] = []
    if turn.text:
        blocks.append({"type": "text", "text": turn.text})
    blocks += [
        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        for call in turn.calls
    ]
    blocks += [
        {"type": "tool_result", "tool_use_id": result.call_id, "content": result.content}
        for result in turn.results
    ]
    return {"role": turn.role, "content": blocks}


def _as_tool(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": as_json_schema(tool.parameters),
    }


def _as_reply(payload: dict[str, Any]) -> Reply:
    blocks = payload.get("content") or []
    usage = payload.get("usage") or {}
    return Reply(
        text="".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text"),
        calls=tuple(
            ToolCall(
                id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                arguments=dict(block.get("input") or {}),
            )
            for block in blocks
            if block.get("type") == "tool_use"
        ),
        tokens_in=int(usage.get("input_tokens", 0)),
        tokens_out=int(usage.get("output_tokens", 0)),
        stop_reason=str(payload.get("stop_reason", "")),
    )


def answer_tool(schema: Schema) -> Tool:
    """The one tool every cell has: the way it returns its typed output.

    A cell finishes by *calling* something, rather than by emitting JSON in prose that
    someone has to find and parse. Parsing prose is where a failed run turns into a parsed
    guess, which is the thing AGENTS.md §Phase 4 names as the failure to prevent.
    """

    def refuse(_: Mapping[str, Any]) -> str:  # pragma: no cover - intercepted by name
        raise ModelError("the answer tool is handled by the runtime, not called")

    return Tool(
        name=ANSWER,
        description="Return your final answer. Call this exactly once, when you are done.",
        parameters=schema,
        run=refuse,
    )


#: Reserved tool name. A cell's allowlist never needs to mention it, and never may shadow it.
ANSWER = "answer"
