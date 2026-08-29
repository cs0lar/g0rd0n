"""A bounded adversarial-science loop with roles represented as data."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence

from .models import require_stable_id


class ScientificRole(StrEnum):
    CANDIDATE_GENERATOR = "candidate_generator"
    CRITIC = "critic"
    FALSIFIER = "falsifier"
    REPLICATOR = "replicator"


class CandidateStatus(StrEnum):
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    SURVIVING = "surviving"
    PROMOTED = "promoted"


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    role: ScientificRole
    instruction: str

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("role instruction is required")


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    statement: str
    prior_weight: float = 0.5

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.statement.strip() or not 0 < self.prior_weight < 1:
            raise ValueError("candidate statement and prior weight in (0, 1) are required")


@dataclass(frozen=True, slots=True)
class FalsifyingExperiment:
    id: str
    description: str
    cost_units: float
    falsifying_outcome: str

    def __post_init__(self) -> None:
        require_stable_id(self.id)
        if not self.description.strip() or self.cost_units <= 0 or not self.falsifying_outcome.strip():
            raise ValueError("falsifying experiment fields are required")


@dataclass(frozen=True, slots=True)
class RedTeamReview:
    strongest_alternative: str
    hidden_assumptions: tuple[str, ...]
    known_failure_modes: tuple[str, ...]
    objections: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.strongest_alternative.strip():
            raise ValueError("a strongest alternative explanation is required")
        if not self.hidden_assumptions or not self.known_failure_modes or not self.objections:
            raise ValueError("review must expose assumptions, failure modes, and objections")


@dataclass(frozen=True, slots=True)
class EvidenceUpdate:
    source: str
    observation: str
    prior_weight: float
    likelihood_if_candidate: float
    likelihood_if_alternative: float
    posterior_weight: float
    replicated: bool


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate: Candidate
    status: CandidateStatus
    review: RedTeamReview | None
    selected_falsifier: FalsifyingExperiment | None
    evidence_updates: tuple[EvidenceUpdate, ...]
    reason: str
    experiment_cost_units: float


@dataclass(frozen=True, slots=True)
class AdversarialOutcome:
    assessments: tuple[CandidateAssessment, ...]
    role_calls: tuple[ScientificRole, ...]
    total_experiment_cost_units: float

    @property
    def promoted_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate.id for item in self.assessments if item.status is CandidateStatus.PROMOTED)


class RoleBackend(Protocol):
    def invoke(self, assignment: RoleAssignment, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class NoveltyIndex:
    def __init__(self, statements: Sequence[str] = (), *, similarity_threshold: float = 0.9) -> None:
        if not 0 < similarity_threshold <= 1:
            raise ValueError("similarity threshold must be in (0, 1]")
        self.threshold = similarity_threshold
        self._signatures = [self._signature(statement) for statement in statements]

    @staticmethod
    def _signature(statement: str) -> frozenset[str]:
        stop_words = {"a", "an", "the", "from", "to", "of", "and"}
        tokens: set[str] = set()
        for token in re.findall(r"[a-z0-9]+", statement.casefold()):
            if token in stop_words:
                continue
            if token.endswith("s") and len(token) > 3:
                token = token[:-1]
            tokens.add(token)
        return frozenset(tokens)

    def admit(self, statement: str) -> bool:
        signature = self._signature(statement)
        if not signature:
            raise ValueError("novelty check requires substantive text")
        for existing in self._signatures:
            union = signature | existing
            if union and len(signature & existing) / len(union) >= self.threshold:
                return False
        self._signatures.append(signature)
        return True


DEFAULT_ASSIGNMENTS = {
    ScientificRole.CANDIDATE_GENERATOR: RoleAssignment(
        ScientificRole.CANDIDATE_GENERATOR, "Generate explicit alternative hypotheses, not endorsements."
    ),
    ScientificRole.CRITIC: RoleAssignment(
        ScientificRole.CRITIC, "Find the strongest alternative, assumptions, failure modes, and objections."
    ),
    ScientificRole.FALSIFIER: RoleAssignment(
        ScientificRole.FALSIFIER, "Propose cheap falsifiers and report structured observations."
    ),
    ScientificRole.REPLICATOR: RoleAssignment(
        ScientificRole.REPLICATOR, "Independently repeat the selected observation."
    ),
}


class AdversarialScienceLoop:
    def __init__(
        self,
        backend: RoleBackend,
        *,
        rejection_threshold: float = 0.2,
        promotion_threshold: float = 0.8,
        novelty_threshold: float = 0.9,
    ) -> None:
        if not 0 < rejection_threshold < promotion_threshold < 1:
            raise ValueError("thresholds must satisfy 0 < rejection < promotion < 1")
        self.backend = backend
        self.rejection_threshold = rejection_threshold
        self.promotion_threshold = promotion_threshold
        self.novelty_threshold = novelty_threshold

    def run(self, question: str) -> AdversarialOutcome:
        if not question.strip():
            raise ValueError("research question is required")
        calls: list[ScientificRole] = []
        generated = self._invoke(ScientificRole.CANDIDATE_GENERATOR, {"question": question}, calls)
        candidates = self._parse_candidates(generated)
        novelty = NoveltyIndex(similarity_threshold=self.novelty_threshold)
        assessments: list[CandidateAssessment] = []
        total_cost = 0.0
        for candidate in candidates:
            if not novelty.admit(candidate.statement):
                assessments.append(CandidateAssessment(candidate, CandidateStatus.DUPLICATE, None, None, (), "semantically duplicate candidate", 0.0))
                continue
            review = self._parse_review(
                self._invoke(ScientificRole.CRITIC, {"candidate": self._candidate_payload(candidate)}, calls)
            )
            falsifier_payload = self._invoke(
                ScientificRole.FALSIFIER,
                {"candidate": self._candidate_payload(candidate), "review": self._review_payload(review)},
                calls,
            )
            experiments = self._parse_falsifiers(falsifier_payload)
            selected = min(experiments, key=lambda item: (item.cost_units, item.id))
            observation = self._parse_observation(
                self._invoke(
                    ScientificRole.FALSIFIER,
                    {
                        "candidate": self._candidate_payload(candidate),
                        "experiment_id": selected.id,
                        "falsifying_outcome": selected.falsifying_outcome,
                    },
                    calls,
                )
            )
            total_cost += selected.cost_units
            update = self._update(candidate.prior_weight, observation, selected.id, replicated=False)
            updates = [update]
            if observation["outcome"] == selected.falsifying_outcome or update.posterior_weight <= self.rejection_threshold:
                assessments.append(CandidateAssessment(candidate, CandidateStatus.REJECTED, review, selected, tuple(updates), "cheapest falsifier rejected candidate", selected.cost_units))
                continue
            replication = self._invoke(
                ScientificRole.REPLICATOR,
                {"candidate": self._candidate_payload(candidate), "experiment_id": selected.id, "original_observation": observation["outcome"]},
                calls,
            )
            replicated_observation = self._parse_observation(replication)
            replicated = replicated_observation["outcome"] == observation["outcome"]
            update = self._update(update.posterior_weight, replicated_observation, f"replication:{selected.id}", replicated=replicated)
            updates.append(update)
            if not replicated or update.posterior_weight <= self.rejection_threshold:
                status = CandidateStatus.REJECTED
                reason = "replication failed or evidence crossed rejection threshold"
            elif update.posterior_weight >= self.promotion_threshold:
                status = CandidateStatus.PROMOTED
                reason = "adversarial evidence replicated above promotion threshold"
            else:
                status = CandidateStatus.SURVIVING
                reason = "candidate survives but lacks promotion evidence"
            assessments.append(CandidateAssessment(candidate, status, review, selected, tuple(updates), reason, selected.cost_units))
        return AdversarialOutcome(tuple(assessments), tuple(calls), total_cost)

    def _invoke(self, role: ScientificRole, payload: Mapping[str, Any], calls: list[ScientificRole]) -> Mapping[str, Any]:
        calls.append(role)
        result = self.backend.invoke(DEFAULT_ASSIGNMENTS[role], payload)
        if not isinstance(result, Mapping):
            raise ValueError(f"{role.value} returned a non-object")
        return result

    @staticmethod
    def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
        return {"id": candidate.id, "statement": candidate.statement, "prior_weight": candidate.prior_weight}

    @staticmethod
    def _review_payload(review: RedTeamReview) -> dict[str, Any]:
        return {
            "strongest_alternative": review.strongest_alternative,
            "hidden_assumptions": list(review.hidden_assumptions),
            "known_failure_modes": list(review.known_failure_modes),
            "objections": list(review.objections),
        }

    @staticmethod
    def _parse_candidates(payload: Mapping[str, Any]) -> tuple[Candidate, ...]:
        values = payload.get("candidates")
        if not isinstance(values, list) or not values:
            raise ValueError("candidate generator must return candidates")
        result = tuple(Candidate(str(item["id"]), str(item["statement"]), float(item.get("prior_weight", 0.5))) for item in values)
        if len({item.id for item in result}) != len(result):
            raise ValueError("candidate ids must be unique")
        return result

    @staticmethod
    def _parse_review(payload: Mapping[str, Any]) -> RedTeamReview:
        return RedTeamReview(
            str(payload["strongest_alternative"]),
            tuple(str(item) for item in payload["hidden_assumptions"]),
            tuple(str(item) for item in payload["known_failure_modes"]),
            tuple(str(item) for item in payload["objections"]),
        )

    @staticmethod
    def _parse_falsifiers(payload: Mapping[str, Any]) -> tuple[FalsifyingExperiment, ...]:
        values = payload.get("experiments")
        if not isinstance(values, list) or not values:
            raise ValueError("falsifier must return experiments")
        return tuple(FalsifyingExperiment(str(item["id"]), str(item["description"]), float(item["cost_units"]), str(item["falsifying_outcome"])) for item in values)

    @staticmethod
    def _parse_observation(value: Mapping[str, Any]) -> Mapping[str, Any]:
        outcome = value.get("outcome")
        candidate_likelihood = float(value.get("likelihood_if_candidate"))
        alternative_likelihood = float(value.get("likelihood_if_alternative"))
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("observation outcome is required")
        if any(not math.isfinite(item) or not 0 <= item <= 1 for item in (candidate_likelihood, alternative_likelihood)):
            raise ValueError("evidence likelihoods must be finite probabilities")
        if candidate_likelihood == alternative_likelihood == 0:
            raise ValueError("evidence likelihoods cannot both be zero")
        return {"outcome": outcome, "likelihood_if_candidate": candidate_likelihood, "likelihood_if_alternative": alternative_likelihood}

    @staticmethod
    def _update(prior: float, observation: Mapping[str, Any], source: str, *, replicated: bool) -> EvidenceUpdate:
        candidate_likelihood = float(observation["likelihood_if_candidate"])
        alternative_likelihood = float(observation["likelihood_if_alternative"])
        numerator = prior * candidate_likelihood
        posterior = numerator / (numerator + (1 - prior) * alternative_likelihood)
        return EvidenceUpdate(source, str(observation["outcome"]), prior, candidate_likelihood, alternative_likelihood, posterior, replicated)
