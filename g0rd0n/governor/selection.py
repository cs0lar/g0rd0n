"""Experiment selection policies; information gain is the default."""

from __future__ import annotations

import random
from typing import Protocol, Sequence

from .models import ExperimentProposal


class ExperimentSelector(Protocol):
    def select(
        self,
        experiments: Sequence[ExperimentProposal],
        active_hypothesis_ids: frozenset[str],
    ) -> ExperimentProposal | None: ...


def discrimination(experiment: ExperimentProposal, active: frozenset[str]) -> float:
    predictions = [experiment.predictions[item] for item in sorted(active) if item in experiment.predictions]
    pair_count = len(predictions) * (len(predictions) - 1) // 2
    if pair_count == 0 or len(predictions) != len(active):
        return 0.0
    separated = sum(
        predictions[left] != predictions[right]
        for left in range(len(predictions))
        for right in range(left + 1, len(predictions))
    )
    return separated / pair_count


class InformationGainSelector:
    def select(
        self,
        experiments: Sequence[ExperimentProposal],
        active_hypothesis_ids: frozenset[str],
    ) -> ExperimentProposal | None:
        ranked = sorted(
            (
                (discrimination(experiment, active_hypothesis_ids) / experiment.cost_units, experiment)
                for experiment in experiments
            ),
            key=lambda item: (-item[0], item[1].cost_units, item[1].id),
        )
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None


class RandomSelector:
    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def select(
        self,
        experiments: Sequence[ExperimentProposal],
        active_hypothesis_ids: frozenset[str],
    ) -> ExperimentProposal | None:
        discriminating = [
            experiment for experiment in experiments if discrimination(experiment, active_hypothesis_ids) > 0
        ]
        return self._random.choice(discriminating) if discriminating else None
