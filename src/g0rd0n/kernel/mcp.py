"""An MCP stdio client, speaking JSON-RPC 2.0 to `knk`'s `mcp_server` as a subprocess.

This module knows about processes, pipes, and JSON-RPC framing. It does not know what a
predicate is, what provenance means, or what a Wager is — that is `bridge`'s job, and the
layering in AGENTS.md is one-directional for a reason. g0rd0n never links knk's C++ API,
vendors it, or forks it; a missing kernel operation is an issue filed against knk.

knk's server distinguishes two kinds of failure and so does this client: a malformed request
is a JSON-RPC error, while a tool that ran and refused comes back as a *successful* response
carrying `isError: true`. Collapsing those two would hide the difference between "g0rd0n is
broken" and "the kernel said no".

Deletion criterion: this module holds the wager that g0rd0n's memory survives g0rd0n. Delete
it and the kernel is reachable only by linking it, which loses the verdict on
`bridge_survives_kernel_subprocess_restart` and takes the append-only assertion log — the
thing every later phase reads its own history out of — with it.
"""

import json
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "g0rd0n", "version": "0.0.0"}


class KernelError(Exception):
    """The kernel could not be reached, or did not answer in a way g0rd0n can use."""


class KernelUnavailable(KernelError):
    """The subprocess is not running and could not be restarted."""


class KernelProtocolError(KernelError):
    """The server answered with a JSON-RPC error, or with something that is not a response."""


class ToolError(KernelError):
    """The tool ran and refused. The kernel said no, and this is what it said."""


class Client:
    """One `mcp_server` subprocess, and the JSON-RPC conversation with it.

    Restarts the subprocess on demand. The kernel's log is the source of truth and is
    replayed on startup, so a restart costs the time to replay and nothing else — which is
    what makes it safe to treat a dead subprocess as a retryable condition rather than a lost
    session.
    """

    def __init__(self, server: Path, storage_root: Path) -> None:
        self._server = server
        self._storage_root = storage_root
        self._process: subprocess.Popen[str] | None = None
        self._next_id = 0
        self.starts = 0

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def restarts(self) -> int:
        """How many times the subprocess has been replaced. Zero on a session that never died.

        A dead subprocess is usually noticed before the next write rather than during one,
        so this counts spawns rather than failed calls — otherwise a clean reconnect would
        look like no reconnect at all.
        """
        return max(self.starts - 1, 0)

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        """Invoke one kernel tool and return its text payload.

        Retries exactly once against a fresh subprocess. Once, because a kernel that dies on
        the same call twice is telling you something, and retrying past that would turn a
        reproducible crash into a loop.
        """
        try:
            response = self._call_once(tool, arguments)
        except KernelUnavailable:
            self._stop()
            response = self._call_once(tool, arguments)

        content = response.get("content") or []
        text = content[0].get("text", "") if content else ""
        if response.get("isError"):
            raise ToolError(f"{tool}: {text}")
        return str(text)

    def close(self) -> None:
        self._stop()

    def _call_once(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._start_if_needed()
        return self._request("tools/call", {"name": tool, "arguments": arguments})

    def _start_if_needed(self) -> None:
        if self.running:
            return
        self._storage_root.mkdir(parents=True, exist_ok=True)
        try:
            self._process = subprocess.Popen(
                [str(self._server), str(self._storage_root)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise KernelUnavailable(f"cannot start {self._server}: {exc}") from exc

        self.starts += 1

        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._notify("notifications/initialized")

    def _stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        while True:
            message = self._read()
            if message.get("id") != request_id:
                continue  # a notification, or a response nobody is waiting for
            if "error" in message:
                error = message["error"]
                raise KernelProtocolError(
                    f"{method}: {error.get('message', error)} ({error.get('code')})"
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise KernelProtocolError(f"{method}: response has no result object")
            return result

    def _notify(self, method: str) -> None:
        self._write({"jsonrpc": "2.0", "method": method})

    def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise KernelUnavailable("the kernel subprocess is not running")
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise KernelUnavailable(f"the kernel subprocess went away: {exc}") from exc

    def _read(self) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise KernelUnavailable("the kernel subprocess is not running")
        line = process.stdout.readline()
        if not line:
            raise KernelUnavailable("the kernel subprocess closed its output")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise KernelProtocolError(
                f"the kernel wrote something that is not JSON: {exc}"
            ) from exc
        if not isinstance(message, dict):
            raise KernelProtocolError(f"the kernel wrote a {type(message).__name__}, not a message")
        return message


@contextmanager
def connect(server: Path, storage_root: Path) -> Iterator[Client]:
    """Open a client, and close the subprocess whatever happens to the caller."""
    client = Client(server, storage_root)
    try:
        yield client
    finally:
        client.close()
