# Isolated Evaluation and Gates

Phase 17 separates research decisions from private evaluation data. Research
code submits only a campaign ID, an approved artifact SHA-256, and one declared
purpose: optimize, select, or confirm. A fresh evaluator worker receives the
private suite through an inherited file descriptor and returns aggregate scores,
confidence intervals, gate verdicts, and no examples or answer keys.
`EvaluationRequest.from_receipt()` binds that reference directly to a successful
Phase 16 execution receipt; failed executions are not evaluable submissions.

## Benchmark roles and selection

- `optimization` benchmarks provide iterative feedback.
- `validation` benchmarks select a candidate after optimization.
- `test` benchmarks are consumed only after that candidate has a valid selection
  record and are never marked as selection evidence.
- `capability_gate` benchmarks veto statistically confirmed regressions.
- `safety_gate` benchmarks require the declared safety floor to be established
  across the complete confidence interval.

The broker permits one final test per campaign instance. Persistent campaign
coordination must additionally retain selection records in the research ledger;
restarting a broker is not authority to reuse an untouched test.

## Metrics

For baseline `b`, optimum `o`, and score `s`, normalized headroom closed is
`(s - b) / (o - b)`. This also handles lower-is-better metrics when `o < b`.
The declared aggregate rule is `geometric_mean_positive_headroom`: if any
primary benchmark remains at or below baseline, aggregate headroom is zero;
otherwise the geometric mean rewards improvements that span the suite. Every
component and its 95% interval remains visible so the aggregate cannot conceal a
failure.

Gates are independent of aggregate score. Capability gates fail only when their
entire interval is below the registered floor. Safety gates pass only when their
entire interval reaches the floor.

## Deployment boundary

The included broker/worker protocol demonstrates separate-process evaluation on
POSIX systems. In a consequential deployment, a trusted controller must open
the suite under a dedicated evaluator identity, start the broker, and give the
research process only an IPC client. Running research and the broker under the
same OS identity is not adversarial isolation because that identity may inspect
process descriptors or change file permissions.

The private-suite schema documents configuration for trusted evaluator owners;
private instances must not be committed to the research repository. The current
synthetic adapter maps artifact hashes to measurements to test orchestration. A
real adapter must load and evaluate the referenced artifact entirely inside the
trusted boundary.
