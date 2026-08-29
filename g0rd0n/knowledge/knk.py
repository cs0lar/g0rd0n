"""KnowledgeStore adapter over knk's supported stdio MCP tool surface."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .contract import (
    AssertionRecord,
    AssertionStatus,
    Conflict,
    ProvenanceRecord,
    Query,
    WriteContext,
)


class KnkError(RuntimeError):
    pass


class ToolClient(Protocol):
    def call(self, name: str, arguments: Mapping[str, Any]) -> Any: ...


class KnkMcpClient:
    """Minimal persistent JSON-RPC client for knk's local MCP subprocess."""

    def __init__(self, binary: Path, storage_root: Path) -> None:
        if not binary.is_absolute() or not storage_root.is_absolute():
            raise ValueError("knk binary and storage_root must be absolute paths")
        self._process = subprocess.Popen(
            [str(binary), str(storage_root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._lock = threading.Lock()
        self._next_id = 1
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "g0rd0n", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def _request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            response = self._read()
        if response.get("id") != request_id:
            raise KnkError("knk returned a mismatched JSON-RPC id")
        if "error" in response:
            raise KnkError(str(response["error"]))
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise KnkError("knk returned a malformed JSON-RPC result")
        return result

    def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        with self._lock:
            self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: Mapping[str, Any]) -> None:
        if self._process.stdin is None or self._process.poll() is not None:
            raise KnkError("knk MCP process is not running")
        self._process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    def _read(self) -> Mapping[str, Any]:
        if self._process.stdout is None:
            raise KnkError("knk MCP stdout is unavailable")
        line = self._process.stdout.readline()
        if not line:
            raise KnkError("knk MCP process closed stdout")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise KnkError("knk returned invalid JSON") from error
        if not isinstance(response, Mapping):
            raise KnkError("knk returned a non-object response")
        return response

    def call(self, name: str, arguments: Mapping[str, Any]) -> Any:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")
        if result.get("isError") is True:
            message = content[0].get("text", "unknown knk tool error") if isinstance(content, list) and content else "unknown knk tool error"
            raise KnkError(str(message))
        if not isinstance(content, list) or not content or not isinstance(content[0], Mapping):
            raise KnkError("knk tool returned malformed content")
        text = content[0].get("text")
        if not isinstance(text, str):
            raise KnkError("knk tool returned non-text content")
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise KnkError("knk tool text was not JSON") from error

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

    def __enter__(self) -> "KnkMcpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


_STATUS_FROM_KNK = {
    "Active": AssertionStatus.ACTIVE,
    "Superseded": AssertionStatus.SUPERSEDED,
    "Retracted": AssertionStatus.RETRACTED,
    "Retraction": AssertionStatus.RETRACTION,
}


class KnkKnowledgeStore:
    def __init__(self, client: ToolClient) -> None:
        self._client = client

    def _entity_id(self, name: str) -> int:
        return int(self._client.call("intern_entity", {"name": name}))

    def _find_entity_id(self, name: str) -> int | None:
        value = self._client.call("find_entity", {"name": name})
        return None if value is None else int(value)

    def _find_predicate_id(self, name: str) -> int | None:
        value = self._client.call("find_predicate", {"name": name})
        return None if value is None else int(value)

    def _value_id(self, value: str) -> int:
        return int(self._client.call("intern_value", {"value": {"kind": "text", "value": value}}))

    def _record_provenance(self, assertion_id: int, context: WriteContext) -> None:
        source = self._entity_id(context.source)
        self._client.call(
            "record_provenance",
            {
                "assertion_id": assertion_id,
                "source": source,
                "recorded_at": context.observed_at,
                "method": context.method,
            },
        )

    def _resolve_assertion(self, raw: Mapping[str, Any]) -> AssertionRecord:
        status = _STATUS_FROM_KNK.get(str(raw.get("status")))
        if status is None:
            raise KnkError(f"unsupported knk assertion status: {raw.get('status')}")
        subject = self._client.call("entity_name", {"id": int(raw["subject"])})
        predicate = self._client.call("predicate_name", {"id": int(raw["predicate"])})
        object_name = self._client.call("entity_name", {"id": int(raw["object"])})
        if not all(isinstance(value, str) for value in (subject, predicate, object_name)):
            raise KnkError("g0rd0n assertions require named entity values")
        return AssertionRecord(
            id=str(raw["id"]),
            subject=subject,
            predicate=predicate,
            object=object_name,
            valid_from=int(raw["valid_from"]),
            valid_to=int(raw["valid_to"]),
            observed_at=int(raw["observed_at"]),
            confidence=float(raw["confidence"]),
            status=status,
            supersedes_id=str(raw["supersedes_id"]) if int(raw.get("supersedes_id", 0)) else None,
            retracts_id=str(raw["retracts_id"]) if int(raw.get("retracts_id", 0)) else None,
        )

    def _get(self, assertion_id: str) -> Mapping[str, Any]:
        raw = self._client.call("get", {"id": int(assertion_id)})
        if not isinstance(raw, Mapping):
            raise KeyError(assertion_id)
        return raw

    def assert_(
        self, subject: str, predicate: str, object: str, context: WriteContext
    ) -> AssertionRecord:
        assertion_id = int(
            self._client.call(
                "commit_by_name",
                {
                    "subject_name": subject,
                    "predicate_name": predicate,
                    "object": {"kind": "text", "value": object},
                    "valid_from": context.valid_from,
                    "valid_to": context.valid_to,
                    "observed_at": context.observed_at,
                    "confidence": context.confidence,
                },
            )
        )
        self._record_provenance(assertion_id, context)
        return self._resolve_assertion(self._get(str(assertion_id)))

    def _replacement_arguments(
        self, target: Mapping[str, Any], object_id: int, context: WriteContext
    ) -> dict[str, Any]:
        return {
            "subject": int(target["subject"]),
            "predicate": int(target["predicate"]),
            "object": object_id,
            "valid_from": context.valid_from,
            "valid_to": context.valid_to,
            "observed_at": context.observed_at,
            "confidence": context.confidence,
        }

    def retract(self, assertion_id: str, context: WriteContext) -> AssertionRecord:
        target = self._get(assertion_id)
        arguments = self._replacement_arguments(target, int(target["object"]), context)
        arguments["retracts_id"] = int(assertion_id)
        new_id = int(self._client.call("commit_retraction", arguments))
        self._record_provenance(new_id, context)
        return self._resolve_assertion(self._get(str(new_id)))

    def supersede(
        self, assertion_id: str, new_object: str, context: WriteContext
    ) -> AssertionRecord:
        target = self._get(assertion_id)
        arguments = self._replacement_arguments(target, self._value_id(new_object), context)
        arguments["supersedes_id"] = int(assertion_id)
        new_id = int(self._client.call("commit_superseding", arguments))
        self._record_provenance(new_id, context)
        return self._resolve_assertion(self._get(str(new_id)))

    def query(self, query: Query) -> tuple[AssertionRecord, ...]:
        subject = self._find_entity_id(query.subject)
        if subject is None:
            return ()
        if query.valid_at is not None and query.known_at is not None:
            raw = self._client.call(
                "valid_at_known_at",
                {"subject": subject, "valid_time": query.valid_at, "observed_time": query.known_at},
            )
        elif query.valid_at is not None:
            raw = self._client.call(
                "valid_at", {"subject": subject, "valid_time": query.valid_at}
            )
        elif query.known_at is not None:
            raw = self._client.call(
                "known_at", {"subject": subject, "observed_time": query.known_at}
            )
        else:
            raw = self._client.call("current_by_name", {"subject_name": query.subject})
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise KnkError("knk query returned a non-list")
        records = tuple(self._resolve_assertion(item) for item in raw)
        return tuple(record for record in records if query.predicate is None or record.predicate == query.predicate)

    def history(self, subject: str, predicate: str) -> tuple[AssertionRecord, ...]:
        subject_id = self._find_entity_id(subject)
        predicate_id = self._find_predicate_id(predicate)
        if subject_id is None or predicate_id is None:
            return ()
        raw = self._client.call(
            "commit_history",
            {"subject": subject_id, "predicate": predicate_id},
        )
        return tuple(self._resolve_assertion(item) for item in raw)

    def provenance(self, assertion_id: str) -> ProvenanceRecord | None:
        raw = self._client.call("provenance_for", {"assertion_id": int(assertion_id)})
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise KnkError("knk provenance result is malformed")
        source = self._client.call("entity_name", {"id": int(raw["source"])})
        if not isinstance(source, str):
            raise KnkError("knk provenance source is not a named entity")
        return ProvenanceRecord(str(raw["assertion_id"]), source, int(raw["recorded_at"]), str(raw["method"]))

    def conflicts(self, subject: str, predicate: str) -> tuple[Conflict, ...]:
        subject_id = self._find_entity_id(subject)
        predicate_id = self._find_predicate_id(predicate)
        if subject_id is None or predicate_id is None:
            return ()
        raw = self._client.call(
            "find_conflicts",
            {"subject": subject_id, "predicate": predicate_id},
        )
        return tuple(Conflict(self._resolve_assertion(pair[0]), self._resolve_assertion(pair[1])) for pair in raw)
