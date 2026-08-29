"""What a Cell is, and what its output has to look like.

AGENTS.md §Phase 4: a Cell is an agent with a role, a system prompt from a versioned
Playbook, a tool allowlist, a budget reservation, and a typed output schema. *Nothing else.*
So this module is five fields and two rules, and there is no base class to inherit from —
a Cell is data, and `runtime.run` is the function that plays it.

The two rules, both of which make a run **fail** rather than degrade:

- **A tool outside the allowlist is refused.** Not answered with an error the model can
  retry against: a cell reaching past its allowlist is a design mistake or an injected
  instruction, and either way the useful response is to stop, cheaply, and say so.
- **Output that does not match the schema is a failed run.** Never coerced, never repaired,
  never re-asked. A parsed guess is a result nobody chose, wearing the costume of one that
  was measured.

Schemas are closed: a field the schema does not name is as much a failure as a missing one.
An extra field is a model telling you something you did not ask for, and silently dropping
it is how a cell's contract rots.

Deletion criterion: this module holds the wager that a cell's output is either what its
schema says or nothing at all. Delete it and `cell_output_failing_its_schema_is_a_failed_run_
not_a_parsed_guess` and `cell_cannot_call_a_tool_outside_its_allowlist` both lose their
verdicts, and the runtime starts believing whatever a model happened to emit.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from g0rd0n.cells.playbook import Playbook
from g0rd0n.ledger import Cost

#: A typed output schema: field name to the Python type it must have. Deliberately tiny —
#: nested JSON Schema would be a language, and AGENTS.md §Style says a cell graph is a dict,
#: not a subclass tree. The same applies to what a cell returns.
Schema = Mapping[str, type]

#: How each schema type is named to the model. The model is told the shape; the runtime still
#: checks it on the way back, because being told is not being bound.
JSON_TYPES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


class CellError(Exception):
    """A cell could not be run, or would not be run, as described."""


class SchemaError(CellError):
    """Output did not match the schema. The run failed; nothing was parsed out of it."""


class ToolNotAllowed(CellError):
    """A cell tried to use a tool outside its allowlist. The run failed."""


@dataclass(frozen=True)
class Tool:
    """One instrument, as a cell sees it.

    `run` returns text and never commits an assertion: AGENTS.md §6 — instruments return
    results, a Cell commits. Phase 4a ships no instruments; Phase 6 is the first to add one.
    """

    name: str
    description: str
    parameters: Schema
    run: Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True)
class Cell:
    """An agent, as data. Five fields, per AGENTS.md §Phase 4, and no behaviour."""

    playbook: Playbook
    tools: tuple[str, ...]
    schema: Schema
    estimate: Cost

    @property
    def role(self) -> str:
        return self.playbook.role


def check_output(payload: Mapping[str, Any], schema: Schema) -> dict[str, Any]:
    """Return the payload if it matches the schema exactly, or raise `SchemaError`.

    Exactly: every named field present, with the named type, and no field that was not
    named. `bool` is rejected where `int` is wanted, because Python says `True == 1` and a
    schema that cannot tell a flag from a count is not typing anything.
    """
    missing = sorted(set(schema) - set(payload))
    if missing:
        raise SchemaError(f"output is missing {', '.join(missing)}")
    extra = sorted(set(payload) - set(schema))
    if extra:
        raise SchemaError(f"output has fields the schema does not name: {', '.join(extra)}")
    for field, kind in schema.items():
        value = payload[field]
        if kind is not bool and isinstance(value, bool):
            raise SchemaError(f"output field {field!r} must be {kind.__name__}, got a bool")
        if kind is float and isinstance(value, int):
            continue  # a whole number is a number; JSON has one numeric type
        if not isinstance(value, kind):
            raise SchemaError(
                f"output field {field!r} must be {kind.__name__}, got {type(value).__name__}"
            )
    return dict(payload)


def as_json_schema(schema: Schema) -> dict[str, Any]:
    """Describe a schema to the model, in the shape the Messages API wants for a tool."""
    return {
        "type": "object",
        "properties": {field: {"type": JSON_TYPES[kind]} for field, kind in schema.items()},
        "required": sorted(schema),
    }
