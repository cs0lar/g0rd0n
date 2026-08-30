"""Instruments: tools that return results and never commit assertions.

Two modules. `fetch` opens sockets and owns the network allowlist; `search` queries arXiv and
can only hand back papers with identifiers. The bench, the prover, and the sandbox arrive with
their own phases.

The rule that defines this layer is AGENTS.md §6: **an instrument returns a result, and a
Cell commits it.** Nothing here imports the bridge, and nothing here decides what is true —
an instrument that could commit its own findings would let a fetch become a belief without
anything in between having to say where it came from.

Depends on `config` and nothing else in `g0rd0n`, so `cells` can depend on it downwards.

Deletion criterion: this package holds the wager that g0rd0n cannot reach a host nobody
allowed and cannot turn a retrieval into a belief on its own. Delete it and the allowlist
moves back inside whatever library happens to open the socket, which loses the verdict on
`a_redirect_off_the_allowlist_is_refused_mid_flight` and on every later claim that a fetched
number came from where it says it did.
"""

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
from g0rd0n.instruments.search import (
    DEFAULT_LIMIT,
    Arxiv,
    Found,
    Search,
    SearchError,
)

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_BYTES",
    "Arxiv",
    "FetchError",
    "Fetched",
    "Fetcher",
    "Found",
    "Http",
    "NetworkRefused",
    "Search",
    "SearchError",
    "Unreachable",
    "check_host",
]
