# First Discovery Campaign: Fixed State and Exact Recall

## Pre-registration

The repository-local pre-registration in
`campaigns/first-discovery/preregistration.json` was authored before executing
the campaign, but it has no independent timestamping authority. It fixes the
question, two task families, candidate class, baselines, exhaustive lengths,
resource limits, logical energy boundary, success threshold, falsifiers, and
stop-before-scale rule.

## Prior-art map

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762) defines the
  Transformer attention baseline and reports self-attention complexity by
  sequence length.
- [Transformers are RNNs](https://arxiv.org/abs/2006.16236) shows that kernelized
  attention admits recurrent linear-complexity execution; recurrence itself is
  therefore not a novel separation.
- [Structured State Spaces (S4)](https://arxiv.org/abs/2111.00396) provides a
  strong prior example of efficient fixed-dimensional state-space sequence
  modeling.
- [State-Regularized RNNs](https://proceedings.mlr.press/v97/wang19j.html)
  distinguishes regular-language behavior from copy tasks where external
  memory is required.

These papers motivate testing the boundary of fixed state, not claiming that
sparse recurrence is absent from contemporary neural research.

## Result

The two-bit candidate is perfect on exhaustive online parity for lengths 1–10.
It fails exact delayed recall immediately at length 3: accuracy is 0.5 against
the pre-registered 0.99 threshold, then halves with every additional bit. The
exact-history control remains perfect while retaining and reading `L` bits.

The lower bound explains the result. Exact recall has `2^L` possible prefixes.
A deterministic `b`-bit state has at most `2^b` states. When `L > b`, two
prefixes collide; after the same delay, a deterministic machine must emit the
same output for both and cannot recall both exactly. Thus exact arbitrary recall
requires `b >= L` information bits.

The canonical result hash reproduces across two complete exhaustive runs. This
is a negative result for fixed persistent state without external memory—not for
event-driven systems with adaptive memory.

## Stopping decision and revised question

The candidate class met the parity resource prediction but violated transfer.
Per the pre-registration, the paid/trained Transformer baseline, hardware energy
measurement, and scaling experiments were not run. Logical access counts do not
support a joule, watt, or 20 W claim.

The next question is: **Which adaptive external-memory gating primitives retain
sparse constant update cost while allocating information capacity only when
exact recall demands it?**
