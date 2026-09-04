# g0rd0n

`g0rd0n` is an experimental scientific orchestration system for formulating,
testing, and auditing resource-bounded alternatives to contemporary neural
architectures. Its central question is not whether one universal computer can
compute something another cannot, but whether a computable architecture can
show a strict capability advantage under explicit limits on data, memory,
compute, adaptation, latency, or energy.

> **Project status:** early research prototype. The repository provides tested
> scientific infrastructure and toy results; it does not contain AGI and makes
> no general superiority or 20 W hardware claim.

## Why g0rd0n?

Research claims are easy to overstate when questions, costs, failed experiments,
and changing assumptions live in separate systems. g0rd0n keeps them connected:

- immutable research events and content-addressed evidence;
- humans, models, programs, provers, and hardware behind one permissioned
  resource interface;
- hard and soft budgets with estimated-versus-actual cost reports;
- deterministic experiment selection and adversarial falsification;
- reproducible baselines, energy boundaries, and proof artifacts;
- checkpointed, reversible adaptation of resource-allocation strategies.

The design favors small, inspectable mechanisms over a heavyweight agent
framework. Roles are data, claims retain proof obligations, and negative results
are first-class outputs.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/).
uv installs the pinned Python 3.12 toolchain when necessary, creates the virtual
environment, and reproduces the dependency set in `uv.lock`.

```bash
git clone https://github.com/cs0lar/g0rd0n.git
cd g0rd0n
uv sync --locked
uv run python -m unittest discover -s tests -v
```

Validate the mission and reproduce the first discovery campaign:

```bash
uv run python -m g0rd0n validate config/mission.json
uv run python -m g0rd0n.campaigns run \
  campaigns/first-discovery/preregistration.json
```

The campaign exhaustively tests a two-bit event-driven candidate. It succeeds
on online parity but is falsified for exact delayed recall at length three,
narrowing the next question to adaptively gated external memory.

For a guided walkthrough, including human resources, budgets, governance, and
self-improvement, read [Getting Started](docs/getting-started.md).

## Architecture

```text
Mission + question
       |
Research governor ---- Budget engine
       |                    |
Resource registry      Cost ledger
(human/model/tool)          |
       |                    |
       +---- Evidence ledger + KnowledgeStore
                         |
              evaluation / proof / vault views
```

Core packages are organized by responsibility:

| Path | Purpose |
| --- | --- |
| `g0rd0n/research/` | Immutable events, replay, provenance, and artifacts |
| `g0rd0n/resources/` | Uniform capabilities, permissions, and invocation |
| `g0rd0n/budget/` | Preflight limits and durable cost accounting |
| `g0rd0n/governor/` | Question, experiment, adversarial, and allocation policies |
| `g0rd0n/evaluation/` | Reproducible baselines, statistics, and energy accounting |
| `g0rd0n/evaluation/isolation.py` | Aggregate-only private evaluation and regression gates |
| `g0rd0n/programs/` | Resumable, human-gated research programs |
| `g0rd0n/methods/` | Frozen proposals bound to reviewed executable artifacts |
| `g0rd0n/memory/` | Durable survey, findings forum, leaderboard, and fresh-session briefing |
| `g0rd0n/integrity/` | Versioned controls, trajectory monitoring, quarantine, and appeals |
| `g0rd0n/ablation/` | Paired harness ablation, held-out adoption, sensitivity, and rollback |
| `g0rd0n/proofs/` | Formal claims, proof artifacts, and verification |
| `g0rd0n/campaigns/` | Pre-registered mission-facing investigations |

JSON contracts live in `schemas/`; reproducible inputs live in `config/`,
`benchmarks/`, `proofs/`, and `campaigns/`.

## Reproducible commands

```bash
# Run a pinned toy baseline
uv run python -m g0rd0n.evaluation run \
  benchmarks/manifests/toy-affine-candidate.json

# Independently check the bundled toy separation proof
uv run python -m g0rd0n.proofs verify \
  proofs/toy-direct-address-membership.json

# Compile and test all Python modules
uv run python -m compileall -q g0rd0n tests
uv run python -m unittest discover -s tests -v
```

Use `uv add <package>` for runtime dependencies and `uv add --dev <package>`
for development tools. Commit the resulting `pyproject.toml` and `uv.lock`
changes together; use `uv lock --check` to detect an outdated lockfile.

Linux RAPL energy tests run only when readable package counters are available;
otherwise that host-specific test is skipped.

## Scientific boundaries

- Resource-bounded separation is the default interpretation of “more capable.”
- Logical operation counts are not silently converted into joules or watts.
- Adaptive scheduling has only synthetic evidence so far; fixed orchestration
  remains the conservative default for real research.
- The `knk` integration is optional and replaceable through `KnowledgeStore`.
- External providers require adapters, explicit permissions, and declared costs.

See [AGENTS.md](AGENTS.md) for the mission, roadmap, review protocol, and full
definition of done. Focused design notes are indexed in [`docs/`](docs/).

## Contributing

Open an issue before undertaking a large experiment or abstraction. Keep changes
small, deterministic where practical, and paired with the cheapest meaningful
test. Pull requests must state the question, hypothesis, evidence, falsifier,
cost, complexity delta, reversibility, and new knowledge. Preserve unrelated
work and never erase negative or conflicting evidence.

## Security and responsible operation

Use least privilege. Do not place credentials in manifests, ledgers, fixtures,
or generated vault notes. Treat model output as a proposal, require explicit
authorization for external writes, and retain human approval for exceptional
budgets or consequential actions. Please report sensitive vulnerabilities
privately to the repository maintainers rather than opening a public issue.

## License

No license file is currently included. Until one is added, the repository is
publicly visible but no open-source license grant should be assumed.
