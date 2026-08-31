"""Cells: agents and humans, with playbooks, allowlists, and typed output.

Six modules, one mechanism each. `playbook` is a versioned prompt, identified by the hash of
its own bytes. `cell` is what an agent *is* — four fields of data, no base class. `model` is
the seam a provider sits behind, plus the one provider, plus the network allowlist. `runtime`
is the function that plays a cell: reserve, converse, check, record, settle. `human` is the
same, for a person: a question, a deadline, and a declared fallback. `graph` composes them,
as a dict.

A Cell commits assertions; an Instrument does not (AGENTS.md §6). That is why `Tool.run`
returns text and why nothing in `cell` or `model` imports the bridge — only `runtime`,
`human`, and `graph` do, and only to record what happened.

A person and a model return the same `Run` and reserve from the same ledger, because
AGENTS.md §Phase 4 says humans are resources in the network with the same accounting.

Deletion criterion: this package holds the wager that g0rd0n can act without acting
unaccountably. Delete it and `cell_cannot_call_a_tool_outside_its_allowlist`,
`cell_output_failing_its_schema_is_a_failed_run_not_a_parsed_guess`,
`transcript_is_interned_and_linked_to_its_playbook_version` and
`a_cell_reserves_before_it_calls_and_settles_after` lose their verdicts at once — no
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
from g0rd0n.cells.graph import Graph, GraphError, Node, order
from g0rd0n.cells.graph import run as run_graph
from g0rd0n.cells.human import Asker, FileDrop, HumanError, HumanQuery
from g0rd0n.cells.human import ask as ask_human
from g0rd0n.cells.model import (
    ANSWER,
    Anthropic,
    Model,
    ModelError,
    ModelUnavailable,
    Reply,
    ToolCall,
    ToolResult,
    Turn,
)
from g0rd0n.cells.playbook import Playbook, PlaybookError
from g0rd0n.cells.playbook import load as load_playbook
from g0rd0n.cells.runtime import Run, RunId, run, transcript

__all__ = [
    "ANSWER",
    "Anthropic",
    "Asker",
    "Cell",
    "CellError",
    "FileDrop",
    "Graph",
    "GraphError",
    "HumanError",
    "HumanQuery",
    "Model",
    "ModelError",
    "ModelUnavailable",
    "Node",
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
    "ask_human",
    "check_output",
    "load_playbook",
    "order",
    "run",
    "run_graph",
    "transcript",
]
