# Getting Started with g0rd0n

This tutorial explains the system from the outside in: reproduce a result,
understand the research loop, invoke a resource, make its cost visible, and see
how bounded self-improvement fits around the loop.

g0rd0n is currently a Python research toolkit, not a hosted service. Its default
adapters and experiments are deterministic fixtures so orchestration policies
can be tested without spending money or making network calls.

## 1. Install and verify

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then let it
provision the pinned Python version and locked environment:

```bash
git clone https://github.com/cs0lar/g0rd0n.git
cd g0rd0n
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python -m g0rd0n validate config/mission.json
```

There are no runtime dependencies beyond the standard library. A skipped Linux
RAPL test means the host does not expose a readable energy counter, not that the
suite failed.

`pyproject.toml` is the dependency declaration and `uv.lock` is the exact
resolution used for reproducible development and experiments. Add runtime
packages with `uv add <package>`, development tools with
`uv add --dev <package>`, and commit both files whenever resolution changes.

## 2. Reproduce a scientific result

Run the first repository-local, procedurally pre-registered campaign:

```bash
uv run python -m g0rd0n.campaigns run \
  campaigns/first-discovery/preregistration.json
```

The command emits canonical JSON. The candidate uses fixed two-bit state and is
tested exhaustively on every binary sequence of lengths 1–10. It computes parity
exactly with sparse updates, but exact-recall accuracy falls below its registered
threshold at length 3. A pigeonhole bound explains why: recalling every `L`-bit
prefix requires at least `2^L` distinguishable states, or `L` information bits.
The registration was authored before execution but was not independently
timestamped; the campaign records that limitation rather than claiming stronger
confirmatory status.

This is how the project should fail usefully. The result rejects a candidate
class, avoids an unnecessary trained baseline and hardware run, and produces a
sharper next question. Read the pre-registration and interpretation in
[`campaigns/first-discovery/`](../campaigns/first-discovery/) and
[`first-discovery-campaign.md`](first-discovery-campaign.md).

## 3. Understand the research loop

Every cycle follows the same causal chain:

```text
question -> assumptions -> hypotheses -> predictions
         -> experiment/proof -> observations -> results
         -> adversarial review -> belief update -> next question
```

The governor improves and selects a question, generates competing hypotheses,
and ranks experiments by prediction discrimination divided by declared cost. It
does not trust the proposing resource to choose its own evidence. Raw
observations are stored separately from interpretations, and the append-only
research ledger can reconstruct state from an empty store.

The loop stops when one declared hypothesis survives, continues when useful
discriminating work remains, and escalates when evidence, resources, or budget
cannot support a defensible decision. See
[`research-governor.md`](research-governor.md).

## 4. Resources: programs, models, and humans

A resource is data describing capabilities, typed inputs and outputs, expected
cost, latency, reliability, rate limits, context limits, permissions, and
provenance. The registry handles all kinds through the same invocation sequence:

1. resolve a capability;
2. check permissions and input limits;
3. reserve rate-limit capacity;
4. invoke an adapter with cooperative cancellation;
5. validate output and record estimated and actual cost.

Humans are not a special escape hatch. A human reviewer is a `Resource` with
`kind=ResourceKind.HUMAN`; its capability normally requires
`Permission.HUMAN_ATTENTION`, and `HumanResourceAdapter` connects the request to
the chosen communication backend. A request without that granted permission is
denied before the reviewer is contacted. This makes scarce human attention
visible and schedulable alongside model calls and programs.

A minimal deterministic invocation looks like this:

```python
from g0rd0n.resources import (
    Capability, ContextLimits, Cost, CostModel, FieldSpec,
    InvocationRequest, LatencyModel, Permission, RateLimit,
    Resource, ResourceKind, ResourceRegistry,
)
from g0rd0n.resources.fakes import DeterministicFakeAdapter, fixed_result

review = Resource(
    id="human:reviewer",
    kind=ResourceKind.HUMAN,
    capabilities=(Capability(
        id="review",
        description="Review a surprising result",
        inputs=(FieldSpec("claim", "string"),),
        outputs=(FieldSpec("decision", "string"),),
        required_permissions=frozenset({Permission.HUMAN_ATTENTION}),
    ),),
    cost_model=CostModel(Cost(calls=1, wall_time_ms=300_000)),
    reliability=1.0,
    rate_limit=RateLimit(4, 3_600),
    latency_model=LatencyModel(60_000, 600_000),
    context_limits=ContextLimits(10_000, 10_000),
    permissions=frozenset({Permission.HUMAN_ATTENTION}),
    provenance="local review policy",
)

registry = ResourceRegistry()
registry.register(
    review,
    DeterministicFakeAdapter({"review": fixed_result({"decision": "replicate"})}),
)
result = registry.invoke(InvocationRequest(
    "human:reviewer",
    "review",
    {"claim": "candidate dominates the baseline"},
    frozenset({Permission.HUMAN_ATTENTION}),
))
print(result.status, result.actual_cost)
```

The fake adapter is appropriate for learning and tests. A real integration wraps
a consented review channel with `HumanResourceAdapter`; model and program
integrations use the corresponding thin adapters. Provider logic stays outside
the registry. See [`resource-registry.md`](resource-registry.md).

## 5. Transparent cost and stopping rules

`BudgetEngine` sits in front of invocation. Each research action declares an
estimate and a conservative maximum. The engine atomically reserves the maximum
against both session and program hard limits, preventing concurrent actions from
overcommitting the budget. It then settles actual currency micros, tokens, API
calls, and wall time into a hash-chained `CostLedger`.

Soft limits warn; hard limits deny before execution. Failed calls are charged if
provider work began. Preflight denials cost zero but remain visible. Stop
conditions can cap cost dimensions, action count, or failure count, and
`BudgetEngine.report()` renders estimated-versus-actual variance for humans.

CPU/GPU time, energy, and human attention also appear in research-program final
reports. Energy measurement is deliberately separate because meaningful joule
comparisons require matching system boundaries and uncertainty. Logical reads
or updates alone never justify a watt claim.

## 6. Adversarial science and durable knowledge

For every promoted hypothesis, the adversarial loop requests the strongest
competing explanation, hidden assumptions, known failure modes, and cheapest
falsifier. Generator, critic, falsifier, and replicator are roles—not necessarily
separate models. A single backend may fill all four, while their outputs remain
epistemically distinct.

Research events are immutable and hash chained. Raw artifacts are content
addressed; results point back to observations; claims point to evidence and
proof obligations. `KnowledgeStore` provides temporal assertions, conflicts,
supersession, and provenance through replaceable in-memory or `knk` adapters.
The Obsidian projection creates deterministic human-readable notes while
preserving marked human-owned regions.

## 7. How self-improvement works

Self-improvement changes research strategy, never the mission or success
criteria. `AdaptiveResourceTopology` represents allocation policy and topology
as data. For each workload family it estimates:

```text
expected research progress / expected total resource cost
```

It can activate a resource, reuse it, record observed progress and cost, or
retire it after enough poor evidence. Exploration bonuses permit bounded trials
of uncertain resources. Checkpoints capture the strategy, active resources,
observations, and action log; rollback restores the previous state.

Acceptance requires held-out comparison with a fixed policy. The repository's
adaptive-policy evidence is synthetic, so it demonstrates mechanics rather than
real-world research improvement. Until credible held-out episodes show an
advantage, the simpler fixed governor remains the default. This is a key safety
invariant: adaptation earns deployment through evidence and remains reversible.

## 8. Bounded autonomous programs

`ResearchProgramSpec` combines a question, candidate hypotheses, ordered
experiments, multidimensional budget, retry policy, and human-review gates.
`ProgramJournal` checkpoints complete state after every consequential event, so
a process can pause, replay, resume, or escalate without silently losing failed
work or spent resources.

Human-gated experiments wait without invoking an executor. Review rejection,
budget denial, repeated failure, and provider cost-contract violations follow
the declared escalation policy. Every exit produces the same audit report:
question, hypotheses, experiments, evidence, claim changes, failures, costs,
unresolved uncertainty, and best next question.

## 9. Where to go next

- Reproduce toy baselines with
  `uv run python -m g0rd0n.evaluation run <manifest>`.
- Verify a proof with `uv run python -m g0rd0n.proofs verify <artifact>`.
- Read [`paradigm-spec.md`](paradigm-spec.md) before adding an architecture.
- Read [`energy-accounting.md`](energy-accounting.md) before making efficiency
  comparisons.
- Follow the PR review contract and testing hierarchy in [`AGENTS.md`](../AGENTS.md).

The next scientific question produced by the first campaign asks which adaptive
external-memory gating primitives retain sparse update cost while allocating
capacity only when recall demands it. A responsible next experiment should
pre-register candidates, strong neural baselines, held-out task families,
resource limits, energy boundaries, and cheap falsifiers before implementation.
