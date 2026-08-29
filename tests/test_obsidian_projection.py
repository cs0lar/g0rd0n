import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind
from g0rd0n.projection.obsidian import (
    MANUAL_END,
    MANUAL_START,
    ObsidianProjector,
    ProjectionError,
)
from g0rd0n.research.ledger import FileResearchLedger, ResearchState


START = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def provenance(offset: int) -> Provenance:
    return Provenance("researcher", START + timedelta(seconds=offset), "session:projection-test")


def obj(identifier: str, kind: ResearchObjectKind, offset: int) -> ResearchObject:
    return ResearchObject(
        identifier,
        kind,
        f"{kind.value.replace('_', ' ').title()} {identifier}",
        {"statement": f"Structured content for {identifier}"},
        provenance(offset),
    )


def populated_ledger(directory: Path) -> FileResearchLedger:
    ledger = FileResearchLedger(directory)
    objects = (
        obj("Q-1", ResearchObjectKind.QUESTION, 0),
        obj("H-1", ResearchObjectKind.HYPOTHESIS, 1),
        obj("E-1", ResearchObjectKind.EXPERIMENT, 2),
        obj("O-1", ResearchObjectKind.OBSERVATION, 3),
        obj("R-1", ResearchObjectKind.RESULT, 4),
        obj("C-1", ResearchObjectKind.CLAIM, 5),
    )
    for item in objects:
        ledger.record(item)
    ledger.relate("Q-1", "has_hypothesis", "H-1", provenance(6))
    ledger.relate("E-1", "tests", "H-1", provenance(7))
    ledger.relate("O-1", "observed_in", "E-1", provenance(8))
    ledger.relate("R-1", "derived_from", "O-1", provenance(9))
    ledger.relate("C-1", "supported_by", "R-1", provenance(10))
    ledger.attach_artifact("O-1", b"trial,value\n1,7.0\n", provenance(11), media_type="text/csv")
    return ledger


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ObsidianProjectionTests(unittest.TestCase):
    def test_projection_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ledger = populated_ledger(root / "ledger")
            first = root / "first-vault"
            second = root / "second-vault"
            ObsidianProjector(first, artifact_loader=ledger.read_artifact).project(ledger.state)
            ObsidianProjector(second, artifact_loader=ledger.read_artifact).project(ledger.state)
            self.assertEqual(tree_bytes(first), tree_bytes(second))

    def test_complete_experiment_is_auditable_through_wikilinks_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ledger = populated_ledger(root / "ledger")
            vault = root / "vault"
            ObsidianProjector(vault, artifact_loader=ledger.read_artifact).project(ledger.state)

            claim = (vault / "06-theories" / "C-1.md").read_text(encoding="utf-8")
            result = (vault / "05-results" / "R-1.md").read_text(encoding="utf-8")
            observation = (vault / "04-experiments" / "O-1.md").read_text(encoding="utf-8")
            self.assertIn("[[05-results/R-1|Result R-1]]", claim)
            self.assertIn("[[04-experiments/O-1|Observation O-1]]", result)
            self.assertIn("[[04-experiments/E-1|Experiment E-1]]", observation)
            digest = ledger.state.artifacts["O-1"][0]
            self.assertIn(f"[[99-generated/artifacts/{digest}|sha256:{digest}]]", observation)
            self.assertEqual((vault / "99-generated" / "artifacts" / digest).read_bytes(), b"trial,value\n1,7.0\n")

    def test_regeneration_preserves_only_the_manual_region(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ledger = populated_ledger(root / "ledger")
            vault = root / "vault"
            projector = ObsidianProjector(vault, artifact_loader=ledger.read_artifact)
            projector.project(ledger.state)
            path = vault / "03-hypotheses" / "H-1.md"
            markdown = path.read_text(encoding="utf-8")
            markdown = markdown.replace("# Hypothesis H-1", "# Unauthorized generated edit")
            markdown = markdown.replace(
                f"{MANUAL_START}\n{MANUAL_END}",
                f"{MANUAL_START}\nReviewer interpretation.\n{MANUAL_END}",
            )
            path.write_text(markdown, encoding="utf-8")

            projector.project(ledger.state)
            regenerated = path.read_text(encoding="utf-8")
            self.assertIn("# Hypothesis H-1", regenerated)
            self.assertNotIn("Unauthorized generated edit", regenerated)
            self.assertIn("Reviewer interpretation.", regenerated)
            edits = projector.collect_manual_edits(ledger.state)
            self.assertEqual([(edit.object_id, edit.markdown) for edit in edits], [("H-1", "Reviewer interpretation.")])

    def test_malformed_ownership_markers_stop_regeneration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ledger = populated_ledger(root / "ledger")
            vault = root / "vault"
            projector = ObsidianProjector(vault, artifact_loader=ledger.read_artifact)
            projector.project(ledger.state)
            path = vault / "01-questions" / "Q-1.md"
            original = path.read_text(encoding="utf-8").replace(MANUAL_END, "")
            path.write_text(original, encoding="utf-8")
            with self.assertRaisesRegex(ProjectionError, "exactly one"):
                projector.project(ledger.state)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_unsafe_stable_id_cannot_escape_vault(self):
        unsafe = obj("../outside", ResearchObjectKind.QUESTION, 0)
        state = ResearchState(objects={unsafe.id: unsafe})
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ProjectionError, "unsafe research object id"):
                ObsidianProjector(Path(temporary_directory)).project(state)

    def test_referenced_artifacts_require_a_verified_loader(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ledger = populated_ledger(root / "ledger")
            with self.assertRaisesRegex(ProjectionError, "artifact_loader"):
                ObsidianProjector(root / "vault").project(ledger.state)
            with self.assertRaisesRegex(ProjectionError, "does not match digest"):
                bad_vault = root / "bad-vault"
                ObsidianProjector(bad_vault, artifact_loader=lambda _: b"wrong").project(ledger.state)
            self.assertEqual(tree_bytes(bad_vault), {})


if __name__ == "__main__":
    unittest.main()
