"""Instruments: tools that return results and never commit assertions.

Six modules. `fetch` opens sockets and owns the network allowlist; `search` queries arXiv and
can only hand back papers with identifiers; `tasks` is the three chartered task families, each
a generator, a size and a checker hashed together; `capability` turns the scores those
checkers produce into the Charter's `cap`; `meter` says what read a joule and how far off it
was; `bench` says what a joule figure and a `cap` are allowed to be reported as. The prover
and the sandbox arrive with their own phases.

The rule that defines this layer is AGENTS.md §6: **an instrument returns a result, and a
Cell commits it.** Nothing here imports the bridge, and nothing here decides what is true —
an instrument that could commit its own findings would let a fetch become a belief without
anything in between having to say where it came from. The bench is the same rule with more at
stake: a measurement that could write itself into the kernel is a measurement with no step at
which anybody checked the meter was plugged in.

Depends on `config` and `content` and nothing else in `g0rd0n`, so `cells` can depend on it
downwards.

Deletion criterion: this package holds the wager that g0rd0n cannot reach a host nobody
allowed, cannot turn a retrieval into a belief on its own, and cannot report a capability it
did not measure. Delete it and `a_redirect_off_the_allowlist_is_refused_mid_flight` and
`a_single_size_is_an_accuracy_not_a_curve` lose their verdicts, the allowlist moves back
inside whatever library happens to open the socket, and a benchmark score goes back to being
a number in a slide.
"""

from g0rd0n.instruments.bench import (
    Budget,
    Comparison,
    Expenditure,
    Result,
    compare,
    expenditure,
)
from g0rd0n.instruments.capability import (
    CONFIDENCE,
    MINIMUM,
    Curve,
    Point,
    cap,
    curve,
    interval,
    margin,
)
from g0rd0n.instruments.fetch import (
    MAX_BYTES,
    Fetched,
    Fetcher,
    FetchError,
    Http,
    NetworkRefused,
    Unreachable,
    check_host,
)
from g0rd0n.instruments.meter import (
    CALIBRATION_SECONDS,
    Basis,
    Calibration,
    Instrument,
    Joules,
    MeterError,
    Rapl,
    Role,
    Session,
    counters,
    delta,
    estimated,
    session,
)
from g0rd0n.instruments.search import (
    DEFAULT_LIMIT,
    Arxiv,
    Found,
    Search,
    SearchError,
)
from g0rd0n.instruments.tasks import (
    FAMILIES,
    Family,
    Instance,
    InstanceSet,
    TaskError,
    family,
    instances,
)

__all__ = [
    "CALIBRATION_SECONDS",
    "CONFIDENCE",
    "DEFAULT_LIMIT",
    "FAMILIES",
    "MAX_BYTES",
    "MINIMUM",
    "Arxiv",
    "Basis",
    "Budget",
    "Calibration",
    "Comparison",
    "Curve",
    "Expenditure",
    "Family",
    "FetchError",
    "Fetched",
    "Fetcher",
    "Found",
    "Http",
    "Instance",
    "InstanceSet",
    "Instrument",
    "Joules",
    "MeterError",
    "NetworkRefused",
    "Point",
    "Rapl",
    "Result",
    "Role",
    "Search",
    "SearchError",
    "Session",
    "TaskError",
    "Unreachable",
    "cap",
    "check_host",
    "compare",
    "counters",
    "curve",
    "delta",
    "estimated",
    "expenditure",
    "family",
    "instances",
    "interval",
    "margin",
    "session",
]
