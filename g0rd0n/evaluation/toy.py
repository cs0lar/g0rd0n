"""Tiny systems used only to validate harness rankings and reproduction."""

from __future__ import annotations

import random

from .harness import ResourceUsage


class LookupBaseline:
    """Memorizes the train domain and guesses outside it."""

    def evaluate(self, *, seed: int, random_source: random.Random):
        train = {value: 2 * value + 1 for value in range(8)}
        test = list(range(8, 16))
        random_source.shuffle(test)
        predictions = [train.get(value, -1) for value in test]
        correct = sum(prediction == 2 * value + 1 for prediction, value in zip(predictions, test))
        return (
            {"accuracy": correct / len(test)},
            ResourceUsage(operations=24, peak_memory_bytes=128, modelled_latency_ms=2.4),
        )


class AffineRuleCandidate:
    """Induces the affine rule from two examples and applies it out of domain."""

    def evaluate(self, *, seed: int, random_source: random.Random):
        examples = [(0, 1), (1, 3)]
        slope = examples[1][1] - examples[0][1]
        intercept = examples[0][1]
        test = list(range(8, 16))
        random_source.shuffle(test)
        correct = sum(slope * value + intercept == 2 * value + 1 for value in test)
        return (
            {"accuracy": correct / len(test)},
            ResourceUsage(operations=12, peak_memory_bytes=32, modelled_latency_ms=1.2),
        )


BUILTIN_SYSTEMS = {
    "builtin:toy_lookup": LookupBaseline,
    "builtin:toy_affine_rule": AffineRuleCandidate,
}
