"""The fetch instrument: what it will not reach, and what it refuses to keep.

Nothing here opens a socket. The allowlist checks are pure, and the redirect check is run
against a real `urllib` redirect handler with a fake response, which is the part that would
otherwise only be checked by trusting the library.
"""

import hashlib
import io
import urllib.error
import urllib.request
from http.client import HTTPMessage

import pytest

from g0rd0n.instruments import fetch

ALLOWED = ("arxiv.org", "export.arxiv.org")


def test_a_host_outside_the_allowlist_is_refused_before_the_request() -> None:
    with pytest.raises(fetch.NetworkRefused, match="not on the network allowlist"):
        fetch.check_host("https://example.com/paper", ALLOWED)

    fetch.check_host("https://arxiv.org/abs/1706.03762", ALLOWED)


def test_the_allowlist_has_no_subdomain_wildcards() -> None:
    """A rule that allows `*.arxiv.org` allows a host nobody listed."""
    with pytest.raises(fetch.NetworkRefused):
        fetch.check_host("https://evil.arxiv.org.attacker.net/x", ALLOWED)
    with pytest.raises(fetch.NetworkRefused):
        fetch.check_host("https://cdn.arxiv.org/x", ALLOWED)


def test_a_url_with_no_host_is_refused() -> None:
    with pytest.raises(fetch.NetworkRefused, match="names no host"):
        fetch.check_host("file:///etc/passwd", ALLOWED)


def test_an_empty_allowlist_reaches_nothing() -> None:
    with pytest.raises(fetch.NetworkRefused, match=r"\(nothing\)"):
        fetch.check_host("https://arxiv.org/abs/1706.03762", ())


def test_a_redirect_off_the_allowlist_is_refused_mid_flight() -> None:
    """`urlopen` follows redirects silently, so the first URL is not the only one that matters.

    `doi.org` is on the shipped allowlist precisely because it redirects, so this is the
    ordinary case rather than an adversarial one: a citation resolved through a redirector
    lands wherever the publisher points it.
    """
    handler = fetch._Allowlisted(ALLOWED)
    request = urllib.request.Request("https://arxiv.org/abs/1706.03762")
    headers = HTTPMessage()

    with pytest.raises(fetch.NetworkRefused, match="not on the network allowlist"):
        handler.redirect_request(
            request, io.BytesIO(b""), 302, "Found", headers, "https://elsewhere.example/paper"
        )

    followed = handler.redirect_request(
        request,
        io.BytesIO(b""),
        302,
        "Found",
        headers,
        "https://export.arxiv.org/api/query?id_list=1706.03762",
    )
    assert followed is not None


def test_a_fetched_body_carries_the_hash_of_exactly_those_bytes() -> None:
    body = b"<feed>arxiv.org/abs/1706.03762</feed>"
    fetched = fetch.Fetched(url="https://export.arxiv.org/x", content=body, media_type="text/xml")

    assert fetched.digest == hashlib.sha256(body).hexdigest()
    assert "1706.03762" in fetched.text


def test_undecodable_bytes_do_not_stop_a_citation_resolving() -> None:
    """`text` replaces rather than raises: a mislabelled encoding is not a fabricated source."""
    fetched = fetch.Fetched(
        url="https://arxiv.org/x", content=b"\xff\xfeabs/1706.03762", media_type="text/xml"
    )

    assert "abs/1706.03762" in fetched.text


def test_an_http_error_is_a_fetch_error_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing:
        def open(self, request: object, timeout: float) -> object:
            raise urllib.error.HTTPError(
                "https://arxiv.org/x", 404, "Not Found", HTTPMessage(), None
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: Failing())
    with pytest.raises(fetch.Unreachable, match="404"):
        fetch.Http(allowlist=ALLOWED).get("https://arxiv.org/x")


def test_the_user_agent_carries_no_contact_address() -> None:
    """Politeness is not a reason to put the operator's email on the wire."""
    assert "@" not in fetch.USER_AGENT
    assert "g0rd0n" in fetch.USER_AGENT
