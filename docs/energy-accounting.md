# Energy Accounting Laboratory

Energy results are meaningful only within a declared physical boundary. An
`EnergyProfile` therefore records included and excluded components, whether the
value was measured or modelled, and the uncertainty basis alongside idle,
active, and average power, joules per task/update, and energy-delay product.

`measure_energy()` takes two idle readings and brackets the workload with two
active readings. Meters may be deterministic models or real counters. On Linux,
`LinuxRaplEnergyMeter.discover()` uses top-level powercap package counters when
available and deliberately excludes nested zones to prevent double-counting.
RAPL is a package boundary, not a whole-system measurement.

Scaling projections retain uncertainty and combine observed idle power with
both utilization and task-rate estimates. They are projections, not measured
20 W claims.

Energy Pareto comparison requires identical `SystemBoundary` values. A
chip/package result cannot be compared with a wall-socket or whole-system result
until both workloads are remeasured at a common boundary.
