"""Resolving a citation: fetch it, check it is what it claims to be, hash it, intern it.

AGENTS.md §Phase 6: "A citation that cannot be resolved to a retrievable artifact is a hard
failure, not a low-confidence claim. Fabricated references are the single most damaging
failure mode available to this system, and the gate against them is mechanical: resolve,
fetch, hash, or discard."

The mechanical part matters, and one detail decides whether it works. **A successful fetch is
not a resolution.** arXiv's API answers a fabricated identifier with HTTP 200 and an empty
Atom feed — verified against the live service while designing this — so a gate that checked
only the status code would resolve a reference to a paper that does not exist, which is
precisely the failure it was built to stop. Publishers' 404 pages behave the same way.

So a `Citation` declares what its own resolution must contain, and the fetched bytes are
searched for it. One field, checked in one place, rather than a parser per source scheme: the
citation asserts "if this is real, its record says *this*", and resolution either finds it or
the run fails. `arxiv()` fills the field in for the one scheme Phase 6 ships.

What this does not do is fetch the full text. Resolution establishes that the reference exists
and pins the bytes that were seen; reading the paper is a Cell's job, through a separate fetch
with its own budget.

Deletion criterion: this module holds the wager that no claim in g0rd0n rests on a citation
nobody retrieved. Delete it and `unresolvable_citation_fails_the_ingestion_run` loses its
verdict, a fabricated reference becomes a low-confidence hypothesis instead of a stopped run,
and the record fills with sources that were never anywhere.
"""

from dataclasses import dataclass

from g0rd0n.instruments.fetch import Fetched, Fetcher, FetchError
from g0rd0n.kernel import Bridge, EntityId, Provenance, Ref

#: arXiv's machine-readable endpoint. On the config's allowlist, and the same endpoint Phase
#: 6b's search instrument queries, so a found paper and a cited paper resolve identically.
ARXIV_QUERY = "https://export.arxiv.org/api/query?id_list="

#: What an arXiv Atom entry carries for a real identifier, and omits for one that is not.
ARXIV_MARKER = "arxiv.org/abs/"


class UnresolvableCitation(Exception):
    """A citation could not be retrieved, or retrieved something that was not it.

    Deliberately not a subclass of anything the ingestion path catches. A citation that will
    not resolve ends the run; there is no degraded mode in which it becomes a weaker claim.
    """


@dataclass(frozen=True)
class Citation:
    """A pointer to a primary source, as the thing that made the claim gives it.

    `must_contain` is what stops a 200-with-nothing-in-it from counting as a resolution. It
    should be the most specific string that a genuine record is obliged to carry and a
    near-miss is not — an identifier, not a title, because titles are how two different papers
    resolve to each other.
    """

    identifier: str
    url: str
    must_contain: str

    @property
    def name(self) -> str:
        """The entity name for this source: `arxiv:2401.00001` becomes `arxiv-2401.00001`.

        `Ref` forbids `:` and path separators in a name, since names become note filenames in
        the vault. Replacing rather than stripping keeps distinct identifiers distinct.
        """
        slug = self.identifier
        for character in (":", "/", "\\"):
            slug = slug.replace(character, "-")
        return slug

    @property
    def ref(self) -> Ref:
        return Ref("source", self.name)


@dataclass(frozen=True)
class Source:
    """A citation that was actually retrieved, with the bytes pinned.

    `document` is knk's entity for the retrieved bytes. It is cited from provenance and never
    committed as a subject or object: knk leaves document entities unnamed, and an unnamed
    entity in an assertion makes the vault unprojectable for good (ADR 0003).
    """

    ref: Ref
    citation: Citation
    digest: str
    document: EntityId
    url: str

    def provenance(self, method: str) -> Provenance:
        """Provenance naming this source, how the claim was extracted, and what was seen.

        The digest travels in the method text because that is the field knk gives us for it,
        and because a provenance that says where without saying *what* leaves no way to tell
        that the page changed underneath the claim.
        """
        return Provenance(
            source=self.ref,
            method=f"{method}; retrieved {self.url}, sha256 {self.digest}, knk document "
            f"{self.document}",
        )


def resolve(citation: Citation, *, bridge: Bridge, fetcher: Fetcher) -> Source:
    """Retrieve a citation and intern what came back, or raise `UnresolvableCitation`.

    Every failure is the same failure: the reference does not resolve. A refused host, a dead
    link, and a record that does not mention the identifier it was fetched for are all the
    citation failing to be a citation, and none of them is a reason to keep the claim.
    """
    try:
        fetched = fetcher.get(citation.url)
    except FetchError as exc:
        raise UnresolvableCitation(f"{citation.identifier} does not resolve: {exc}") from exc

    _check_is_what_it_claims(citation, fetched)
    document = bridge.intern_document(fetched.content)
    return Source(
        ref=citation.ref,
        citation=citation,
        digest=fetched.digest,
        document=document,
        url=fetched.url,
    )


def arxiv(identifier: str) -> Citation:
    """A citation to an arXiv paper, pointed at the API record rather than the abstract page.

    The API record is what a fabricated identifier fails to produce, and it is stable in a way
    the HTML abstract page — with its site furniture and its rotating banners — is not, so the
    digest stays meaningful across a rebuild.
    """
    bare = identifier.removeprefix("arxiv:")
    if not bare.strip():
        raise UnresolvableCitation("an arXiv citation needs an identifier")
    return Citation(
        identifier=f"arxiv:{bare}",
        url=f"{ARXIV_QUERY}{bare}",
        must_contain=f"{ARXIV_MARKER}{bare}",
    )


def _check_is_what_it_claims(citation: Citation, fetched: Fetched) -> None:
    if not fetched.content:
        raise UnresolvableCitation(f"{citation.identifier} resolves to an empty document")
    if citation.must_contain not in fetched.text:
        raise UnresolvableCitation(
            f"{citation.identifier} was retrieved from {fetched.url} but the record does not "
            f"mention {citation.must_contain!r}; a fetch that succeeds is not a citation that "
            "resolves"
        )
