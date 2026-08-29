"""Controlled vocabulary used to prevent category errors in claims."""

from enum import StrEnum


class ScientificDimension(StrEnum):
    COMPUTABILITY = "computability"
    COMPLEXITY = "complexity"
    LEARNABILITY = "learnability"
    GENERALITY = "generality"
    AUTONOMY = "autonomy"
    EFFICIENCY = "efficiency"
    PHYSICAL_REALIZABILITY = "physical_realizability"


class ClaimStrength(StrEnum):
    THEOREM = "theorem"
    ASYMPTOTIC_SEPARATION = "asymptotic_separation"
    BOUND_SEPARATION = "bound_separation"
    VERIFIED_ALGORITHMIC_ADVANTAGE = "verified_algorithmic_advantage"
    EMPIRICAL_PARETO_DOMINANCE = "empirical_pareto_dominance"


class BaselineFamily(StrEnum):
    TRANSFORMER = "transformer"
    RECURRENT_NEURAL_NETWORK = "recurrent_neural_network"
    CONVOLUTIONAL_NEURAL_NETWORK = "convolutional_neural_network"
    STATE_SPACE_MODEL = "state_space_model"
    NEURAL_MEMORY_SYSTEM = "neural_memory_system"


class VerificationMode(StrEnum):
    MEASUREMENT = "measurement"
    FORMAL_CHECK = "formal_check"
