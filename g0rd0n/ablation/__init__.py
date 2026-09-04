"""Harness ablation, held-out adoption, and rollback decisions."""

from .analysis import (
    AblationStudy,
    HeldOutEvaluation,
    evaluate_held_out,
    paired_estimate,
    run_study,
    select_adoption,
    sensitivity_analysis,
)
from .models import (
    AblationSpec,
    AblationWorkload,
    AdoptionPlan,
    AdoptionStatus,
    DecisionThresholds,
    HarnessConfiguration,
    HarnessMechanism,
    HumanIdea,
    IdeaOrigin,
    MechanismDecision,
    MechanismProfile,
    PairedEstimate,
    RunMetrics,
    RunResult,
    SeededDefect,
    SensitivityResult,
    WorkloadBudget,
    WorkloadOutcome,
    WorkloadSource,
    WorkloadSplit,
)
from .runner import AblationMatrix, configurations, run_configuration, run_matrix

__all__ = [
    "AblationMatrix", "AblationSpec", "AblationStudy", "AblationWorkload", "AdoptionPlan",
    "AdoptionStatus", "DecisionThresholds", "HarnessConfiguration", "HarnessMechanism",
    "HeldOutEvaluation", "HumanIdea", "IdeaOrigin", "MechanismDecision", "MechanismProfile",
    "PairedEstimate", "RunMetrics", "RunResult", "SeededDefect", "SensitivityResult",
    "WorkloadBudget", "WorkloadOutcome", "WorkloadSource", "WorkloadSplit", "configurations",
    "evaluate_held_out", "paired_estimate", "run_configuration", "run_matrix", "run_study",
    "select_adoption", "sensitivity_analysis",
]
