"""Cells: agents and humans, with playbooks, allowlists, and typed output.

Seven modules, one mechanism each. `playbook` is a versioned prompt, identified by the hash of
its own bytes. `cell` is what an agent *is* — four fields of data, no base class. `model` is
the seam a provider sits behind, plus the one provider, plus the network allowlist. `runtime`
is the function that plays a cell: reserve, converse, check, record, settle. `human` is the
same, for a person: a question, a deadline, and a declared fallback. `graph` composes them,
as a dict. `arm` is the odd one out and is here because it calls a model: a system *under
evaluation*, its versioned config, and the loop that asks it every instance of a set.

A Cell commits assertions; an Instrument does not (AGENTS.md §6). That is why `Tool.run`
returns text and why nothing in `cell` or `model` imports the bridge — only `runtime`,
`human`, and `graph` do, and only to record what happened.

`arm` commits nothing either, and for a third reason: it is the *subject* of an experiment
rather than something doing g0rd0n's work, so its 120 answers are not 120 claims about the
world. The one commit an evaluation makes is `cortex/protocol.py`'s single `measures`.

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

from g0rd0n.cells.arm import CONTROL, Answered, Arm, ArmError, Attempt, attempt
from g0rd0n.cells.arm import baselines as arm_baselines
from g0rd0n.cells.arm import load as load_arm
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
    "CONTROL",
    "Answered",
    "Anthropic",
    "Arm",
    "ArmError",
    "Asker",
    "Attempt",
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
    "arm_baselines",
    "ask_human",
    "attempt",
    "check_output",
    "load_arm",
    "load_playbook",
    "order",
    "run",
    "run_graph",
    "transcript",
]
