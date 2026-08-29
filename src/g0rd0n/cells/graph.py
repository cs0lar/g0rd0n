"""Composition: a DAG of calls, described in data.

AGENTS.md §Phase 4 asks for "a plain DAG of calls, described in data, not a framework", and
§Style for "a cell graph is a dict, not a subclass tree". So a graph is a `dict[str, Node]`,
a node names what it needs, and `run` is a function that walks it. There is no scheduler, no
executor, no node base class, and nothing is concurrent.

Data flows through `needs`, which is both the edge list and the substitution table:

    {
        "extract": Node(cell=extractor, task="Read $paper and pull the claim"),
        "critic":  Node(cell=critic, task="Attack this claim: $claim",
                        needs={"claim": "extract.claim"}),
    }

`$name` rather than `{name}`, and `string.Template` rather than `str.format`, because a task
is prose that routinely contains braces — JSON, code, set notation — and `format` would treat
all of it as syntax. A placeholder with nothing to fill it is an error, never an empty string.

**A failed node stops the graph.** Nothing downstream runs, and the failure is raised naming
the node. The alternative — carry on with the nodes that can still run — produces a partial
result that looks like a whole one, and the record would not say which parts were missing.

Every node reserves and settles on its own, so `g0rd0n cost --by wager` still reconciles and
a graph that dies halfway has spent exactly what its finished nodes cost.

Deletion criterion: this module holds the wager that a multi-step piece of work is describable
as data and priced step by step. Delete it and `a_cycle_is_refused_before_anything_is_spent`
loses its verdict, composition moves into whatever calling code happens to want, and the
shape of a run stops being something you can read without running it.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from string import Template
from typing import Any

from g0rd0n.cells import human
from g0rd0n.cells import runtime as cell_runtime
from g0rd0n.cells.cell import Cell, Tool
from g0rd0n.cells.human import Asker, HumanQuery
from g0rd0n.cells.model import Model
from g0rd0n.cells.runtime import Run, RunId
from g0rd0n.config import Config
from g0rd0n.kernel import Bridge
from g0rd0n.ledger import Ledger


class GraphError(Exception):
    """A graph could not be walked, or describes something that is not a DAG."""


@dataclass(frozen=True)
class Node:
    """One call: who makes it, what they are asked, and what the question is built from."""

    cell: Cell | HumanQuery
    task: str
    needs: Mapping[str, str] = field(default_factory=dict)


#: A graph is a plain dict. Nothing wraps it, and nothing needs to.
Graph = Mapping[str, Node]


def order(graph: Graph) -> tuple[str, ...]:
    """A deterministic topological order, or `GraphError` if there is not one.

    Ready nodes are taken in name order rather than insertion order, so the same graph runs
    its steps in the same sequence whoever built the dict and in whatever order they added to
    it. Two identical graphs then produce identical ledgers.
    """
    _check_references(graph)
    remaining = {
        name: {_node_of(source) for source in node.needs.values()} for name, node in graph.items()
    }
    ordered: list[str] = []

    while remaining:
        ready = sorted(name for name, needs in remaining.items() if not needs - set(ordered))
        if not ready:
            raise GraphError(f"these nodes are in a cycle: {', '.join(sorted(remaining))}")
        ordered += ready
        for name in ready:
            del remaining[name]
    return tuple(ordered)


def run(
    graph: Graph,
    *,
    config: Config,
    ledger: Ledger,
    bridge: Bridge,
    model: Model,
    wager_id: str,
    asker: Asker | None = None,
    tools: Mapping[str, Tool] | None = None,
) -> dict[str, Run]:
    """Walk the graph, one node at a time, and return every run it completed.

    Raises `GraphError` naming the node that failed, with the original failure attached. The
    runs that finished before it are lost to the caller but not to the record: each one
    interned its transcript and settled its own reservation as it went.
    """
    runs: dict[str, Run] = {}
    for name in order(graph):
        node = graph[name]
        task = _fill(name, node, runs)
        try:
            runs[name] = _play(
                node,
                task,
                config=config,
                ledger=ledger,
                bridge=bridge,
                model=model,
                wager_id=wager_id,
                asker=asker,
                tools=tools,
            )
        except Exception as exc:
            raise GraphError(f"node {name!r} failed: {exc}") from exc
    return runs


def _play(
    node: Node,
    task: str,
    *,
    config: Config,
    ledger: Ledger,
    bridge: Bridge,
    model: Model,
    wager_id: str,
    asker: Asker | None,
    tools: Mapping[str, Tool] | None,
) -> Run:
    """Dispatch one node. A person and a model are two cases, not two hierarchies."""
    if isinstance(node.cell, HumanQuery):
        if asker is None:
            raise GraphError(f"{node.cell.role} is a human query but no asker was given")
        return human.ask(node.cell, ledger=ledger, bridge=bridge, asker=asker, wager_id=wager_id)
    return cell_runtime.run(
        node.cell,
        task,
        config=config,
        ledger=ledger,
        bridge=bridge,
        model=model,
        wager_id=wager_id,
        tools=tools,
    )


def _fill(name: str, node: Node, runs: Mapping[str, Run]) -> str:
    """Build a node's task from upstream outputs. A missing value is an error, not a blank."""
    values: dict[str, Any] = {}
    for placeholder, source in node.needs.items():
        upstream, _, field_name = source.partition(".")
        output = runs[upstream].output
        if field_name not in output:
            raise GraphError(
                f"node {name!r} needs {source!r}, but {upstream!r} returned "
                f"{', '.join(sorted(output)) or 'nothing'}"
            )
        values[placeholder] = output[field_name]
    try:
        return Template(node.task).substitute(values)
    except (KeyError, ValueError) as exc:
        raise GraphError(f"node {name!r} has a task placeholder nothing fills: {exc}") from exc


def _check_references(graph: Graph) -> None:
    """Every `needs` must name a node in this graph, and a field on it, before anything runs."""
    for name, node in graph.items():
        for placeholder, source in node.needs.items():
            upstream, separator, field_name = source.partition(".")
            if not separator or not field_name:
                raise GraphError(
                    f"node {name!r} needs {source!r}, which is not of the form 'node.field'"
                )
            if upstream not in graph:
                raise GraphError(f"node {name!r} needs {upstream!r}, which is not in the graph")
            if upstream == name:
                raise GraphError(f"node {name!r} needs its own output ({placeholder})")


def _node_of(source: str) -> RunId:
    return source.partition(".")[0]
