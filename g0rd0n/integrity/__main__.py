"""Run the pre-registered integrity-monitor comparison."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .adversarial import compare_monitored_to_phase18, load_adversarial_cases
from .models import IntegrityPolicy, MonitorQuality


def _quality_dict(quality: MonitorQuality) -> dict[str, object]:
    return {
        **asdict(quality),
        "true_positive_rate": quality.true_positive_rate,
        "false_positive_rate": quality.false_positive_rate,
        "total_cost_units": quality.total_cost_units,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("policy", type=Path)
    arguments = parser.parse_args()
    suite_value = json.loads(arguments.suite.read_text(encoding="utf-8"))
    comparison = compare_monitored_to_phase18(
        load_adversarial_cases(arguments.suite),
        IntegrityPolicy.from_json(arguments.policy),
        maximum_false_positive_rate=float(suite_value["maximum_false_positive_rate"]),
    )
    print(
        json.dumps(
            {
                "baseline": _quality_dict(comparison.baseline),
                "monitored": _quality_dict(comparison.monitored),
                "maximum_false_positive_rate": comparison.maximum_false_positive_rate,
                "passes_merge_gate": comparison.passes_merge_gate,
            },
            sort_keys=True,
        )
    )
    return 0 if comparison.passes_merge_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
