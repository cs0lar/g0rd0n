"""Hash-chained storage for frozen methods and their exact executions."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from g0rd0n.research.ledger import GENESIS_HASH, IntegrityError, canonical_json, content_hash

from .models import (
    ApprovalRecord,
    ExecutionReceipt,
    ExecutionStatus,
    FrozenMethod,
    MethodEvent,
    MethodEventKind,
    MethodProtocol,
    SupersessionRecord,
    approval_from_dict,
    frozen_from_dict,
    receipt_from_dict,
    supersession_from_dict,
)


def artifact_tree_hash(root: Path) -> str:
    """Hash the paths and bytes of a self-contained executable artifact tree."""
    if not root.is_dir():
        raise ValueError("artifact root must be a directory")
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("artifact tree cannot contain symbolic links")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        entries.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not entries:
        raise ValueError("artifact tree must contain at least one file")
    return content_hash({"files": entries})


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _event(sequence: int, kind: MethodEventKind, payload: Mapping[str, Any], previous_hash: str) -> MethodEvent:
    normalized_payload = json.loads(canonical_json(payload))
    unsigned = {"sequence": sequence, "kind": kind, "payload": normalized_payload, "previous_hash": previous_hash}
    return MethodEvent(sequence, kind, normalized_payload, previous_hash, content_hash(unsigned))


class MethodJournal:
    """Append-only protocol state reconstructed entirely from its event log."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self._events: list[MethodEvent] = []
        self._methods: dict[str, FrozenMethod] = {}
        self._approvals: dict[str, ApprovalRecord] = {}
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._supersessions: dict[str, SupersessionRecord] = {}
        self._read()

    def events(self) -> tuple[MethodEvent, ...]:
        return tuple(self._events)

    def method(self, method_id: str) -> FrozenMethod:
        return self._methods[method_id]

    def approval(self, approval_id: str) -> ApprovalRecord:
        return self._approvals[approval_id]

    def receipt(self, receipt_id: str) -> ExecutionReceipt:
        return self._receipts[receipt_id]

    def supersession(self, method_id: str) -> SupersessionRecord | None:
        return self._supersessions.get(method_id)

    def freeze(self, protocol: MethodProtocol, *, actor: str, frozen_at: datetime) -> FrozenMethod:
        frozen = FrozenMethod(protocol, content_hash(protocol.to_dict()), frozen_at, actor.strip())
        if not frozen.frozen_by or frozen.frozen_at.tzinfo is None:
            raise ValueError("freeze requires an actor and timezone-aware timestamp")
        self._append(
            MethodEventKind.FROZEN,
            {
                "protocol": protocol.to_dict(),
                "protocol_hash": frozen.protocol_hash,
                "frozen_at": frozen.frozen_at,
                "frozen_by": frozen.frozen_by,
            },
        )
        return frozen

    def approve(
        self,
        method_id: str,
        artifact_root: Path,
        *,
        approval_id: str,
        reviewer: str,
        policy_version: str,
        approved_at: datetime,
    ) -> ApprovalRecord:
        frozen = self._methods.get(method_id)
        if frozen is None:
            raise ValueError("cannot approve an unfrozen method")
        if method_id in self._supersessions:
            raise ValueError("cannot approve a superseded method")
        approval = ApprovalRecord(
            approval_id.strip(), method_id, reviewer.strip(), policy_version.strip(),
            frozen.protocol_hash, artifact_tree_hash(artifact_root), approved_at,
        )
        if not all((approval.id, approval.reviewer, approval.policy_version)) or approval.approved_at.tzinfo is None:
            raise ValueError("approval requires ids, reviewer, policy version, and timezone-aware timestamp")
        self._append(MethodEventKind.APPROVED, asdict(approval))
        return approval

    def record_execution(
        self,
        method_id: str,
        artifact_root: Path,
        *,
        approval_id: str,
        receipt_id: str,
        result_artifact_hash: str,
        status: ExecutionStatus,
        recorded_at: datetime,
    ) -> ExecutionReceipt:
        frozen = self._methods.get(method_id)
        approval = self._approvals.get(approval_id)
        if frozen is None or approval is None or approval.method_id != method_id:
            raise ValueError("execution requires an approval for this frozen method")
        if method_id in self._supersessions:
            raise ValueError("cannot execute a superseded method")
        code_hash = artifact_tree_hash(artifact_root)
        if approval.protocol_hash != frozen.protocol_hash or approval.code_hash != code_hash:
            raise ValueError("execution artifact does not match exact approval")
        receipt = ExecutionReceipt(
            receipt_id.strip(), method_id, approval_id, frozen.protocol_hash, code_hash,
            result_artifact_hash.strip(), status, recorded_at,
        )
        if not receipt.id or not _is_digest(receipt.result_artifact_hash) or receipt.recorded_at.tzinfo is None:
            raise ValueError("receipt requires ids, lowercase SHA-256 result hash, and timezone-aware timestamp")
        self._append(MethodEventKind.EXECUTION_RECORDED, asdict(receipt))
        return receipt

    def supersede(
        self,
        prior_method_id: str,
        replacement_method_id: str,
        *,
        actor: str,
        reason: str,
        superseded_at: datetime,
    ) -> SupersessionRecord:
        if prior_method_id not in self._methods or replacement_method_id not in self._methods:
            raise ValueError("both prior and replacement methods must be frozen")
        record = SupersessionRecord(
            prior_method_id, replacement_method_id, actor.strip(), reason.strip(), superseded_at
        )
        if prior_method_id == replacement_method_id or not record.actor or not record.reason or record.superseded_at.tzinfo is None:
            raise ValueError("supersession requires distinct methods, actor, reason, and timezone-aware timestamp")
        self._append(MethodEventKind.SUPERSEDED, asdict(record))
        return record

    def _append(self, kind: MethodEventKind, payload: Mapping[str, Any]) -> None:
        previous = self._events[-1].event_hash if self._events else GENESIS_HASH
        event = _event(len(self._events), kind, payload, previous)
        snapshot = (
            self._methods.copy(),
            self._approvals.copy(),
            self._receipts.copy(),
            self._supersessions.copy(),
        )
        self._apply(event)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND)
            try:
                content = memoryview(canonical_json(asdict(event)) + b"\n")
                while content:
                    written = os.write(descriptor, content)
                    if written == 0:
                        raise OSError("method journal write made no progress")
                    content = content[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except BaseException:
            self._methods, self._approvals, self._receipts, self._supersessions = snapshot
            raise
        self._events.append(event)

    def _apply(self, event: MethodEvent) -> None:
        if event.kind is MethodEventKind.FROZEN:
            frozen = frozen_from_dict(event.payload)
            if frozen.protocol.id in self._methods:
                raise IntegrityError("method id was frozen more than once")
            if frozen.protocol_hash != content_hash(frozen.protocol.to_dict()):
                raise IntegrityError("frozen protocol hash mismatch")
            self._methods[frozen.protocol.id] = frozen
        elif event.kind is MethodEventKind.APPROVED:
            approval = approval_from_dict(event.payload)
            frozen = self._methods.get(approval.method_id)
            if approval.id in self._approvals or frozen is None or approval.method_id in self._supersessions:
                raise IntegrityError("invalid or duplicate method approval")
            if approval.protocol_hash != frozen.protocol_hash or not _is_digest(approval.code_hash):
                raise IntegrityError("approval protocol hash mismatch")
            self._approvals[approval.id] = approval
        elif event.kind is MethodEventKind.EXECUTION_RECORDED:
            receipt = receipt_from_dict(event.payload)
            approval = self._approvals.get(receipt.approval_id)
            if receipt.id in self._receipts or approval is None or receipt.method_id in self._supersessions:
                raise IntegrityError("invalid or duplicate execution receipt")
            if not _is_digest(receipt.result_artifact_hash):
                raise IntegrityError("execution receipt result hash is invalid")
            if (receipt.method_id, receipt.protocol_hash, receipt.code_hash) != (
                approval.method_id, approval.protocol_hash, approval.code_hash
            ):
                raise IntegrityError("execution receipt does not match approval")
            self._receipts[receipt.id] = receipt
        else:
            record = supersession_from_dict(event.payload)
            if record.prior_method_id in self._supersessions or record.prior_method_id not in self._methods or record.replacement_method_id not in self._methods:
                raise IntegrityError("invalid method supersession")
            if record.prior_method_id == record.replacement_method_id:
                raise IntegrityError("method cannot supersede itself")
            self._supersessions[record.prior_method_id] = record

    def _read(self) -> None:
        previous = GENESIS_HASH
        with self.path.open(encoding="utf-8") as stream:
            for sequence, line in enumerate(stream):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete method event at line {sequence + 1}")
                try:
                    value = json.loads(line)
                    event = MethodEvent(
                        int(value["sequence"]), MethodEventKind(value["kind"]), dict(value["payload"]),
                        str(value["previous_hash"]), str(value["event_hash"]),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise IntegrityError(f"invalid method event at line {sequence + 1}") from error
                expected = _event(sequence, event.kind, event.payload, previous)
                if event != expected:
                    raise IntegrityError("method event sequence or hash chain is invalid")
                self._apply(event)
                self._events.append(event)
                previous = event.event_hash
