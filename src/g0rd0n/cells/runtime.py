"""Running one cell: reserve, converse, check, record, settle.

This is the whole runtime, and it is a function rather than a framework. AGENTS.md §Style:
no LangChain-style abstraction layers, no agent framework, a few hundred lines and it should
stay that way. If this file grows, something upstream is wrong.

The order is the invariant, and it is the same order AGENTS.md §3 gives:

    reservation = ledger.reserve(...)   # before anything is sent
    reply       = model.reply(...)      # spent against that reservation, per call
    ledger.settle(reservation)          # whatever happened

Three things are worth knowing about how it fails.

**A failed run is still recorded.** The transcript is interned and the `plays` edge committed
on the way out however the conversation ended — schema failure, refused tool, dead endpoint.
Append-only epistemics apply to g0rd0n's own behaviour: the run that went wrong is the one
you most want to read later, and a runtime that only records its successes is a runtime that
lies by omission.

**Money is settled even when recording fails.** Settlement is in the inner `finally`, so a
kernel that dies between the last model call and the commit costs a transcript, never an
unsettled reservation quietly shrinking every later budget.

**Nothing is retried.** Not the model call, not the tool, not a schema failure. Re-asking a
model that returned the wrong shape is how a failed run becomes a parsed guess with extra
steps, and it spends money doing it.

Deletion criterion: this module holds the wager that no cell spends without a reservation and
no cell's output escapes its schema. Delete it and `cell_cannot_call_a_tool_outside_its_
allowlist`, `cell_output_failing_its_schema_is_a_failed_run_not_a_parsed_guess`, and
`transcript_is_interned_and_linked_to_its_playbook_version` all lose their verdicts at once.
"""

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from g0rd0n.cells.cell import Cell, CellError, Tool, ToolNotAllowed, check_output
from g0rd0n.cells.model import ANSWER, Model, ToolCall, ToolResult, Turn, answer_tool
from g0rd0n.config import Config
from g0rd0n.kernel import Bridge, Claim, EntityId, Provenance, Ref
from g0rd0n.ledger import Cost, Ledger
from g0rd0n.ledger.ledger import Reservation

RunId = str


@dataclass(frozen=True)
class Run:
    """One settled run — of a cell, or of a person — with what it cost and where it is recorded.

    `fell_back` is only ever true for a `HumanQuery` whose deadline passed. It is a field on
    the result rather than a detail in the transcript because a caller must be able to tell
    "a person said this" from "nobody answered and this is what we agreed to assume", and a
    graph downstream of a fallback is running on an assumption, not an answer.
    """

    id: RunId
    role: str
    output: dict[str, Any]
    cost: Cost
    transcript: EntityId
    playbook: Ref
    turns: tuple[Turn, ...]
    fell_back: bool = False


def run(
    cell: Cell,
    task: str,
    *,
    config: Config,
    ledger: Ledger,
    bridge: Bridge,
    model: Model,
    wager_id: str,
    tools: Mapping[str, Tool] | None = None,
    run_id: RunId | None = None,
) -> Run:
    """Play one cell against one task, and return what it produced.

    Raises `CellError` if the cell reached outside its allowlist, returned output its schema
    does not admit, or never answered. Raises `LedgerError` if it cost more than was reserved
    for it. In all of those the transcript is still interned and the reservation still settles.
    """
    available = dict(tools or {})
    _check_allowlist(cell, available)
    if cell.estimate.tokens_out < 1:
        raise CellError(f"{cell.role}: estimate reserves no output tokens, so nothing can run")

    identifier = run_id or f"run-{uuid.uuid4().hex[:12]}"
    reservation = ledger.reserve(wager_id, cell.estimate, cell.role)
    turns: list[Turn] = [Turn(role="user", text=task)]
    spent = Cost()
    output: dict[str, Any] = {}
    failure: Exception | None = None

    try:
        output, spent = _converse(cell, turns, config, ledger, model, available, reservation)
    except Exception as exc:  # recorded, settled, then re-raised unchanged
        failure = exc

    try:
        document = record(
            bridge, cell.playbook.ref, identifier, transcript(cell, identifier, turns)
        )
    finally:
        ledger.settle(reservation)

    if failure is not None:
        raise failure
    return Run(
        id=identifier,
        role=cell.role,
        output=output,
        cost=spent,
        transcript=document,
        playbook=cell.playbook.ref,
        turns=tuple(turns),
    )


def _converse(
    cell: Cell,
    turns: list[Turn],
    config: Config,
    ledger: Ledger,
    model: Model,
    available: Mapping[str, Tool],
    reservation: Reservation,
) -> tuple[dict[str, Any], Cost]:
    """The loop. Appends to `turns` as it goes, so a failure still leaves a transcript."""
    price = config.price_of(cell.playbook.model)
    offered = (*(available[name] for name in cell.tools), answer_tool(cell.schema))
    spent = Cost()

    for _ in range(cell.playbook.max_turns):
        started = time.monotonic()
        reply = model.reply(
            model=cell.playbook.model,
            system=cell.playbook.system,
            turns=tuple(turns),
            tools=offered,
            max_tokens=cell.estimate.tokens_out,
        )
        cost = Cost(
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            usd=price.usd(reply.tokens_in, reply.tokens_out),
            seconds=time.monotonic() - started,
        )
        spent = spent + cost
        ledger.spend(reservation, cost)
        turns.append(Turn(role="assistant", text=reply.text, calls=reply.calls))

        answers = [call for call in reply.calls if call.name == ANSWER]
        if answers:
            return check_output(answers[0].arguments, cell.schema), spent
        if not reply.calls:
            raise CellError(
                f"{cell.role} stopped without calling {ANSWER!r} "
                f"(stop reason: {reply.stop_reason or 'none given'})"
            )
        turns.append(Turn(role="user", results=_use_tools(cell, reply.calls, available)))

    raise CellError(f"{cell.role} used all {cell.playbook.max_turns} turns without answering")


def _use_tools(
    cell: Cell, calls: tuple[ToolCall, ...], available: Mapping[str, Tool]
) -> tuple[ToolResult, ...]:
    """Run the instruments a reply asked for, refusing anything off the allowlist.

    A refusal ends the run rather than becoming a message the model can try around. A cell
    reaching past its allowlist is a design mistake or an instruction that came in with the
    data, and neither is improved by giving it another go.
    """
    results: list[ToolResult] = []
    for call in calls:
        if call.name not in cell.tools:
            raise ToolNotAllowed(
                f"{cell.role} asked for {call.name!r}, which is not in its "
                f"allowlist ({', '.join(cell.tools) or 'empty'})"
            )
        results.append(
            ToolResult(call_id=call.id, content=available[call.name].run(call.arguments))
        )
    return tuple(results)


def _check_allowlist(cell: Cell, available: Mapping[str, Tool]) -> None:
    """Refuse before spending anything if the allowlist names a tool nobody provided."""
    if ANSWER in cell.tools:
        raise CellError(f"{ANSWER!r} is reserved for a cell's own output and cannot be listed")
    missing = sorted(set(cell.tools) - set(available))
    if missing:
        raise CellError(f"{cell.role} allows tools that were not provided: {', '.join(missing)}")


def record(bridge: Bridge, version: Ref, identifier: RunId, text: str) -> EntityId:
    """Intern a transcript and link the run to the prompt version that produced it.

    Shared with `human.ask`, because AGENTS.md §Phase 4 accounts for a person the same way it
    accounts for a model: a question is a prompt, and a person's answer is attributable to the
    exact wording that was put to them.

    The transcript is a document entity, and knk leaves those unnamed, so it is referenced
    from the provenance rather than committed as a subject or object — every entity in an
    assertion carries a `kind:name` (ADR 0003), and a nameless one would make the vault
    unprojectable.

    The edge lands as a `Hypothesis` like everything else the bridge writes. That reads oddly
    for a fact about g0rd0n's own execution, but the bridge has exactly one write path and
    this is not the phase to grow it a second one.
    """
    document = bridge.intern_document(text.encode("utf-8"))
    bridge.hypothesise(
        Claim(Ref("run", identifier), "plays", version, 1.0),
        Provenance(
            source=Ref("source", f"transcript-{identifier}"),
            method=f"g0rd0n run transcript, knk document {document}",
        ),
    )
    return document


def transcript(cell: Cell, identifier: RunId, turns: list[Turn]) -> str:
    """The conversation as text: what was asked, what was answered, what was called.

    Rendered from the same `Turn` list the model was sent, so the record and the request
    cannot disagree. No wall-clock anywhere in it — the run id and the playbook version are
    what make it identifiable, and a timestamp would stop two identical runs comparing equal.
    """
    lines = [
        f"run: {identifier}",
        f"role: {cell.role}",
        f"playbook: {cell.playbook.ref}",
        f"model: {cell.playbook.model}",
        "",
        "=== system ===",
        cell.playbook.system,
    ]
    for turn in turns:
        lines += ["", f"=== {turn.role} ==="]
        if turn.text:
            lines.append(turn.text)
        lines += [f"[calls {call.name} {call.arguments!r}]" for call in turn.calls]
        lines += [f"[result of {result.call_id}] {result.content}" for result in turn.results]
    return "\n".join(lines) + "\n"
