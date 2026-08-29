# Resource Registry and Invocation Boundary

Phase 05 models humans, models, programs, theorem provers, simulators, knowledge
sources, channels, and hardware targets as `Resource` data. A resource declares
capabilities, typed input/output fields, fixed preflight cost, reliability,
permissions, rate limits, context limits, provenance, and descriptive latency
and historical-performance fields.

`ResourceRegistry` performs the same sequence for every invocation:

1. resolve resource and capability;
2. enforce explicit permissions;
3. validate input shape and context size;
4. reserve rate-limit capacity;
5. invoke through a cooperative cancellation token;
6. enforce timeout, output shape, and output size;
7. append an `InvocationResult` with estimated and actual cost.

Denied, invalid, rate-limited, cancelled, timed-out, failed, and successful
requests are all visible in invocation history. Preflight failures have zero
actual cost; once adapter execution starts, the estimate is charged unless the
adapter returns a more accurate cost. Phase 06 will extend this accounting into
durable budget governance.

## Adapter boundary

All providers implement the small `ResourceAdapter` protocol. Thin
`ModelResourceAdapter`, `ProgramResourceAdapter`, and `HumanResourceAdapter`
wrappers give provider code a clear integration point without introducing
provider branches into the registry. `DeterministicFakeAdapter` supports cheap,
repeatable tests.

Timeout cancellation is cooperative for generic in-process adapters: the token
is set and control returns, but Python cannot forcibly terminate a thread.
Program adapters that own subprocesses should terminate those processes when the
token is cancelled. Adapters must not publish external side effects after
cancellation.
