import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from g0rd0n.evaluation.energy import (
    CapabilityCostEnergyRecord,
    EnergyReading,
    EnergyUncertainty,
    LinuxRaplEnergyMeter,
    MeasurementMethod,
    SyntheticEnergyMeter,
    SystemBoundary,
    energy_pareto_front,
    measure_energy,
    project_power,
)


BOUNDARY = SystemBoundary(
    "modelled-whole-system",
    ("cpu", "memory", "storage", "control"),
    ("display",),
)
UNCERTAINTY = EnergyUncertainty(0.1, "synthetic model error bound")


def profile(active_joules=20.0):
    meter = SyntheticEnergyMeter(
        (
            EnergyReading(0.0, 0),
            EnergyReading(5.0, 1_000_000_000),
            EnergyReading(5.0, 1_000_000_000),
            EnergyReading(5.0 + active_joules, 3_000_000_000),
        ),
        boundary=BOUNDARY,
        uncertainty=UNCERTAINTY,
    )
    result, measured = measure_energy(meter, lambda: "complete", task_count=4, learned_updates=2)
    return result, measured


class EnergyAccountingTests(unittest.TestCase):
    def test_synthetic_meter_reports_complete_energy_profile(self):
        result, measured = profile()
        self.assertEqual(result, "complete")
        self.assertEqual(measured.method, MeasurementMethod.MODELLED)
        self.assertEqual(measured.idle_power_watts, 5.0)
        self.assertEqual(measured.active_power_watts, 10.0)
        self.assertAlmostEqual(measured.average_power_watts, 25 / 3)
        self.assertEqual(measured.joules_per_task, 5.0)
        self.assertEqual(measured.joules_per_learned_update, 10.0)
        self.assertEqual(measured.energy_delay_product_joule_seconds, 40.0)

    def test_counter_wrap_is_accounted_for(self):
        meter = SyntheticEnergyMeter(
            (
                EnergyReading(95.0, 0),
                EnergyReading(2.0, 1_000_000_000),
                EnergyReading(2.0, 1_000_000_000),
                EnergyReading(12.0, 2_000_000_000),
            ),
            boundary=BOUNDARY,
            uncertainty=UNCERTAINTY,
            maximum_joules=100.0,
        )
        _, measured = measure_energy(meter, lambda: None, task_count=1)
        self.assertEqual(measured.idle_power_watts, 7.0)
        self.assertEqual(measured.active_energy_joules, 10.0)

    def test_projection_preserves_uncertainty_and_idle_floor(self):
        _, measured = profile()
        projection = project_power(measured, tasks_per_second=2, utilization=0.5)
        self.assertEqual(projection.projected_power_watts, 15.0)
        self.assertEqual(projection.uncertainty_watts, 1.5)
        with self.assertRaises(ValueError):
            project_power(measured, tasks_per_second=1, utilization=1.1)

    def test_pareto_record_combines_capability_cost_and_energy(self):
        _, baseline_energy = profile(40.0)
        _, candidate_energy = profile(20.0)
        records = (
            CapabilityCostEnergyRecord("baseline", 0.7, 2.0, baseline_energy),
            CapabilityCostEnergyRecord("candidate", 0.9, 1.0, candidate_energy),
        )
        self.assertEqual(energy_pareto_front(records), ("candidate",))
        incompatible = replace(
            baseline_energy,
            boundary=SystemBoundary("cpu-chip", ("cpu",), ("memory", "storage")),
        )
        with self.assertRaisesRegex(ValueError, "identical system boundaries"):
            energy_pareto_front((records[1], CapabilityCostEnergyRecord("chip", 1.0, 0.5, incompatible)))

    def test_linux_rapl_discovers_only_package_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "intel-rapl:0"
            nested = package / "intel-rapl:0:0"
            package.mkdir()
            nested.mkdir()
            (package / "energy_uj").write_text("1500000", encoding="utf-8")
            (package / "max_energy_range_uj").write_text("100000000", encoding="utf-8")
            (nested / "energy_uj").write_text("500000", encoding="utf-8")
            meter = LinuxRaplEnergyMeter.discover(root)
            self.assertIsNotNone(meter)
            assert meter is not None
            self.assertEqual(meter.read().joules, 1.5)
            self.assertEqual(meter.maximum_joules, 100.0)
            self.assertEqual(meter.boundary.included_components, ("cpu_package:intel-rapl:0",))

    def test_real_host_path_reads_when_supported(self):
        meter = LinuxRaplEnergyMeter.discover()
        if meter is None:
            self.skipTest("Linux powercap package counter is not exposed or readable")
        self.assertGreaterEqual(meter.read().joules, 0)


if __name__ == "__main__":
    unittest.main()
