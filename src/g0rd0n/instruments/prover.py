"""The prover seam: what a machine-checked proof has to hand back, and how to read it.

AGENTS.md §Phase 9 asks for "optional Lean/Coq integration for separation lemmas that reach
the third stage". This module is the half of that integration that does not need Lean to be
installed: the artifact a checker returns, the checker it names, and the one reading of that
artifact that decides whether a proof is a proof.

**No checker is shipped.** There is no Lean and no Coq on the machine this was written on,
and a runner for a tool nobody can run it against is the same speculative driver Phase 8b
declined to write for a wall-plug meter. `Checker` is the seam one arrives through. Until
then the third stage is reachable only from a test, and that is the honest state of affairs:
AGENTS.md is explicit that a real proof here "would be a major result", and a system that
could reach `machine-checked` without a checker would be the overclaim this phase exists to
make visible.

**What a checker is trusted for is the axioms, and only the axioms.** A proof assistant will
happily check a proof that assumes what it set out to prove, as long as the assumption is
declared as an axiom — and it will check a proof with a hole in it, as long as the hole is
spelled `sorry`. Both compile. Both are the most likely way for "machine-checked" to become a
lie. So a `Checked` artifact carries the complete list of axioms the theorem depends on, and
`unadmitted` sorts them into three piles:

- the checker's own foundational axioms, which every proof in that system rests on and which
  say nothing about this claim (`TRUSTED`);
- the hole, which means there is no proof (`HOLES`), and is refused outright; and
- everything else, which is an *assumption the proof made*, and which the claim it is being
  presented for must already have declared as a contingency — or the proof is contingent on
  something the claim never admitted.

That third pile is where Phase 9's bookkeeping stops being a label and becomes a check: an
S1 claim contingent on `TC⁰ ≠ NC¹` that reaches `machine-checked` will have a proof with that
separation as an axiom in it, and the checker is what finds out whether the claim said so.

**The tables are Lean 4's, from its documentation, and have not been run.** `propext`,
`Classical.choice` and `Quot.sound` are Lean 4's core axioms and `sorryAx` is what `sorry`
elaborates to; `#print axioms` is how Lean reports a theorem's dependencies. None of that has
been exercised on this machine because Lean is not installed on it. A checker absent from the
tables is refused rather than guessed at, which is `Config.price_of`'s rule applied to trust.

Deletion criterion: this module holds the wager that a proof which assumes something is
reported as assuming it. Delete it and `machine_checked_status_requires_a_checker_artifact`
and `a_proof_with_a_hole_in_it_is_not_machine_checked` lose their verdicts, and
"machine-checked" goes back to meaning "a file compiled".

An instrument: it returns results and commits nothing (AGENTS.md §6).
"""

from dataclasses import dataclass
from typing import Protocol

from g0rd0n.content import version_of

#: The foundational axioms of each checker g0rd0n knows how to read. A proof depending on
#: these depends on the checker's logic, which is the thing "machine-checked" already trusts.
#: `Lean.ofReduceBool` — what `native_decide` rests on — is deliberately absent: it trusts the
#: compiler rather than the kernel, and a proof that does must declare it like any other
#: assumption.
TRUSTED: dict[str, frozenset[str]] = {
    "lean4": frozenset({"propext", "Classical.choice", "Quot.sound"}),
}

#: What an unfinished proof looks like to each checker. A theorem that depends on it has a
#: hole in it, however it was reached, and is not a proof.
HOLES: dict[str, frozenset[str]] = {
    "lean4": frozenset({"sorryAx"}),
}


class ProverError(Exception):
    """A checker's artifact is not one this system can read as a proof."""


@dataclass(frozen=True)
class Checked:
    """What a checker hands back for one theorem: enough to repeat the check, and its axioms.

    `proof` is the source file's bytes, so the artifact can be interned and the check repeated
    by anyone with the same checker version. `statement` is the theorem's type as the checker
    elaborated it, which is what gets compared against the formal statement a sketch
    committed to — the name alone would let a different theorem with the same name through.
    `axioms` is the checker's own report of what the theorem depends on, in full.
    """

    checker: str
    version: str
    theorem: str
    statement: str
    proof: bytes
    axioms: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("checker", "version", "theorem", "statement"):
            if not str(getattr(self, field)).strip():
                raise ProverError(
                    f"a checker artifact must name its {field}; a proof nobody can re-check "
                    "against the same checker is a proof somebody reports having seen"
                )
        if not self.proof.strip():
            raise ProverError("a checker artifact must carry the proof it checked")
        if self.checker not in TRUSTED:
            raise ProverError(
                f"{self.checker!r} is not a checker g0rd0n knows how to read; it knows "
                f"{', '.join(sorted(TRUSTED))}. Its foundational axioms would have to be "
                "declared before anything it checks could be told apart from what it assumes."
            )

    @property
    def proof_version(self) -> str:
        """The hash of the proof file. Two artifacts with one of these checked the same bytes."""
        return version_of(self.proof)

    @property
    def digest(self) -> str:
        """The artifact's identity: checker, version, theorem, statement, proof, and axioms."""
        return version_of(
            "\n".join(
                (
                    f"checker: {self.checker} {self.version}",
                    f"theorem: {self.theorem}",
                    f"statement: {' '.join(self.statement.split())}",
                    f"proof: {self.proof_version}",
                    f"axioms: {', '.join(sorted(self.axioms))}",
                )
            ).encode("utf-8")
        )

    @property
    def holes(self) -> tuple[str, ...]:
        """The axioms that mean there is no proof."""
        return tuple(sorted(set(self.axioms) & HOLES[self.checker]))

    @property
    def assumptions(self) -> tuple[str, ...]:
        """Every axiom that is neither the checker's foundation nor a hole: what it assumed."""
        return tuple(sorted(set(self.axioms) - TRUSTED[self.checker] - HOLES[self.checker]))


class Checker(Protocol):
    """Something that checks a proof of a named theorem and reports what it depends on.

    The seam a Lean or Coq runner arrives through. None is shipped; see the module docstring.
    """

    def check(self, proof: bytes, theorem: str) -> Checked: ...


def unadmitted(checked: Checked, declared: tuple[str, ...]) -> tuple[str, ...]:
    """The assumptions a proof made that the claim did not declare. Empty means it may stand.

    Raises for a hole: a theorem that depends on `sorry` is not a proof with an extra
    assumption, it is not a proof, and reporting it as "machine-checked, contingent on sorry"
    would be the most elaborate way yet of calling a sketch a theorem.
    """
    if checked.holes:
        raise ProverError(
            f"{checked.theorem} depends on {', '.join(checked.holes)}, which is the checker's "
            "name for a hole in the proof. A proof with a hole in it is a sketch that "
            "compiles, not a machine-checked result."
        )
    return tuple(axiom for axiom in checked.assumptions if axiom not in declared)
