"""Verifier registry, content-addressed artifacts, and counterexample search."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from g0rd0n.research.ledger import canonical_json

from .models import Counterexample, FormalClaim, ProofBundle, VerificationResult


class ProofVerifier(Protocol):
    id: str

    def verify(self, bundle: ProofBundle) -> VerificationResult: ...


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[str, ProofVerifier] = {}

    def register(self, verifier: ProofVerifier) -> None:
        if verifier.id in self._verifiers:
            raise ValueError(f"verifier already registered: {verifier.id}")
        self._verifiers[verifier.id] = verifier

    def verify(self, bundle: ProofBundle) -> VerificationResult:
        try:
            verifier = self._verifiers[bundle.claim.verifier]
        except KeyError as error:
            raise ValueError(f"unknown verifier: {bundle.claim.verifier}") from error
        return verifier.verify(bundle)


class ProofArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, artifact: Mapping[str, Any]) -> str:
        content = canonical_json(artifact)
        digest = hashlib.sha256(content).hexdigest()
        path = self.root / f"{digest}.json"
        if not path.exists():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                remaining = memoryview(content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written == 0:
                        raise OSError("proof artifact write made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return digest

    def get(self, digest: str) -> Mapping[str, Any]:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("artifact digest must be lowercase sha256")
        content = (self.root / f"{digest}.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("proof artifact hash mismatch")
        value = json.loads(content)
        if not isinstance(value, Mapping):
            raise ValueError("proof artifact root must be an object")
        return value


def search_bound_counterexample(claim: FormalClaim, *, maximum_n: int) -> Counterexample | None:
    if maximum_n < claim.domain_min_n:
        raise ValueError("counterexample search range does not intersect claim domain")
    for n in range(claim.domain_min_n, maximum_n + 1):
        x_cost = claim.x_bound.evaluate(n)
        y_cost = claim.y_bound.evaluate(n)
        if x_cost >= y_cost:
            return Counterexample(n, x_cost, y_cost, "claimed upper bound is not strictly below lower bound")
    return None
