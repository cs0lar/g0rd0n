"""Run the pre-registered harness ablation and held-out adoption check."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from g0rd0n.research.ledger import canonical_json

from .analysis import run_study
from .models import AblationSpec, HarnessConfiguration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("defaults", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    spec = AblationSpec.from_json(arguments.spec, repository_root=arguments.repository_root)
    study = run_study(spec)
    configured = HarnessConfiguration.from_json(arguments.defaults)
    configuration_matches = configured == study.adoption.default_configuration
    report = {
        "study_id": spec.id,
        "selection": {
            "baseline": asdict(study.selection.baseline.metrics),
            "cumulative": [
                {"configuration": item.configuration.id, "metrics": asdict(item.metrics)}
                for item in study.selection.cumulative
            ],
            "components": [
                {"configuration": item.configuration.id, "metrics": asdict(item.metrics)}
                for item in study.selection.components
            ],
            "human_ideas": asdict(study.selection.human_baseline.metrics),
        },
        "adoption": [asdict(item) for item in study.adoption.decisions],
        "held_out": {
            "baseline": asdict(study.held_out.baseline.metrics),
            "adopted": asdict(study.held_out.adopted.metrics),
            "progress_per_cost": asdict(study.held_out.progress_per_cost),
            "transfer": asdict(study.held_out.transfer),
            "component_evidence": [asdict(item) for item in study.held_out.component_evidence],
        },
        "sensitivity": [asdict(item) for item in study.sensitivity],
        "configuration_matches": configuration_matches,
        "rollback": asdict(study.adoption.rollback_configuration()),
        "passes_merge_gate": study.passes_merge_gate and configuration_matches,
    }
    print(canonical_json(report).decode("utf-8"))
    return 0 if report["passes_merge_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
