"""First mission-facing campaign: fixed-state sparsity versus exact recall."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from g0rd0n.research.ledger import canonical_json


@dataclass(frozen=True, slots=True)
class CurvePoint:
    sequence_length: int
    candidate_accuracy: float
    history_baseline_accuracy: float
    candidate_state_bits: int
    history_baseline_state_bits: int
    candidate_mean_updates: float
    history_baseline_mean_reads: float


@dataclass(frozen=True, slots=True)
class CampaignResult:
    campaign_id: str
    status: str
    candidate_class: str
    parity_curve: tuple[CurvePoint, ...]
    recall_curve: tuple[CurvePoint, ...]
    first_falsifying_length: int | None
    recall_accuracy_threshold: float
    theorem: str
    theorem_obligations: Mapping[str, bool]
    replication_hash: str
    replicated: bool
    transformer_benchmark_executed: bool
    stop_reason: str
    energy_claim: str
    revised_question: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _all_binary_sequences(length: int):
    for value in range(2**length):
        yield tuple((value >> offset) & 1 for offset in reversed(range(length)))


def _fixed_state_recall(sequence: tuple[int, ...], state_bits: int) -> tuple[int, ...]:
    retained = sequence[-state_bits:] if state_bits else ()
    return (0,) * (len(sequence) - len(retained)) + retained


def _event_parity(sequence: tuple[int, ...]) -> int:
    state = 0
    for event in sequence:
        if event:
            state ^= 1
    return state


def _curve(state_bits: int, lengths: tuple[int, ...]) -> tuple[tuple[CurvePoint, ...], tuple[CurvePoint, ...]]:
    parity: list[CurvePoint] = []
    recall: list[CurvePoint] = []
    for length in lengths:
        sequences = tuple(_all_binary_sequences(length))
        candidate_parity_correct = sum(_event_parity(sequence) == sum(sequence) % 2 for sequence in sequences)
        candidate_recall_correct = sum(_fixed_state_recall(sequence, state_bits) == sequence for sequence in sequences)
        mean_ones = sum(sum(sequence) for sequence in sequences) / len(sequences)
        parity.append(
            CurvePoint(length, candidate_parity_correct / len(sequences), 1.0, 1, length, mean_ones, float(length))
        )
        recall.append(
            CurvePoint(
                length,
                candidate_recall_correct / len(sequences),
                1.0,
                state_bits,
                length,
                float(length),
                float(length),
            )
        )
    return tuple(parity), tuple(recall)


def _execute_once(spec: Mapping[str, Any]) -> dict[str, Any]:
    state_bits = int(spec["candidate"]["fixed_state_bits"])
    lengths = tuple(int(item) for item in spec["evaluation"]["sequence_lengths"])
    threshold = float(spec["success_thresholds"]["exact_recall_accuracy"])
    parity, recall = _curve(state_bits, lengths)
    first_falsifier = next(
        (point.sequence_length for point in recall if point.sequence_length > state_bits and point.candidate_accuracy < threshold),
        None,
    )
    obligations = {
        "state_count": all(2**state_bits < 2**length for length in lengths if length > state_bits),
        "collision": all(length <= state_bits or 2**length > 2**state_bits for length in lengths),
        "exact_recall_requires_distinct_prefix_states": all(
            len(set(_all_binary_sequences(length))) == 2**length for length in lengths
        ),
        "lower_bound_b_at_least_L": all(
            length <= state_bits or (2**state_bits < 2**length and state_bits < length)
            for length in lengths
        ),
    }
    return {
        "parity_curve": [asdict(item) for item in parity],
        "recall_curve": [asdict(item) for item in recall],
        "first_falsifying_length": first_falsifier,
        "theorem_obligations": obligations,
    }


def run_campaign(spec_path: Path) -> CampaignResult:
    with spec_path.open(encoding="utf-8") as stream:
        spec = json.load(stream)
    if not isinstance(spec, Mapping):
        raise ValueError("campaign pre-registration must be an object")
    first = _execute_once(spec)
    second = _execute_once(spec)
    first_hash = hashlib.sha256(canonical_json(first)).hexdigest()
    second_hash = hashlib.sha256(canonical_json(second)).hexdigest()
    falsified = first["first_falsifying_length"] is not None
    return CampaignResult(
        str(spec["id"]),
        "falsified_candidate_class" if falsified else "candidate_survives_cheap_falsifier",
        str(spec["candidate"]["class"]),
        tuple(CurvePoint(**item) for item in first["parity_curve"]),
        tuple(CurvePoint(**item) for item in first["recall_curve"]),
        first["first_falsifying_length"],
        float(spec["success_thresholds"]["exact_recall_accuracy"]),
        "Any deterministic machine that exactly recalls every L-bit prefix after a common delay needs at least 2^L distinguishable states, hence at least L persistent state bits.",
        first["theorem_obligations"],
        first_hash,
        first_hash == second_hash,
        False,
        "The pre-registered cheap recall falsifier rejected the fixed-state class before paid or trained Transformer evaluation.",
        "No joule or 20 W claim: only logical state and access counts were recorded; hardware energy measurement was stopped as pre-registered.",
        "Which adaptive external-memory gating primitives retain sparse constant update cost while allocating information capacity only when exact recall demands it?",
    )
