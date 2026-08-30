"""Append-only hash-chained session checkpoints."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from g0rd0n.research.ledger import GENESIS_HASH, IntegrityError, canonical_json, content_hash

from .models import ProgramCost, ProgramState, ProgramStatus


def _state_from(value: Mapping[str, Any]) -> ProgramState:
    return ProgramState(
        str(value["program_id"]),
        str(value["spec_hash"]),
        ProgramStatus(value["status"]),
        int(value["session_number"]),
        tuple(str(item) for item in value["pending_experiment_ids"]),
        tuple(str(item) for item in value["completed_experiment_ids"]),
        tuple(str(item) for item in value["failed_experiment_ids"]),
        tuple((str(item[0]), int(item[1])) for item in value["attempts"]),
        int(value["failure_count"]),
        ProgramCost.from_dict(value["spend"]),
        tuple(str(item) for item in value["observations"]),
        tuple(str(item) for item in value["evidence"]),
        tuple(str(item) for item in value["claims_changed"]),
        tuple(str(item) for item in value["failures"]),
        tuple(str(item) for item in value["unresolved_uncertainty"]),
        str(value["best_next_question"]),
        str(value["reason"]),
    )


@dataclass(frozen=True, slots=True)
class ProgramCheckpoint:
    sequence: int
    event: str
    state: ProgramState
    previous_hash: str
    event_hash: str

    @classmethod
    def create(cls, sequence: int, event: str, state: ProgramState, previous_hash: str) -> "ProgramCheckpoint":
        unsigned = {"sequence": sequence, "event": event, "state": asdict(state), "previous_hash": previous_hash}
        return cls(sequence, event, state, previous_hash, content_hash(unsigned))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "state": asdict(self.state),
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


class ProgramJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self._checkpoints = self._read()

    def checkpoints(self) -> tuple[ProgramCheckpoint, ...]:
        return tuple(self._checkpoints)

    @property
    def state(self) -> ProgramState | None:
        return None if not self._checkpoints else self._checkpoints[-1].state

    def append(self, event: str, state: ProgramState) -> ProgramCheckpoint:
        previous_hash = self._checkpoints[-1].event_hash if self._checkpoints else GENESIS_HASH
        checkpoint = ProgramCheckpoint.create(len(self._checkpoints), event, state, previous_hash)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND)
        try:
            remaining = memoryview(canonical_json(checkpoint.to_dict()) + b"\n")
            while remaining:
                written = os.write(descriptor, remaining)
                if written == 0:
                    raise OSError("program journal write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._checkpoints.append(checkpoint)
        return checkpoint

    def _read(self) -> list[ProgramCheckpoint]:
        checkpoints: list[ProgramCheckpoint] = []
        previous_hash = GENESIS_HASH
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.endswith("\n"):
                    raise IntegrityError(f"incomplete program checkpoint at line {line_number}")
                try:
                    value = json.loads(line)
                    state = _state_from(value["state"])
                    checkpoint = ProgramCheckpoint(int(value["sequence"]), str(value["event"]), state, str(value["previous_hash"]), str(value["event_hash"]))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise IntegrityError(f"invalid program checkpoint at line {line_number}") from error
                expected = ProgramCheckpoint.create(len(checkpoints), checkpoint.event, state, previous_hash)
                if checkpoint != expected:
                    raise IntegrityError("program checkpoint sequence or hash chain is invalid")
                checkpoints.append(checkpoint)
                previous_hash = checkpoint.event_hash
        return checkpoints
