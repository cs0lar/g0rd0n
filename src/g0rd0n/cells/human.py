"""Human cells: a person as an instrument, with the same accounting as a model.

AGENTS.md §Phase 4: a `HumanQuery` is a Cell whose instrument is a person, with a price in
wall-clock, a deadline, and a fallback if the deadline passes. "Humans are resources in the
network with the same accounting as models" is the load-bearing sentence, and it is why this
module returns the same `Run` a cell does, reserves before it asks, and links its transcript
with `plays` to the exact wording of the question.

**A question is a prompt, so it is versioned like one** — the hash of its own bytes. Reword
the question and you are asking something else; a person's answer stays attributed to what
they were actually asked.

**The deadline is the only thing the fallback covers.** A person who answers with the wrong
shape is a failed run, exactly as a model would be. Quietly substituting the fallback would
record "we assumed this because nobody replied" over the top of someone who did reply, which
is the specific self-deception this project exists to prevent. Falling back is recorded on
the `Run` itself, because a graph running downstream of a fallback is running on an
assumption rather than an answer.

The fallback is checked against the schema **before anything is reserved**, so a fallback that
could never be used is a configuration error found in the first millisecond rather than at
the deadline, an hour later, with the question already asked.

Deletion criterion: this module holds the wager that waiting for a person is priced, bounded,
and recorded like any other call. Delete it and `human_query_times_out_to_its_declared_
fallback` loses its verdict, a human in the loop becomes an unbounded wait nobody budgeted,
and the difference between "a person said so" and "nobody answered" stops being in the record.
"""

import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from g0rd0n.cells.cell import CellError, Schema, check_output
from g0rd0n.cells.model import Turn
from g0rd0n.cells.runtime import Run, RunId, record
from g0rd0n.content import version_of
from g0rd0n.kernel import Bridge, Ref
from g0rd0n.ledger import Cost, Ledger

#: How often a file-drop asker looks for an answer. Short enough that a person is not kept
#: waiting by the poll, long enough that an hour-long deadline is not a spin loop.
POLL_SECONDS = 0.5


class HumanError(CellError):
    """A human query could not be asked, or was answered in a way its schema does not admit."""


@dataclass(frozen=True)
class HumanQuery:
    """A question put to a person, priced in wall-clock and bounded by a deadline."""

    role: str
    question: str
    schema: Schema
    deadline_seconds: float
    fallback: Mapping[str, Any]
    estimate: Cost

    @property
    def version(self) -> str:
        return version_of(self.question.encode("utf-8"))

    @property
    def ref(self) -> Ref:
        """The prompt this run played, in the same namespace a playbook uses."""
        return Ref("playbook_version", f"{self.role}-{self.version}")


class Asker(Protocol):
    """Whatever puts a question to a person. Returns `None` if the deadline passed."""

    def ask(self, query: HumanQuery, run_id: RunId) -> Mapping[str, Any] | None: ...


@dataclass
class FileDrop:
    """Ask by writing a question into a directory and waiting for an answer beside it.

    A file rather than a console prompt, because g0rd0n runs unattended and a person is not a
    blocking `input()`: the question survives the asker, can be answered from another machine
    or another day, and leaves both halves on disk where a human can see what was asked.

    Writes `<run_id>.question.json`; waits for `<run_id>.answer.json`.
    """

    queue: Path
    poll_seconds: float = POLL_SECONDS

    def ask(self, query: HumanQuery, run_id: RunId) -> Mapping[str, Any] | None:
        self.queue.mkdir(parents=True, exist_ok=True)
        question = self.queue / f"{run_id}.question.json"
        answer = self.queue / f"{run_id}.answer.json"
        question.write_text(
            json.dumps(
                {
                    "run": run_id,
                    "role": query.role,
                    "question": query.question,
                    "answer_with": {field: kind.__name__ for field, kind in query.schema.items()},
                    "deadline_seconds": query.deadline_seconds,
                    "write_your_answer_to": answer.name,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        deadline = time.monotonic() + query.deadline_seconds
        while time.monotonic() < deadline:
            if answer.is_file():
                return _read_answer(answer)
            time.sleep(min(self.poll_seconds, max(deadline - time.monotonic(), 0.0)))
        return _read_answer(answer) if answer.is_file() else None


def ask(
    query: HumanQuery,
    *,
    ledger: Ledger,
    bridge: Bridge,
    asker: Asker,
    wager_id: str,
    run_id: RunId | None = None,
) -> Run:
    """Put a question to a person, and return what came back — or the declared fallback.

    Same shape as `runtime.run`, and for the same reason: reserve before asking, record
    whatever happened, settle on the way out however it ended.
    """
    check_output(query.fallback, query.schema)  # before anything is reserved
    if query.deadline_seconds <= 0:
        raise HumanError(f"{query.role}: a deadline of {query.deadline_seconds}s asks nobody")

    identifier = run_id or f"run-{uuid.uuid4().hex[:12]}"
    reservation = ledger.reserve(wager_id, query.estimate, query.role)
    turns = [Turn(role="user", text=query.question)]
    failure: Exception | None = None
    output: dict[str, Any] = {}
    fell_back = False
    started = time.monotonic()

    try:
        answered = asker.ask(query, identifier)
        fell_back = answered is None
        output = dict(query.fallback) if answered is None else check_output(answered, query.schema)
    except Exception as exc:  # recorded, settled, then re-raised unchanged
        failure = exc

    waited = Cost(seconds=time.monotonic() - started, human_seconds=time.monotonic() - started)
    turns.append(Turn(role="assistant", text=_answer_text(output, fell_back, failure)))
    try:
        ledger.spend(reservation, waited)
        document = record(bridge, query.ref, identifier, transcript(query, identifier, turns))
    finally:
        ledger.settle(reservation)

    if failure is not None:
        raise failure
    return Run(
        id=identifier,
        role=query.role,
        output=output,
        cost=waited,
        transcript=document,
        playbook=query.ref,
        turns=tuple(turns),
        fell_back=fell_back,
    )


def transcript(query: HumanQuery, identifier: RunId, turns: list[Turn]) -> str:
    """What was asked of whom, and what came back. No wall-clock, as with a cell's."""
    lines = [
        f"run: {identifier}",
        f"role: {query.role}",
        f"playbook: {query.ref}",
        "model: (a person)",
        f"deadline_seconds: {query.deadline_seconds}",
        "",
        "=== question ===",
        query.question,
    ]
    for turn in turns[1:]:
        lines += ["", f"=== {turn.role} ===", turn.text]
    return "\n".join(lines) + "\n"


def _answer_text(output: Mapping[str, Any], fell_back: bool, failure: Exception | None) -> str:
    if failure is not None:
        return f"(no usable answer: {failure})"
    prefix = (
        "(nobody answered before the deadline; using the declared fallback)\n" if fell_back else ""
    )
    return prefix + json.dumps(dict(output), indent=2, sort_keys=True)


def _read_answer(path: Path) -> Mapping[str, Any]:
    """Read an answer file, refusing anything that is not a JSON object.

    A half-written file is a real possibility — someone is editing it by hand — so a decode
    failure is an error rather than a timeout. Treating it as "nobody answered" would use the
    fallback while a person was mid-sentence.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanError(f"{path} is not readable as JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HumanError(f"{path} must contain a JSON object, not a {type(payload).__name__}")
    return payload
