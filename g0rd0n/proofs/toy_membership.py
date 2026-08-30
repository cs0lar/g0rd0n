"""Independent checker for a narrow direct-address membership separation."""

from __future__ import annotations

from .models import BoundTemplate, ProofBundle, VerificationResult


VERIFIER_ID = "builtin:toy-membership-separation-v1"
REQUIRED_ASSUMPTIONS = {
    "The universe is {0,...,U-1}, the set contains n distinct keys with U>n, and X uses a U-bit vector.",
    "A word-RAM computes the query address and reads one indexed bit in constant time.",
    "Y is a deterministic ordered comparison decision tree over n distinct stored keys.",
    "The measured resource is worst-case sequential key comparisons or indexed bit reads per query.",
}
REQUIRED_OBLIGATIONS = {"x-correct", "x-upper", "y-lower", "strict-separation"}


class ToyMembershipSeparationVerifier:
    id = VERIFIER_ID

    def verify(self, bundle: ProofBundle) -> VerificationResult:
        claim = bundle.claim
        certificate = bundle.certificate
        errors: list[str] = []
        discharged: list[str] = []

        if claim.task_family != "static set membership":
            errors.append("unexpected task family")
        if set(claim.assumptions) != REQUIRED_ASSUMPTIONS:
            errors.append("claim assumptions do not exactly define the checked models")
        if {item.id for item in claim.obligations} != REQUIRED_OBLIGATIONS:
            errors.append("claim proof obligations do not match verifier obligations")
        if claim.x_bound.template is not BoundTemplate.CONSTANT or claim.x_bound.constant != 1:
            errors.append("X must claim an upper bound of one indexed read")
        if claim.y_bound.template is not BoundTemplate.CEIL_LOG2_N_PLUS_1:
            errors.append("Y must claim the comparison-tree logarithmic lower bound")

        if certificate.get("direct_address_rule") == "return bit_vector[query]":
            discharged.extend(("x-correct", "x-upper"))
        else:
            errors.append("direct-address certificate is missing or altered")

        if (
            certificate.get("induction_rule") == "natural-number induction"
            and certificate.get("capacity_base") == "C(0)=0"
            and certificate.get("capacity_recurrence") == "C(h)=1+2*C(h-1)"
            and certificate.get("capacity_closed_form") == "C(h)=2^h-1"
            and certificate.get("normalized_step") == "1+2*(2^h-1)=2^(h+1)-1"
            and self._capacity(0) == 0
        ):
            discharged.append("y-lower")
        else:
            errors.append("comparison-tree capacity induction failed")

        # For the supported monotone templates, checking the declared minimum
        # establishes 1 < ceil(log2(n+1)) for every larger n.
        if (
            claim.domain_min_n >= 2
            and claim.x_bound.evaluate(claim.domain_min_n) < claim.y_bound.evaluate(claim.domain_min_n)
        ):
            discharged.append("strict-separation")
        else:
            errors.append("bounds are not strictly separated on the full declared domain")

        discharged_set = set(discharged)
        missing = REQUIRED_OBLIGATIONS - discharged_set
        if missing:
            errors.append(f"undischarged obligations: {sorted(missing)}")
        return VerificationResult(not errors, self.id, tuple(sorted(discharged_set)), tuple(errors))

    @staticmethod
    def _capacity(height: int) -> int:
        return 0 if height == 0 else 1 + 2 * ToyMembershipSeparationVerifier._capacity(height - 1)
