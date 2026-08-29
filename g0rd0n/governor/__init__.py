"""Minimal closed-loop research governor."""

from .adversarial import (
    AdversarialOutcome,
    AdversarialScienceLoop,
    Candidate,
    CandidateAssessment,
    CandidateStatus,
    EvidenceUpdate,
    FalsifyingExperiment,
    NoveltyIndex,
    RedTeamReview,
    RoleAssignment,
    ScientificRole,
)
from .governor import GovernorConfig, MinimalResearchGovernor
from .models import CycleDecision, CycleOutcome, ExperimentProposal
from .selection import InformationGainSelector, RandomSelector

__all__ = [
    "AdversarialOutcome",
    "AdversarialScienceLoop",
    "Candidate",
    "CandidateAssessment",
    "CandidateStatus",
    "CycleDecision",
    "CycleOutcome",
    "ExperimentProposal",
    "EvidenceUpdate",
    "FalsifyingExperiment",
    "GovernorConfig",
    "InformationGainSelector",
    "MinimalResearchGovernor",
    "NoveltyIndex",
    "RandomSelector",
    "RedTeamReview",
    "RoleAssignment",
    "ScientificRole",
]
