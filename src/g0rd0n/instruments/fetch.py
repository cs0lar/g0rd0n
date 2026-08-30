"""Fetching: the one place g0rd0n opens a socket to anywhere but the model endpoint.

An instrument, so it returns bytes and commits nothing (AGENTS.md §6). What it does own is the
**network allowlist**, which lives here rather than beside the model provider because the
allowlist guards egress and this is the egress layer — a Cell reaching a paper and a Cell
reaching Anthropic go out through the same rule, and a rule enforced in two places is a rule
that will eventually be enforced in one.

Three things this module refuses, all of them before or during the request rather than after:

- **A host nobody allowed.** Exact hostname match, no subdomain wildcards. A rule that allows
  `*.example.com` allows a host nobody listed.
- **A redirect to a host nobody allowed.** Checked on every hop, not just the first. This is
  not hypothetical: `doi.org` exists to redirect, so a citation resolved through it lands
  wherever the publisher says. An allowlist checked only on the URL you typed is decoration.
- **A response larger than `MAX_BYTES`.** A metadata record is kilobytes; anything reaching
  this bound is a dataset that arrived by accident, and reading it costs memory nobody
  budgeted.

Hand-rolled over `urllib`, no SDK, for the reason `cells/model.py` gives: whatever opens the
socket decides where the bytes go, so the check has to sit immediately above it.

Deletion criterion: this module holds the wager that g0rd0n cannot reach a host nobody
allowed, by any route. Delete it and `a_host_outside_the_allowlist_is_refused_before_the_
request` and `a_redirect_off_the_allowlist_is_refused_mid_flight` both lose their verdicts,
and egress moves inside a library where no test of ours can watch it happen.
"""

import hashlib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO, Protocol

from g0rd0n import __version__

DEFAULT_TIMEOUT_SECONDS = 30.0

#: The largest response this will read. A citation resolves to a metadata record, not a
#: corpus; anything past this is something nobody meant to ask for.
MAX_BYTES = 8 * 1024 * 1024

#: Sent on every request. No contact address: the operator's email is theirs, and a polite
#: header is not a reason to put it on the wire.
USER_AGENT = f"g0rd0n/{__version__} (research instrument; https://github.com/cs0lar/g0rd0n)"


class FetchError(Exception):
    """Something outside g0rd0n could not be read, or would not be asked for."""


class NetworkRefused(FetchError):
    """The request would have gone to a host the config does not allow. Nothing was sent."""


class Unreachable(FetchError):
    """The host was allowed, and could not be read anyway."""


@dataclass(frozen=True)
class Fetched:
    """What came back, and the hash of exactly those bytes.

    The digest is the point. A citation is only resolved if somebody can go and look at the
    same thing later, and `sha256` is what makes "the same thing" checkable rather than
    asserted.
    """

    url: str
    content: bytes
    media_type: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def text(self) -> str:
        """The body as text, replacing anything undecodable rather than raising.

        Used for the `must_contain` check, which is a search for a known-ASCII identifier.
        A citation must not fail to resolve because a publisher mislabelled its encoding.
        """
        return self.content.decode("utf-8", errors="replace")


class Fetcher(Protocol):
    """The seam. Tests pass a stub; nothing in the test suite opens a socket."""

    def get(self, url: str) -> Fetched: ...


@dataclass(frozen=True)
class Http:
    """The real one. Holds the allowlist, because the allowlist is what makes it safe."""

    allowlist: tuple[str, ...]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def get(self, url: str) -> Fetched:
        """GET one URL, or raise. Never retries — see `cells/model.py` for why."""
        check_host(url, self.allowlist)
        opener = urllib.request.build_opener(_Allowlisted(self.allowlist))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                content = response.read(MAX_BYTES + 1)
                media_type = str(response.headers.get_content_type())
                final = str(response.geturl())
        except NetworkRefused:
            raise
        except urllib.error.HTTPError as exc:
            raise Unreachable(f"{url} answered {exc.code} {exc.reason}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise Unreachable(f"{url} could not be read: {exc}") from exc

        if len(content) > MAX_BYTES:
            raise Unreachable(f"{url} is larger than {MAX_BYTES} bytes; nothing was kept")
        return Fetched(url=final, content=content, media_type=media_type)


def check_host(url: str, allowlist: Sequence[str]) -> None:
    """Raise `NetworkRefused` unless `url`'s host is on the allowlist. Called before sending.

    Exact hostname match, with no subdomain wildcards: a rule that allows `*.example.com`
    allows a host nobody listed, and this is the boundary where "nobody decided that" is
    most expensive.
    """
    host = urllib.parse.urlparse(url).hostname
    if host is None:
        raise NetworkRefused(f"{url!r} names no host")
    if host not in allowlist:
        allowed = ", ".join(allowlist) or "(nothing)"
        raise NetworkRefused(
            f"{host} is not on the network allowlist, which has {allowed}; nothing was sent"
        )


class _Allowlisted(urllib.request.HTTPRedirectHandler):
    """A redirect handler that re-checks the allowlist on every hop.

    `urlopen` follows redirects silently, so without this the allowlist would only constrain
    the first URL. `doi.org` is on the allowlist precisely because it redirects, which makes
    this the ordinary case rather than the adversarial one.
    """

    def __init__(self, allowlist: Sequence[str]) -> None:
        super().__init__()
        self._allowlist = tuple(allowlist)

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        check_host(newurl, self._allowlist)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
