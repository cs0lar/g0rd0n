"""Searching the literature: arXiv, and only in a shape that can be cited back.

AGENTS.md §Phase 6 asks for "search and fetch against the allowlist; preference for primary
sources (papers, proceedings, datasheets, benchmark repositories) over secondary summaries".
That preference is expressed structurally rather than as advice: this instrument queries a
preprint server's own API, so every result is a paper with an arXiv identifier, and there is
no code path by which a blog post or a summary of a paper can come back from it.

**A result is an identifier, never a passage.** `Found` carries what arXiv says about a paper —
id, title, date, abstract — and `evidence.arxiv(found.identifier)` turns it straight into a
citation the channel can resolve. That is the point: a Cell handed search results cannot invent
a reference, because the only references in front of it are ones there is already a URL for. It
can still misread an abstract; it cannot conjure the paper.

The arrow runs one way, as everywhere else: `evidence` knows about `Found`, and this module has
never heard of a `Citation`.

Identifiers keep their version (`2207.00729v4`). arXiv accepts and echoes them, so a claim
cites the exact text it was read from rather than whatever the latest revision happens to say.

Deletion criterion: this module holds the wager that g0rd0n can find primary literature without
being able to invent it. Delete it and `search_results_are_citable_identifiers_not_prose` loses
its verdict, and the only way to get a reference into the system becomes a string somebody
typed — which is the shape a fabricated citation arrives in.

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

import urllib.parse
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from typing import Protocol

from g0rd0n.instruments.fetch import Fetcher, FetchError

ARXIV_API = "https://export.arxiv.org/api/query"

ATOM = "{http://www.w3.org/2005/Atom}"

#: arXiv's "search everything" field prefix. The query goes in **unquoted**: wrapping it in
#: double quotes makes arXiv match the whole thing as one exact phrase, so a perfectly good
#: three-word query returns zero results and looks like "no such literature exists" rather than
#: like a bug. Found by searching for a paper that certainly exists and getting nothing back.
FIELD = "all:"

#: How many results a query returns unless it says otherwise. Small on purpose: a search that
#: hands back fifty papers is a search nobody read the results of.
DEFAULT_LIMIT = 10

#: Markup that makes an XML parser do work proportional to something other than the document's
#: size. `xml.etree` expands internal entities, so a hostile or broken feed could cost far more
#: than its `MAX_BYTES`. Rejected before parsing rather than mitigated after: the allowlist says
#: where bytes may come from, not that they are safe.
UNSAFE = ("<!DOCTYPE", "<!ENTITY")


class SearchError(Exception):
    """A search could not be run, or came back as something that is not a result list."""


@dataclass(frozen=True)
class Found:
    """One paper, as the search told us about it.

    `summary` is the abstract, which is the most a search result may carry: it is enough for a
    Cell to decide whether the paper is worth fetching, and not enough to mistake for having
    read it.
    """

    identifier: str
    title: str
    published: str
    summary: str
    url: str


class Search(Protocol):
    """The seam. Tests pass a stub; nothing in the test suite opens a socket."""

    def find(self, query: str, limit: int = DEFAULT_LIMIT) -> tuple[Found, ...]: ...


@dataclass(frozen=True)
class Arxiv:
    """arXiv's Atom API, through the allowlisted fetcher.

    Holds a `Fetcher` rather than opening its own socket, so the network allowlist and the
    redirect check apply here exactly as they do everywhere else.
    """

    fetcher: Fetcher

    def find(self, query: str, limit: int = DEFAULT_LIMIT) -> tuple[Found, ...]:
        """Search titles, abstracts and authors. Returns papers, most relevant first."""
        if not query.strip():
            raise SearchError("an empty query matches everything, which is not a search")
        if limit < 1:
            raise SearchError(f"a search for {limit} results is not a search")

        asked = urllib.parse.urlencode(
            {
                "search_query": f"{FIELD}{query}",
                "start": 0,
                "max_results": limit,
                "sortBy": "relevance",
            }
        )
        try:
            fetched = self.fetcher.get(f"{ARXIV_API}?{asked}")
        except FetchError as exc:
            raise SearchError(f"searching arXiv for {query!r} failed: {exc}") from exc
        return parse(fetched.text)


def parse(feed: str) -> tuple[Found, ...]:
    """Read an arXiv Atom feed into results, or raise `SearchError`.

    A feed with no entries is an empty result, not an error: "nothing matched" is an answer.
    """
    for marker in UNSAFE:
        if marker in feed:
            raise SearchError(f"the feed contains {marker}, which this will not parse")
    try:
        root = ElementTree.fromstring(feed)
    except ElementTree.ParseError as exc:
        raise SearchError(f"arXiv answered something that is not an Atom feed: {exc}") from exc

    # Parsing is not arriving. An HTML error page is well-formed XML, so without this a 503
    # comes back as "nothing matched" — the same shape of lie as a citation that resolves
    # because the fetch returned 200. Check the root is the thing we asked for.
    if root.tag != f"{ATOM}feed":
        raise SearchError(
            f"arXiv answered a <{root.tag}> rather than an Atom feed; a document that parses "
            "is not a result list that arrived"
        )

    found = []
    for entry in root.findall(f"{ATOM}entry"):
        url = _text(entry, "id")
        identifier = url.rsplit("/abs/", 1)[-1]
        if not identifier or identifier == url:
            raise SearchError(f"an arXiv entry carries no identifier: {url!r}")
        found.append(
            Found(
                identifier=identifier,
                title=_text(entry, "title"),
                published=_text(entry, "published"),
                summary=_text(entry, "summary"),
                url=url,
            )
        )
    return tuple(found)


def _text(entry: ElementTree.Element, tag: str) -> str:
    """One field of an entry, with its whitespace normalised.

    arXiv wraps titles and abstracts across lines, so the raw text of a title contains newlines
    and runs of spaces. Normalising here keeps them out of provenance and out of note names.
    """
    node = entry.find(f"{ATOM}{tag}")
    return " ".join((node.text or "").split()) if node is not None else ""
