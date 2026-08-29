"""Human-readable baseline and Pareto reporting."""

from __future__ import annotations

import statistics
from typing import Mapping, Sequence

from .analysis import Comparison
from .harness import BenchmarkResult
from .manifest import BaselineManifest


def markdown_report(
    manifests: Sequence[BaselineManifest],
    results: Sequence[BenchmarkResult],
    comparisons: Sequence[Comparison] = (),
    pareto_ids: Sequence[str] = (),
) -> str:
    by_id: Mapping[str, BaselineManifest] = {manifest.id: manifest for manifest in manifests}
    lines = ["# Baseline laboratory report", ""]
    for result in results:
        manifest = by_id[result.manifest_id]
        primary = manifest.benchmark.primary_metric
        values = result.metric_values(primary)
        lines.extend(
            [
                f"## {manifest.id}",
                "",
                f"- Role/family: `{manifest.role}` / `{manifest.family.value}`",
                f"- Implementation: `{manifest.implementation}` `{manifest.implementation_version}`",
                f"- Model revision: `{manifest.model_revision}`",
                f"- Benchmark: `{manifest.benchmark.id}` (`{manifest.benchmark.task_family.value}`)",
                f"- Study stage: `{manifest.benchmark.stage.value}`",
                f"- Primary metric mean: {statistics.mean(values):.6g}",
                f"- Seeds: {', '.join(str(trial.seed) for trial in result.trials)}",
                f"- Captured Python: `{result.environment.python_version}`",
                f"- Captured platform: `{result.environment.operating_system}`",
                f"- Energy boundary: {manifest.energy_boundary}",
                "",
            ]
        )
    if comparisons:
        lines.extend(["## Statistical comparisons", ""])
        for comparison in comparisons:
            lines.append(
                f"- `{comparison.metric}` improvement={comparison.mean_improvement:.6g}, "
                f"95% bootstrap CI=[{comparison.confidence_interval_95[0]:.6g}, "
                f"{comparison.confidence_interval_95[1]:.6g}], "
                f"paired randomization p={comparison.randomization_p_value:.6g}"
            )
        lines.append("")
    lines.extend(["## Pareto front", "", *(f"- `{item}`" for item in pareto_ids), ""])
    return "\n".join(lines)
