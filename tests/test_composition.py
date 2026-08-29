"""Phase 4b: cells composed as data, and a person as one of them.

The fourth Phase 4 minimum test lives here. The deadline tests use real wall-clock, kept to
tens of milliseconds — a fake clock would test the fake, and the thing under test *is* whether
a deadline actually expires.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from test_cells import Scripted, a_cell, answers

from g0rd0n import cells
from g0rd0n.cells import graph as graph_module
from g0rd0n.cells import human
from g0rd0n.cells.cell import Schema
from g0rd0n.cells.human import FileDrop, HumanQuery
from g0rd0n.config import Config
from g0rd0n.kernel import Bridge, Ref
from g0rd0n.ledger import Cost
from g0rd0n.ledger.ledger import open_session

ADVICE: Schema = {"verdict": str, "confident": bool}
FALLBACK = {"verdict": "nobody answered", "confident": False}


def a_query(
    deadline_seconds: float = 0.05,
    question: str = "Is this claim falsifiable as written?",
    fallback: Mapping[str, Any] | None = None,
) -> HumanQuery:
    return HumanQuery(
        role="referee",
        question=question,
        schema=ADVICE,
        deadline_seconds=deadline_seconds,
        fallback=FALLBACK if fallback is None else fallback,
        estimate=Cost(usd=0.0, human_seconds=600.0, seconds=600.0),
    )


class Answers:
    """An asker that replies at once with whatever it was built with, or times out."""

    def __init__(self, payload: Mapping[str, Any] | None) -> None:
        self.payload = payload
        self.asked: list[str] = []

    def ask(self, query: HumanQuery, run_id: str) -> Mapping[str, Any] | None:
        self.asked.append(query.question)
        return self.payload


def ask(query: HumanQuery, asker: human.Asker, config: Config, bridge: Bridge) -> cells.Run:
    with open_session(config, campaign="c-test", phase="4b") as ledger:
        return human.ask(query, ledger=ledger, bridge=bridge, asker=asker, wager_id="w-001")


# --------------------------------------------------------------------------------------
# The fourth Phase 4 minimum test
# --------------------------------------------------------------------------------------


def test_human_query_times_out_to_its_declared_fallback(
    cell_config: Config, bridge: Bridge, tmp_path: Path
) -> None:
    """A real deadline, a real asker, and nobody there. The fallback is used and *recorded*.

    `fell_back` is the assertion that matters: a caller has to be able to tell "a person said
    this" from "nobody answered and this is what we agreed to assume".
    """
    queue = tmp_path / "queue"
    done = ask(
        a_query(deadline_seconds=0.05), FileDrop(queue, poll_seconds=0.01), cell_config, bridge
    )

    assert done.fell_back is True
    assert done.output == FALLBACK
    assert done.cost.human_seconds >= 0.05, "waiting for a person is priced in wall-clock"
    assert list(queue.glob("*.question.json")), "the question was never actually put to anyone"


def test_an_answer_before_the_deadline_is_used_and_is_not_a_fallback(
    cell_config: Config, bridge: Bridge, tmp_path: Path
) -> None:
    """The other half: a person who answers is not quietly overwritten by the fallback."""
    queue = tmp_path / "queue"
    queue.mkdir()
    asker = FileDrop(queue, poll_seconds=0.01)
    run_id = "run-known"
    (queue / f"{run_id}.answer.json").write_text(
        json.dumps({"verdict": "no, it names no measurement", "confident": True}),
        encoding="utf-8",
    )

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        done = human.ask(
            a_query(deadline_seconds=5.0),
            ledger=ledger,
            bridge=bridge,
            asker=asker,
            wager_id="w-001",
            run_id=run_id,
        )

    assert done.fell_back is False
    assert done.output["verdict"] == "no, it names no measurement"


def test_a_person_answering_the_wrong_shape_is_a_failed_run_not_a_fallback(
    cell_config: Config, bridge: Bridge
) -> None:
    """The fallback covers the deadline and nothing else.

    Substituting it for a malformed reply would record "nobody answered" over the top of
    someone who did, which is worse than failing.
    """
    with pytest.raises(cells.SchemaError):
        ask(a_query(), Answers({"verdict": "yes"}), cell_config, bridge)


def test_a_fallback_that_could_never_be_used_is_refused_before_anything_is_reserved(
    cell_config: Config, bridge: Bridge
) -> None:
    """Found in the first millisecond, not at the deadline an hour later."""
    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        with pytest.raises(cells.SchemaError):
            human.ask(
                a_query(fallback={"verdict": "x"}),
                ledger=ledger,
                bridge=bridge,
                asker=Answers(None),
                wager_id="w-001",
            )
        assert ledger.open_reservations == ()
        assert ledger._entries == {}, "a refused query still reserved something"


def test_a_question_is_versioned_like_a_prompt(cell_config: Config, bridge: Bridge) -> None:
    """A person's answer stays attributed to the exact words they were asked."""
    first = ask(a_query(question="Is it falsifiable?"), Answers(None), cell_config, bridge)
    second = ask(a_query(question="Is it falsifiable?  "), Answers(None), cell_config, bridge)

    assert first.playbook != second.playbook
    assert first.playbook.kind == "playbook_version"
    assert bridge.name_of(bridge.assertions_for(Ref("run", first.id))[0].object) == first.playbook


def test_a_human_run_is_recorded_the_same_way_a_cell_run_is(
    cell_config: Config, bridge: Bridge
) -> None:
    """Same accounting: a `plays` edge, an interned transcript, a settled reservation."""
    done = ask(a_query(), Answers(None), cell_config, bridge)
    played = bridge.assertions_for(Ref("run", done.id))

    assert len(played) == 1
    assert bridge.predicate_of(played[0].predicate) == "plays"
    assert done.transcript > 0
    assert "using the declared fallback" in human.transcript(a_query(), done.id, list(done.turns))


def test_a_deadline_of_zero_asks_nobody(cell_config: Config, bridge: Bridge) -> None:
    with pytest.raises(cells.HumanError, match="asks nobody"):
        ask(a_query(deadline_seconds=0), Answers(None), cell_config, bridge)


def test_a_half_written_answer_file_is_an_error_not_a_timeout(
    cell_config: Config, bridge: Bridge, tmp_path: Path
) -> None:
    """Someone is editing that file by hand. Falling back mid-sentence would be a lie."""
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "run-known.answer.json").write_text('{"verdict": "ye', encoding="utf-8")

    with (
        open_session(cell_config, campaign="c-test", phase="4b") as ledger,
        pytest.raises(cells.HumanError, match="not readable as JSON"),
    ):
        human.ask(
            a_query(deadline_seconds=5.0),
            ledger=ledger,
            bridge=bridge,
            asker=FileDrop(queue, poll_seconds=0.01),
            wager_id="w-001",
            run_id="run-known",
        )


# --------------------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------------------


def test_the_order_is_topological_and_deterministic() -> None:
    """Same graph, same sequence, whoever built the dict and in whatever order."""
    forwards = {
        "extract": graph_module.Node(a_cell(), "read it"),
        "critic": graph_module.Node(a_cell(), "attack $s", {"s": "extract.summary"}),
        "judge": graph_module.Node(a_cell(), "rule on $a", {"a": "critic.summary"}),
    }
    backwards = dict(reversed(list(forwards.items())))

    assert cells.order(forwards) == ("extract", "critic", "judge")
    assert cells.order(backwards) == cells.order(forwards)


def test_independent_nodes_run_in_name_order_not_insertion_order() -> None:
    graph = {
        "zulu": graph_module.Node(a_cell(), "one"),
        "alpha": graph_module.Node(a_cell(), "two"),
    }

    assert cells.order(graph) == ("alpha", "zulu")


def test_a_cycle_is_refused_before_anything_is_spent(cell_config: Config, bridge: Bridge) -> None:
    graph = {
        "a": graph_module.Node(a_cell(), "$x", {"x": "b.summary"}),
        "b": graph_module.Node(a_cell(), "$y", {"y": "a.summary"}),
    }

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        with pytest.raises(cells.GraphError, match="cycle"):
            cells.run_graph(
                graph,
                config=cell_config,
                ledger=ledger,
                bridge=bridge,
                model=Scripted(),
                wager_id="w-001",
            )
        assert ledger._entries == {}, "a cyclic graph reserved money before being checked"


def test_a_reference_to_a_node_that_is_not_there_is_refused() -> None:
    for needs, complaint in [
        ({"x": "nowhere.summary"}, "not in the graph"),
        ({"x": "summary"}, "not of the form"),
        ({"x": "a.summary"}, "its own output"),
    ]:
        with pytest.raises(cells.GraphError, match=complaint):
            cells.order({"a": graph_module.Node(a_cell(), "$x", needs)})


def test_an_upstream_output_flows_into_the_next_task(cell_config: Config, bridge: Bridge) -> None:
    """The point of the whole module: node two is asked about node one's answer."""
    stub = Scripted(
        answers(summary="fixed-depth transformers sit inside TC0", understood=True),
        answers(summary="that is an expressivity claim, not a thermodynamic one", understood=True),
    )
    graph = {
        "extract": graph_module.Node(a_cell(), "Read the paper"),
        "critic": graph_module.Node(a_cell(), "Attack this: $claim", {"claim": "extract.summary"}),
    }

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        runs = cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
        )

    asked = stub.requests[1]["turns"]
    assert isinstance(asked, tuple)
    assert asked[0].text == "Attack this: fixed-depth transformers sit inside TC0"
    assert set(runs) == {"extract", "critic"}


def test_a_task_containing_braces_survives_substitution(
    cell_config: Config, bridge: Bridge
) -> None:
    """Why `$name` and not `{name}`: a task is prose, and prose contains JSON and code."""
    stub = Scripted(answers(summary="ok", understood=True))
    task = 'Given {"a": 1} and f(x) = {x | x > 0}, comment on $nothing_here'
    graph = {"one": graph_module.Node(a_cell(), task.replace("$nothing_here", "this"))}

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
        )

    assert stub.requests[0]["turns"][0].text == task.replace("$nothing_here", "this")  # type: ignore[index]


def test_a_failed_node_stops_the_graph_and_names_itself(
    cell_config: Config, bridge: Bridge
) -> None:
    """A partial result that looks like a whole one is worse than a stopped run."""
    stub = Scripted(answers(summary="s"), answers(summary="never reached", understood=True))
    graph = {
        "extract": graph_module.Node(a_cell(), "Read it"),
        "critic": graph_module.Node(a_cell(), "Attack $c", {"c": "extract.summary"}),
    }

    with (
        open_session(cell_config, campaign="c-test", phase="4b") as ledger,
        pytest.raises(cells.GraphError, match="node 'extract' failed"),
    ):
        cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
        )

    assert len(stub.replies) == 1, "the downstream node ran anyway"


def test_a_graph_node_can_be_a_person(cell_config: Config, bridge: Bridge) -> None:
    """A person and a model are two cases in one function, not two hierarchies."""
    stub = Scripted(answers(summary="the claim", understood=True))
    graph = {
        "extract": graph_module.Node(a_cell(), "Read it"),
        "referee": graph_module.Node(a_query(), "Rule on $c", {"c": "extract.summary"}),
    }

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        runs = cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
            asker=Answers({"verdict": "it stands", "confident": True}),
        )

    assert runs["referee"].output["verdict"] == "it stands"
    assert runs["referee"].fell_back is False


def test_a_human_node_without_an_asker_is_refused(cell_config: Config, bridge: Bridge) -> None:
    graph = {"referee": graph_module.Node(a_query(), "Rule on it")}

    with (
        open_session(cell_config, campaign="c-test", phase="4b") as ledger,
        pytest.raises(cells.GraphError, match="no asker"),
    ):
        cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=Scripted(),
            wager_id="w-001",
        )


def test_every_node_reserves_and_settles_on_its_own(cell_config: Config, bridge: Bridge) -> None:
    """Costs per wager still sum to the session total, one node at a time."""
    stub = Scripted(
        answers(summary="one", understood=True),
        answers(summary="two", understood=True),
    )
    graph = {
        "a": graph_module.Node(a_cell(), "one"),
        "b": graph_module.Node(a_cell(), "two on $x", {"x": "a.summary"}),
    }

    with open_session(cell_config, campaign="c-test", phase="4b") as ledger:
        runs = cells.run_graph(
            graph,
            config=cell_config,
            ledger=ledger,
            bridge=bridge,
            model=stub,
            wager_id="w-001",
        )
        assert ledger.open_reservations == ()
        assert len(ledger._entries) == 2

    assert sum(run.cost.tokens_in for run in runs.values()) == 200


def test_a_graph_is_a_dict_and_nothing_wraps_it() -> None:
    """AGENTS.md §Style: a cell graph is a dict, not a subclass tree."""
    assert not hasattr(graph_module, "GraphBuilder")
    assert cells.order({}) == ()
    assert isinstance({"a": graph_module.Node(a_cell(), "x")}, dict)
