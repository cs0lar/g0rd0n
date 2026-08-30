"""Formal claims and independently checkable proof artifacts."""

from .models import (
    BoundKind,
    BoundTemplate,
    ComplexityBound,
    Counterexample,
    FormalClaim,
    ProofBundle,
    ProofObligation,
    VerificationResult,
)
from .toy_membership import ToyMembershipSeparationVerifier
from .workbench import ProofArtifactStore, ProofVerifier, VerifierRegistry, search_bound_counterexample


def builtin_verifier_registry() -> VerifierRegistry:
    registry = VerifierRegistry()
    registry.register(ToyMembershipSeparationVerifier())
    return registry


__all__ = [
    "BoundKind",
    "BoundTemplate",
    "ComplexityBound",
    "Counterexample",
    "FormalClaim",
    "ProofArtifactStore",
    "ProofBundle",
    "ProofObligation",
    "ProofVerifier",
    "ToyMembershipSeparationVerifier",
    "VerificationResult",
    "VerifierRegistry",
    "builtin_verifier_registry",
    "search_bound_counterexample",
]
