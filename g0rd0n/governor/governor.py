"""The smallest useful, budgeted, evidence-preserving research loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Sequence

from g0rd0n.budget.engine import BudgetEngine, BudgetedResult
from g0rd0n.core.mission import MissionSpec
from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind
from g0rd0n.research.ledger import FileResearchLedger, ObjectStatus, canonical_json
from g0rd0n.resources.models import Cost, InvocationRequest, InvocationStatus, Permission
from g0rd0n.resources.registry import ResourceRegistry

from .models import (
    CycleDecision,
    CycleOutcome,
    ExperimentProposal,
    HypothesisProposal,
    QuestionProposal,
    require_stable_id,
)
from .selection import ExperimentSelector, InformationGainSelector


@dataclass(frozen=True, slots=True)
class GovernorConfig:
    resource_id: str
    budget_scope_id: str
    granted_permissions: frozenset[Permission]
    planning_maximum_cost: Cost
    max_experiments: int = 3

    def __post_init__(self) -> None:
        if not self.resource_id.strip() or not self.budget_scope_id.strip():
            raise ValueError("governor resource and budget scope are required")
        if self.max_experiments <= 0:
            raise ValueError("max_experiments must be positive")


class MinimalResearchGovernor:
    def __init__(
        self,
        *,
        mission: MissionSpec,
        registry: ResourceRegistry,
        budget: BudgetEngine,
        ledger: FileResearchLedger,
        config: GovernorConfig,
        selector: ExperimentSelector | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.mission = mission
        self.registry = registry
        self.budget = budget
        self.ledger = ledger
        self.config = config
        self.selector = selector or InformationGainSelector()
        self.now = now or (lambda: datetime.now(UTC))
        self._object_counter = 0

    def run(self, current_question: str) -> CycleOutcome:
        current = self._record_object(
            ResearchObjectKind.QUESTION,
            self._new_id("Q-current"),
            "Current research question",
            {"text": current_question, "mission_id": self.mission.id},
            "governor input",
        )
        self._activate(current.id, "loaded current question")

        improved = self._call(
            "improve_question",
            {"mission": self.mission.question, "current_question": current_question},
            self.config.planning_maximum_cost,
        )
        if improved is None:
            return self._finish(CycleDecision.ESCALATE, "question improvement resource failed", None, (), ())
        try:
            questions = self._parse_questions(improved)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            return self._failure(f"invalid question proposals: {error}", None, (), ())
        if not questions:
            return self._failure("question improvement produced no candidates", None, (), ())
        if any(item.id in self.ledger.state.objects for item in questions):
            return self._failure("question proposal reused an existing stable id", None, (), ())
        selected_question = max(questions, key=lambda item: (item.score, item.id))
        for proposal in questions:
            recorded = self._record_object(
                ResearchObjectKind.QUESTION,
                proposal.id,
                proposal.text,
                {
                    "text": proposal.text,
                    "mission_relevance": proposal.mission_relevance,
                    "clarity": proposal.clarity,
                    "falsifiability": proposal.falsifiability,
                },
                "question improvement resource",
            )
            self.ledger.relate(recorded.id, "improves", current.id, self._provenance("governor selection"))
            status = ObjectStatus.ACTIVE if proposal.id == selected_question.id else ObjectStatus.REJECTED
            self.ledger.transition(recorded.id, status, self._provenance("governor selection"), reason="highest question score" if status is ObjectStatus.ACTIVE else "lower question score")
        self.ledger.transition(
            current.id,
            ObjectStatus.SUPERSEDED,
            self._provenance("governor selection"),
            reason=f"replaced by improved question {selected_question.id}",
        )

        generated = self._call(
            "generate_hypotheses",
            {"question": selected_question.text},
            self.config.planning_maximum_cost,
        )
        if generated is None:
            return self._finish(CycleDecision.ESCALATE, "hypothesis resource failed", selected_question.id, (), ())
        try:
            hypotheses = self._parse_hypotheses(generated)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            return self._failure(f"invalid hypotheses: {error}", selected_question.id, (), ())
        if len(hypotheses) < 2:
            return self._failure("at least two competing hypotheses are required", selected_question.id, (), ())
        if any(item.id in self.ledger.state.objects for item in hypotheses):
            return self._failure(
                "hypothesis proposal reused an existing stable id", selected_question.id, (), ()
            )
        hypothesis_by_id = {item.id: item for item in hypotheses}
        for hypothesis in hypotheses:
            recorded = self._record_object(
                ResearchObjectKind.HYPOTHESIS,
                hypothesis.id,
                hypothesis.statement,
                {"statement": hypothesis.statement},
                "hypothesis resource",
            )
            self._activate(recorded.id, "admitted as competing hypothesis")
            self.ledger.relate(selected_question.id, "has_hypothesis", recorded.id, self._provenance("governor"))

        proposed = self._call(
            "propose_experiments",
            {
                "question": selected_question.text,
                "hypotheses": [
                    {"id": item.id, "statement": item.statement} for item in hypotheses
                ],
            },
            self.config.planning_maximum_cost,
        )
        if proposed is None:
            return self._finish(
                CycleDecision.ESCALATE,
                "experiment proposal resource failed",
                selected_question.id,
                tuple(hypothesis_by_id),
                (),
            )
        try:
            experiments = self._parse_experiments(proposed, frozenset(hypothesis_by_id))
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            return self._failure(
                f"invalid experiment proposals: {error}",
                selected_question.id,
                tuple(hypothesis_by_id),
                (),
            )

        for proposal in experiments:
            if proposal.id in self.ledger.state.objects:
                return self._failure(
                    f"experiment id already exists: {proposal.id}",
                    selected_question.id,
                    tuple(hypothesis_by_id),
                    (),
                )
            recorded = self._record_object(
                ResearchObjectKind.EXPERIMENT,
                proposal.id,
                proposal.description,
                {
                    "description": proposal.description,
                    "predictions": dict(proposal.predictions),
                    "cost_units": proposal.cost_units,
                    "maximum_cost": {
                        "currency_micros": proposal.maximum_cost.currency_micros,
                        "tokens": proposal.maximum_cost.tokens,
                        "calls": proposal.maximum_cost.calls,
                        "wall_time_ms": proposal.maximum_cost.wall_time_ms,
                    },
                },
                "experiment proposal resource",
            )
            for hypothesis_id in sorted(hypothesis_by_id):
                self.ledger.relate(recorded.id, "tests", hypothesis_id, self._provenance("governor"))

        active = set(hypothesis_by_id)
        remaining = list(experiments)
        run_ids: list[str] = []
        while len(active) > 1 and len(run_ids) < self.config.max_experiments:
            selected = self.selector.select(remaining, frozenset(active))
            if selected is None:
                return self._finish(
                    CycleDecision.ESCALATE,
                    "no remaining experiment discriminates active hypotheses",
                    selected_question.id,
                    tuple(sorted(active)),
                    tuple(run_ids),
                )
            remaining.remove(selected)
            experiment = self.ledger.state.objects[selected.id]
            self._activate(experiment.id, "selected for maximum discrimination per cost")
            for hypothesis_id in sorted(active):
                prediction_id = self._new_id(f"P-{selected.id}-{hypothesis_id}")
                prediction = self._record_object(
                    ResearchObjectKind.PREDICTION,
                    prediction_id,
                    f"{hypothesis_id} predicts {selected.predictions[hypothesis_id]}",
                    {
                        "experiment_id": selected.id,
                        "hypothesis_id": hypothesis_id,
                        "expected_outcome": selected.predictions[hypothesis_id],
                    },
                    "declared experiment prediction",
                )
                self._activate(prediction.id, "prediction registered before observation")
                self.ledger.relate(hypothesis_id, "predicts", prediction.id, self._provenance("governor"))

            execution = self._call_budgeted(
                "run_experiment", {"experiment_id": selected.id}, selected.maximum_cost
            )
            if execution.invocation is None or execution.event.status is not InvocationStatus.SUCCEEDED:
                self.ledger.transition(
                    experiment.id,
                    ObjectStatus.REJECTED,
                    self._provenance("governor"),
                    reason=f"experiment invocation ended as {execution.event.status.value}",
                )
                return self._finish(
                    CycleDecision.ESCALATE,
                    "selected experiment could not complete within resource or budget constraints",
                    selected_question.id,
                    tuple(sorted(active)),
                    tuple(run_ids),
                )
            output = dict(execution.invocation.output or {})
            outcome = output.get("outcome")
            evidence = output.get("evidence")
            if not isinstance(outcome, str) or not isinstance(evidence, Mapping):
                self.ledger.transition(
                    experiment.id,
                    ObjectStatus.REJECTED,
                    self._provenance("governor"),
                    reason="experiment returned malformed evidence",
                )
                return self._failure(
                    "experiment returned malformed evidence",
                    selected_question.id,
                    tuple(sorted(active)),
                    tuple(run_ids),
                )
            run_ids.append(selected.id)
            self.ledger.transition(
                experiment.id,
                ObjectStatus.COMPLETED,
                self._provenance("governor"),
                reason="experiment produced a structured observation",
            )
            observation = self._record_object(
                ResearchObjectKind.OBSERVATION,
                self._new_id(f"O-{selected.id}"),
                f"Observed {outcome}",
                {"outcome": outcome},
                "experiment executor",
            )
            self._complete(observation.id, "raw observation recorded")
            self.ledger.relate(observation.id, "observed_in", experiment.id, self._provenance("governor"))
            self.ledger.attach_artifact(
                observation.id,
                canonical_json(dict(evidence)),
                self._provenance("experiment executor"),
                media_type="application/json",
            )
            prior_active = set(active)
            active = {item for item in active if selected.predictions[item] == outcome}
            result = self._record_object(
                ResearchObjectKind.RESULT,
                self._new_id(f"R-{selected.id}"),
                f"Result of {selected.id}",
                {
                    "outcome": outcome,
                    "surviving_hypotheses": sorted(active),
                    "eliminated_hypotheses": sorted(prior_active - active),
                },
                "deterministic prediction comparison",
            )
            self._complete(result.id, "result derived from observation")
            self.ledger.relate(result.id, "derived_from", observation.id, self._provenance("governor"))
            for hypothesis_id in sorted(prior_active):
                if hypothesis_id in active:
                    self.ledger.relate(result.id, "supports", hypothesis_id, self._provenance("governor"))
                else:
                    self.ledger.relate(result.id, "contradicts", hypothesis_id, self._provenance("governor"))
                    self.ledger.transition(
                        hypothesis_id,
                        ObjectStatus.REJECTED,
                        self._provenance("governor"),
                        reason=f"prediction contradicted by {observation.id}",
                    )
            if not active:
                return self._finish(
                    CycleDecision.ESCALATE,
                    "observation contradicted every declared hypothesis",
                    selected_question.id,
                    (),
                    tuple(run_ids),
                )

        if len(active) == 1:
            survivor = next(iter(active))
            self.ledger.transition(
                survivor,
                ObjectStatus.COMPLETED,
                self._provenance("governor"),
                reason="sole hypothesis surviving declared predictions",
            )
            return self._finish(
                CycleDecision.STOP,
                "one hypothesis remains after discriminating evidence",
                selected_question.id,
                (survivor,),
                tuple(run_ids),
            )
        next_experiment = self.selector.select(remaining, frozenset(active))
        decision = CycleDecision.CONTINUE if next_experiment is not None else CycleDecision.ESCALATE
        reason = (
            "experiment limit reached; discriminating work remains"
            if decision is CycleDecision.CONTINUE
            else "experiment limit reached with no discriminating work remaining"
        )
        return self._finish(
            decision,
            reason,
            selected_question.id,
            tuple(sorted(active)),
            tuple(run_ids),
        )

    def _call(self, capability: str, payload: Mapping[str, Any], maximum: Cost) -> Mapping[str, Any] | None:
        result = self._call_budgeted(capability, payload, maximum)
        if result.invocation is None or result.event.status is not InvocationStatus.SUCCEEDED:
            return None
        return result.invocation.output

    def _call_budgeted(self, capability: str, payload: Mapping[str, Any], maximum: Cost) -> BudgetedResult:
        return self.budget.invoke(
            self.registry,
            InvocationRequest(
                self.config.resource_id,
                capability,
                payload,
                self.config.granted_permissions,
            ),
            scope_id=self.config.budget_scope_id,
            maximum_cost=maximum,
        )

    def _record_object(
        self,
        kind: ResearchObjectKind,
        object_id: str,
        title: str,
        content: dict[str, Any],
        source: str,
    ) -> ResearchObject:
        require_stable_id(object_id)
        obj = ResearchObject(object_id, kind, title, content, self._provenance(source))
        self.ledger.record(obj)
        return obj

    def _provenance(self, source: str) -> Provenance:
        return Provenance("minimal-research-governor", self.now(), source)

    def _new_id(self, prefix: str) -> str:
        self._object_counter += 1
        safe_prefix = "".join(character if character.isalnum() or character in "._-" else "-" for character in prefix)
        return f"{safe_prefix}-{self._object_counter:04d}"

    def _activate(self, object_id: str, reason: str) -> None:
        self.ledger.transition(object_id, ObjectStatus.ACTIVE, self._provenance("governor"), reason=reason)

    def _complete(self, object_id: str, reason: str) -> None:
        self._activate(object_id, reason)
        self.ledger.transition(object_id, ObjectStatus.COMPLETED, self._provenance("governor"), reason=reason)

    def _finish(
        self,
        decision: CycleDecision,
        reason: str,
        selected_question_id: str | None,
        surviving: Sequence[str],
        experiments_run: Sequence[str],
    ) -> CycleOutcome:
        decision_object = self._record_object(
            ResearchObjectKind.DECISION,
            self._new_id("D-cycle"),
            f"Research cycle decision: {decision.value}",
            {
                "decision": decision.value,
                "reason": reason,
                "selected_question_id": selected_question_id,
                "surviving_hypothesis_ids": list(surviving),
                "experiments_run": list(experiments_run),
            },
            "governor stopping rule",
        )
        self._complete(decision_object.id, reason)
        if selected_question_id is not None and selected_question_id in self.ledger.state.objects:
            self.ledger.relate(
                decision_object.id,
                "selects_question",
                selected_question_id,
                self._provenance("governor"),
            )
        for hypothesis_id in surviving:
            if hypothesis_id in self.ledger.state.objects:
                self.ledger.relate(
                    decision_object.id,
                    "retains",
                    hypothesis_id,
                    self._provenance("governor"),
                )
        for experiment_id in experiments_run:
            if experiment_id in self.ledger.state.objects:
                self.ledger.relate(
                    decision_object.id,
                    "after_experiment",
                    experiment_id,
                    self._provenance("governor"),
                )
        return CycleOutcome(decision, reason, selected_question_id, tuple(surviving), tuple(experiments_run))

    def _failure(
        self,
        reason: str,
        selected_question_id: str | None,
        surviving: Sequence[str],
        experiments_run: Sequence[str],
    ) -> CycleOutcome:
        failure = self._record_object(
            ResearchObjectKind.FAILURE,
            self._new_id("F-cycle"),
            "Research cycle failure",
            {"reason": reason},
            "governor validation",
        )
        self._complete(failure.id, reason)
        return self._finish(CycleDecision.ESCALATE, reason, selected_question_id, surviving, experiments_run)

    @staticmethod
    def _parse_questions(payload: Mapping[str, Any]) -> tuple[QuestionProposal, ...]:
        values = payload.get("questions")
        if not isinstance(values, list):
            raise ValueError("questions must be an array")
        questions = tuple(
            QuestionProposal(
                str(item["id"]),
                str(item["text"]),
                float(item["mission_relevance"]),
                float(item["clarity"]),
                float(item["falsifiability"]),
            )
            for item in values
        )
        if len({item.id for item in questions}) != len(questions):
            raise ValueError("question ids must be unique")
        return questions

    @staticmethod
    def _parse_hypotheses(payload: Mapping[str, Any]) -> tuple[HypothesisProposal, ...]:
        values = payload.get("hypotheses")
        if not isinstance(values, list):
            raise ValueError("hypotheses must be an array")
        hypotheses = tuple(HypothesisProposal(str(item["id"]), str(item["statement"])) for item in values)
        if len({item.id for item in hypotheses}) != len(hypotheses):
            raise ValueError("hypothesis ids must be unique")
        return hypotheses

    @staticmethod
    def _parse_experiments(
        payload: Mapping[str, Any], hypothesis_ids: frozenset[str]
    ) -> tuple[ExperimentProposal, ...]:
        values = payload.get("experiments")
        if not isinstance(values, list):
            raise ValueError("experiments must be an array")
        experiments: list[ExperimentProposal] = []
        for item in values:
            predictions = {str(key): str(value) for key, value in item["predictions"].items()}
            if set(predictions) != set(hypothesis_ids):
                raise ValueError("every experiment must predict every hypothesis")
            maximum = item["maximum_cost"]
            experiments.append(
                ExperimentProposal(
                    str(item["id"]),
                    str(item["description"]),
                    predictions,
                    float(item["cost_units"]),
                    Cost(
                        int(maximum.get("currency_micros", 0)),
                        int(maximum.get("tokens", 0)),
                        int(maximum.get("calls", 0)),
                        int(maximum.get("wall_time_ms", 0)),
                    ),
                )
            )
        if len({item.id for item in experiments}) != len(experiments):
            raise ValueError("experiment ids must be unique")
        return tuple(experiments)
