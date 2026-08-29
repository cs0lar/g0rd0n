"""Cells: agents and humans, with playbooks, allowlists, and typed output.

Four modules, one mechanism each. `playbook` is a versioned prompt, identified by the hash of
its own bytes. `cell` is what an agent *is* — five fields of data, no base class. `model` is
the seam a provider sits behind, plus the one provider, plus the network allowlist. `runtime`
is the function that plays a cell: reserve, converse, check, record, settle.

A Cell commits assertions; an Instrument does not (AGENTS.md §6). That is why `Tool.run`
returns text and why nothing in `cell` or `model` imports the bridge — only `runtime` does,
and only to record what happened.

Phase 4a runs one cell. Composition (a DAG in data) and `HumanQuery` are 4b.

Deletion criterion: this package holds the wager that g0rd0n can act without acting
unaccountably. Delete it and every Phase 4 minimum test loses its verdict at once — no
allowlist, no schema, no transcript, no reservation — and a model call becomes a thing that
happens rather than a thing that was priced, bounded, and recorded.
"""

from g0rd0n.cells.cell import (
    Cell,
    CellError,
    Schema,
    SchemaError,
    Tool,
    ToolNotAllowed,
    check_output,
)
from g0rd0n.cells.model import (
    ANSWER,
    Anthropic,
    Model,
    ModelError,
    ModelUnavailable,
    NetworkRefused,
    Reply,
    ToolCall,
    ToolResult,
    Turn,
    check_host,
)
from g0rd0n.cells.playbook import Playbook, PlaybookError
from g0rd0n.cells.playbook import load as load_playbook
from g0rd0n.cells.runtime import Run, RunId, run, transcript

__all__ = [
    "ANSWER",
    "Anthropic",
    "Cell",
    "CellError",
    "Model",
    "ModelError",
    "ModelUnavailable",
    "NetworkRefused",
    "Playbook",
    "PlaybookError",
    "Reply",
    "Run",
    "RunId",
    "Schema",
    "SchemaError",
    "Tool",
    "ToolCall",
    "ToolNotAllowed",
    "ToolResult",
    "Turn",
    "check_host",
    "check_output",
    "load_playbook",
    "run",
    "transcript",
]
