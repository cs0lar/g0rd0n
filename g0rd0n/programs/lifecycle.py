"""Bounded multi-session execution with review gates and failure recovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Mapping, Protocol

from g0rd0n.research.ledger import content_hash

from .journal import ProgramJournal
from .models import (
    ExperimentResult,
    ExperimentTask,
    ProgramCost,
    ProgramState,
    ProgramStatus,
    ResearchProgramSpec,
)


class ExperimentExecutor(Protocol):
    def execute(self, task: ExperimentTask, *, attempt: int) -> ExperimentResult: ...


@dataclass(frozen=True, slots=True)
class SessionReport:
    program_id: str
    status: ProgramStatus
    question: str
    hypotheses_considered: tuple[str, ...]
    experiments_performed: tuple[str, ...]
    observations: tuple[str, ...]
    evidence_obtained: tuple[str, ...]
    claims_changed: tuple[str, ...]
    failures: tuple[str, ...]
    spend: ProgramCost
    unresolved_uncertainty: tuple[str, ...]
    best_next_question: str
    reason: str

    def markdown(self) -> str:
        def items(values: tuple[str, ...]) -> str:
            return "\n".join(f"- {item}" for item in values) if values else "- None recorded"

        return "\n".join(
            (
                f"# Research program report: {self.program_id}",
                "",
                f"- Status: `{self.status.value}`",
                f"- Reason: {self.reason}",
                "",
                "## Question asked",
                "",
                self.question,
                "",
                "## Hypotheses considered",
                "",
                items(self.hypotheses_considered),
                "",
                "## Experiments performed",
                "",
                items(self.experiments_performed),
                "",
                "## Observations and evidence",
                "",
                items(self.observations + self.evidence_obtained),
                "",
                "## Claims changed",
                "",
                items(self.claims_changed),
                "",
                "## Failures",
                "",
                items(self.failures),
                "",
                "## Resource spend",
                "",
                f"- Money: {self.spend.currency_micros} micros",
                f"- Tokens: {self.spend.tokens}",
                f"- Compute: {self.spend.compute_ms} ms",
                f"- Energy: {self.spend.energy_joules:.6f} J",
                f"- Human review: {self.spend.human_minutes:.3f} min",
                "",
                "## Unresolved uncertainty",
                "",
                items(self.unresolved_uncertainty),
                "",
                "## Best next question",
                "",
                self.best_next_question,
                "",
            )
        )


class ResearchProgramLifecycle:
    def __init__(
        self,
        spec: ResearchProgramSpec,
        journal: ProgramJournal,
        executor: ExperimentExecutor,
    ) -> None:
        self.spec = spec
        self.journal = journal
        self.executor = executor
        spec_hash = content_hash(asdict(spec))
        if journal.state is None:
            state = ProgramState(
                spec.id,
                spec_hash,
                ProgramStatus.READY,
                0,
                tuple(item.id for item in spec.experiments),
                (),
                (),
                (),
                0,
                ProgramCost(),
                (),
                (),
                (),
                (),
                (),
                spec.question,
                "program initialized",
            )
            journal.append("program_initialized", state)
        elif journal.state.program_id != spec.id:
            raise ValueError("journal belongs to a different research program")
        elif journal.state.spec_hash != spec_hash:
            raise ValueError("research program specification changed since checkpoint")
        self._tasks = {item.id: item for item in spec.experiments}
        if set(journal.state.pending_experiment_ids + journal.state.completed_experiment_ids + journal.state.failed_experiment_ids) - set(self._tasks):
            raise ValueError("journal references experiments absent from the specification")

    @property
    def state(self) -> ProgramState:
        assert self.journal.state is not None
        return self.journal.state

    def run_session(
        self,
        *,
        max_actions: int,
        review_decisions: Mapping[str, bool] | None = None,
    ) -> SessionReport:
        if max_actions <= 0:
            raise ValueError("session max_actions must be positive")
        if self.state.status in {ProgramStatus.COMPLETED, ProgramStatus.ESCALATED}:
            return self.report()
        reviews = dict(review_decisions or {})
        state = replace(
            self.state,
            status=ProgramStatus.RUNNING,
            session_number=self.state.session_number + 1,
            reason="session started from durable checkpoint",
        )
        self.journal.append("session_started", state)
        actions = 0
        while state.pending_experiment_ids and actions < max_actions:
            task = self._tasks[state.pending_experiment_ids[0]]
            if task.requires_human_review and task.id not in reviews:
                state = replace(state, status=ProgramStatus.WAITING_REVIEW, reason=f"human review required for {task.id}")
                self.journal.append("review_required", state)
                return self.report()
            if task.requires_human_review and not reviews[task.id]:
                reason = f"human reviewer rejected {task.id}"
                if self.spec.escalation.escalate_on_review_rejection:
                    state = replace(state, status=ProgramStatus.ESCALATED, failure_count=state.failure_count + 1, failures=state.failures + (reason,), reason=reason)
                    self.journal.append("review_rejected", state)
                    return self.report()
                state = self._fail_task(state, task, reason)
                self.journal.append("review_rejected", state)
                actions += 1
                continue
            if not (state.spend + task.maximum_cost).within(self.spec.budget):
                reason = f"maximum cost for {task.id} would exceed program budget"
                status = ProgramStatus.ESCALATED if self.spec.escalation.escalate_on_budget_denial else ProgramStatus.PAUSED
                state = replace(state, status=status, reason=reason)
                self.journal.append("budget_denied", state)
                return self.report()

            attempt = state.attempt_count(task.id) + 1
            attempts = dict(state.attempts)
            attempts[task.id] = attempt
            try:
                result = self.executor.execute(task, attempt=attempt)
            except Exception as error:
                state = replace(state, attempts=tuple(sorted(attempts.items())))
                state = self._handle_failure(state, task, f"{task.id} attempt {attempt} raised {type(error).__name__}: {error}")
                self.journal.append("experiment_failed", state)
                actions += 1
                if state.status is ProgramStatus.ESCALATED:
                    return self.report()
                continue

            state = replace(
                state,
                attempts=tuple(sorted(attempts.items())),
                spend=state.spend + result.actual_cost,
                observations=state.observations + (result.observation,),
                evidence=state.evidence + result.evidence,
                claims_changed=state.claims_changed + result.claims_changed,
                failures=state.failures + result.failures,
                unresolved_uncertainty=result.unresolved_uncertainty,
                best_next_question=result.best_next_question,
            )
            if not result.actual_cost.within(task.maximum_cost):
                reason = f"{task.id} exceeded its declared maximum cost"
                state = replace(state, status=ProgramStatus.ESCALATED, failures=state.failures + (reason,), reason=reason)
                self.journal.append("maximum_cost_exceeded", state)
                return self.report()
            if result.success:
                state = replace(
                    state,
                    pending_experiment_ids=state.pending_experiment_ids[1:],
                    completed_experiment_ids=state.completed_experiment_ids + (task.id,),
                    reason=f"{task.id} completed",
                )
                self.journal.append("experiment_completed", state)
            else:
                state = self._handle_failure(state, task, f"{task.id} attempt {attempt} did not satisfy its stop condition")
                self.journal.append("experiment_failed", state)
                if state.status is ProgramStatus.ESCALATED:
                    return self.report()
            actions += 1

        if not state.pending_experiment_ids:
            state = replace(state, status=ProgramStatus.COMPLETED, reason="experiment queue exhausted")
            self.journal.append("program_completed", state)
        else:
            state = replace(state, status=ProgramStatus.PAUSED, reason="session action limit reached")
            self.journal.append("session_paused", state)
        return self.report()

    def _handle_failure(self, state: ProgramState, task: ExperimentTask, reason: str) -> ProgramState:
        failures = state.failures + (reason,)
        failure_count = state.failure_count + 1
        if failure_count >= self.spec.escalation.max_total_failures:
            return replace(state, failure_count=failure_count, failures=failures, status=ProgramStatus.ESCALATED, reason="total failure escalation threshold reached")
        if state.attempt_count(task.id) >= task.max_attempts:
            return replace(
                state,
                pending_experiment_ids=state.pending_experiment_ids[1:],
                failed_experiment_ids=state.failed_experiment_ids + (task.id,),
                failure_count=failure_count,
                failures=failures,
                reason=f"{task.id} exhausted retry allowance",
            )
        return replace(state, failure_count=failure_count, failures=failures, reason=f"{task.id} retained for retry")

    def _fail_task(self, state: ProgramState, task: ExperimentTask, reason: str) -> ProgramState:
        failure_count = state.failure_count + 1
        updated = replace(
            state,
            pending_experiment_ids=state.pending_experiment_ids[1:],
            failed_experiment_ids=state.failed_experiment_ids + (task.id,),
            failure_count=failure_count,
            failures=state.failures + (reason,),
            reason=reason,
        )
        if failure_count >= self.spec.escalation.max_total_failures:
            return replace(updated, status=ProgramStatus.ESCALATED, reason="total failure escalation threshold reached")
        return updated

    def report(self) -> SessionReport:
        state = self.state
        attempts = dict(state.attempts)
        performed = tuple(task.id for task in self.spec.experiments if attempts.get(task.id, 0) > 0)
        return SessionReport(
            self.spec.id,
            state.status,
            self.spec.question,
            self.spec.hypotheses,
            performed,
            state.observations,
            state.evidence,
            state.claims_changed,
            state.failures,
            state.spend,
            state.unresolved_uncertainty,
            state.best_next_question,
            state.reason,
        )
