"""The search instrument: what comes back, and what it will not parse.

Nothing here opens a socket. `Canned` is the `Fetcher` seam and records the URL it was asked
for, which is how the query-construction tests check the request without making one.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

from g0rd0n.evidence import arxiv
from g0rd0n.instruments.fetch import Fetched, Unreachable
from g0rd0n.instruments.search import ARXIV_API, FIELD, Arxiv, SearchError, parse

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2207.00729v4</id>
    <published>2022-07-02T03:49:34Z</published>
    <title>The Parallelism Tradeoff: Limitations
      of Log-Precision Transformers</title>
    <summary>We prove that transformers whose arithmetic precision
      is logarithmic in the number of input tokens ...</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1411.6730v1</id>
    <published>2014-11-25T00:00:00Z</published>
    <title>Experimental verification of Landauer's principle</title>
    <summary>at least kT ln(2) of heat must be dissipated</summary>
  </entry>
</feed>
"""

EMPTY = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


@dataclass
class Canned:
    """Answers every URL with the same feed, and remembers what it was asked."""

    body: str = FEED
    asked: list[str] = field(default_factory=list)
    fail: bool = False

    def get(self, url: str) -> Fetched:
        self.asked.append(url)
        if self.fail:
            raise Unreachable(f"{url} answered 503 Service Unavailable")
        return Fetched(url=url, content=self.body.encode(), media_type="application/atom+xml")


def query_of(asked: str) -> Mapping[str, str]:
    from urllib.parse import parse_qs, urlparse

    return {key: values[0] for key, values in parse_qs(urlparse(asked).query).items()}


def test_search_results_are_citable_identifiers_not_prose() -> None:
    """Every result is a paper the Evidence Channel already has a URL for.

    That is the whole point of searching a preprint server's own API rather than the web: a
    Cell handed these can misread an abstract, but it cannot conjure a reference, because the
    only references in front of it resolve.
    """
    fetcher = Canned()
    found = Arxiv(fetcher=fetcher).find("log-precision transformers")

    assert [result.identifier for result in found] == ["2207.00729v4", "1411.6730v1"]
    assert all(arxiv(result.identifier).url.startswith(ARXIV_API) for result in found)
    assert arxiv(found[0].identifier).must_contain == "arxiv.org/abs/2207.00729v4"


def test_a_multi_word_query_is_not_an_exact_phrase_search() -> None:
    """The bug this was found with: quoting the query makes arXiv match the whole phrase.

    `all:"log-precision transformers circuit complexity"` returns zero results against the
    live API, which reads as "no such literature exists" rather than as a broken query. The
    query goes in unquoted.
    """
    fetcher = Canned()
    Arxiv(fetcher=fetcher).find("log-precision transformers circuit complexity")

    asked = query_of(fetcher.asked[0])
    assert asked["search_query"] == f"{FIELD}log-precision transformers circuit complexity"
    assert '"' not in asked["search_query"]


def test_a_search_asks_for_the_number_of_results_it_was_told_to() -> None:
    fetcher = Canned()
    Arxiv(fetcher=fetcher).find("landauer", limit=3)

    asked = query_of(fetcher.asked[0])
    assert asked["max_results"] == "3"
    assert asked["sortBy"] == "relevance"


def test_identifiers_keep_their_version() -> None:
    """A claim cites the text it was read from, not whatever the latest revision says."""
    found = Arxiv(fetcher=Canned()).find("transformers")

    assert found[0].identifier.endswith("v4")


def test_wrapped_titles_and_abstracts_come_back_on_one_line() -> None:
    """arXiv wraps them, and a newline in a title ends up in provenance and in note names."""
    found = Arxiv(fetcher=Canned()).find("transformers")

    assert found[0].title == "The Parallelism Tradeoff: Limitations of Log-Precision Transformers"
    assert "\n" not in found[0].summary


def test_an_empty_result_is_an_answer_not_an_error() -> None:
    """ "Nothing matched" is a finding. It is how the audit learned arXiv is the wrong corpus."""
    assert Arxiv(fetcher=Canned(body=EMPTY)).find("no such thing") == ()


def test_a_feed_with_entity_declarations_is_not_parsed() -> None:
    """`xml.etree` expands internal entities, so a hostile feed can cost far more than its size."""
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "boom">]>'
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )

    with pytest.raises(SearchError, match="DOCTYPE"):
        parse(bomb)


def test_an_entry_without_an_arxiv_identifier_is_an_error() -> None:
    """A result with no identifier is a result nothing can cite, which is worse than none."""
    odd = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><id>https://example.com/paper</id></entry></feed>"
    )

    with pytest.raises(SearchError, match="carries no identifier"):
        parse(odd)


def test_a_document_that_parses_is_not_a_result_list_that_arrived() -> None:
    """An HTML error page is well-formed XML, so it parses and finds no entries.

    Without a check on the root element that comes back as "nothing matched" — the same shape
    of lie as a citation resolving because the fetch returned 200.
    """
    with pytest.raises(SearchError, match="rather than an Atom feed"):
        parse("<html><body>503 Service Unavailable</body></html>")

    with pytest.raises(SearchError, match="not an Atom feed"):
        parse("503 Service Unavailable")


def test_an_empty_query_is_refused_before_the_network() -> None:
    fetcher = Canned()

    with pytest.raises(SearchError, match="not a search"):
        Arxiv(fetcher=fetcher).find("   ")
    with pytest.raises(SearchError, match="not a search"):
        Arxiv(fetcher=fetcher).find("landauer", limit=0)
    assert fetcher.asked == []


def test_an_unreachable_arxiv_is_a_search_error() -> None:
    with pytest.raises(SearchError, match="failed"):
        Arxiv(fetcher=Canned(fail=True)).find("landauer")
