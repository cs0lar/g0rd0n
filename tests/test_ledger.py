import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind
from g0rd0n.research.ledger import (
    FileResearchLedger,
    IntegrityError,
    ObjectStatus,
    canonical_json,
)


START = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)


def provenance(offset: int = 0) -> Provenance:
    return Provenance("test-researcher", START + timedelta(seconds=offset), "test-session")


def research_object(identifier: str, kind: ResearchObjectKind, offset: int) -> ResearchObject:
    return ResearchObject(
        id=identifier,
        kind=kind,
        title=f"{kind.value}: {identifier}",
        content={"statement": f"content for {identifier}"},
        provenance=provenance(offset),
    )


class LedgerTests(unittest.TestCase):
    def test_canonical_serialization_is_key_order_independent(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), canonical_json({"a": 1, "b": 2}))

    def test_complete_cycle_replays_and_traces_raw_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            ledger = FileResearchLedger(path)
            objects = (
                research_object("Q-1", ResearchObjectKind.QUESTION, 0),
                research_object("H-1", ResearchObjectKind.HYPOTHESIS, 1),
                research_object("P-1", ResearchObjectKind.PREDICTION, 2),
                research_object("E-1", ResearchObjectKind.EXPERIMENT, 3),
                research_object("O-1", ResearchObjectKind.OBSERVATION, 4),
                research_object("R-1", ResearchObjectKind.RESULT, 5),
                research_object("C-1", ResearchObjectKind.CLAIM, 6),
            )
            for obj in objects:
                ledger.record(obj)
            raw = b"trial,value\n1,3.25\n"
            digest = ledger.attach_artifact("O-1", raw, provenance(7), media_type="text/csv")
            ledger.relate("H-1", "answers", "Q-1", provenance(8))
            ledger.relate("P-1", "predicted_by", "H-1", provenance(9))
            ledger.relate("E-1", "tests", "H-1", provenance(10))
            ledger.relate("O-1", "observed_in", "E-1", provenance(11))
            ledger.relate("R-1", "derived_from", "O-1", provenance(12))
            ledger.relate("C-1", "supported_by", "R-1", provenance(13))
            ledger.transition("E-1", ObjectStatus.ACTIVE, provenance(14), reason="execution started")
            ledger.transition("E-1", ObjectStatus.COMPLETED, provenance(15), reason="protocol completed")

            replayed = FileResearchLedger(path)
            self.assertEqual(replayed.state.head_hash, ledger.state.head_hash)
            self.assertEqual(replayed.state.objects, ledger.state.objects)
            self.assertEqual(replayed.read_artifact(digest), raw)
            sources = replayed.state.trace_sources("C-1")
            self.assertEqual([source.id for source in sources], ["R-1", "O-1", "E-1", "H-1", "Q-1"])
            self.assertEqual(replayed.state.artifacts["O-1"], (digest,))

    def test_same_events_have_identical_serialization_and_hashes(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            ledgers = [FileResearchLedger(Path(first)), FileResearchLedger(Path(second))]
            for ledger in ledgers:
                ledger.record(research_object("Q-1", ResearchObjectKind.QUESTION, 0))
                ledger.transition("Q-1", ObjectStatus.ACTIVE, provenance(1), reason="selected")
            self.assertEqual(
                (Path(first) / "events.jsonl").read_bytes(),
                (Path(second) / "events.jsonl").read_bytes(),
            )

    def test_changed_history_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            ledger = FileResearchLedger(path)
            ledger.record(research_object("Q-1", ResearchObjectKind.QUESTION, 0))
            log_path = path / "events.jsonl"
            event = json.loads(log_path.read_text(encoding="utf-8"))
            event["payload"]["object"]["title"] = "silently changed"
            log_path.write_text(json.dumps(event, separators=(",", ":")) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "content hash"):
                FileResearchLedger(path)

    def test_duplicate_objects_and_invalid_transitions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = FileResearchLedger(Path(temporary_directory))
            obj = research_object("Q-1", ResearchObjectKind.QUESTION, 0)
            ledger.record(obj)
            with self.assertRaisesRegex(IntegrityError, "already exists"):
                ledger.record(obj)
            with self.assertRaisesRegex(IntegrityError, "invalid status transition"):
                ledger.transition("Q-1", ObjectStatus.COMPLETED, provenance(1), reason="skipped")

    def test_failed_append_does_not_change_log(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = FileResearchLedger(Path(temporary_directory))
            ledger.record(research_object("Q-1", ResearchObjectKind.QUESTION, 0))
            before = ledger.log_path.read_bytes()
            with self.assertRaises(KeyError):
                ledger.transition("missing", ObjectStatus.ACTIVE, provenance(1), reason="invalid")
            self.assertEqual(ledger.log_path.read_bytes(), before)

    def test_failed_artifact_attachment_leaves_no_orphan(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = FileResearchLedger(Path(temporary_directory))
            with self.assertRaises(KeyError):
                ledger.attach_artifact("missing", b"unreferenced", provenance(1))
            self.assertEqual(tuple(ledger.artifact_directory.iterdir()), ())
            self.assertEqual(ledger.log_path.read_bytes(), b"")

    def test_artifact_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = FileResearchLedger(Path(temporary_directory))
            ledger.record(research_object("O-1", ResearchObjectKind.OBSERVATION, 0))
            digest = ledger.attach_artifact("O-1", b"raw", provenance(1))
            (ledger.artifact_directory / digest).chmod(0o644)
            (ledger.artifact_directory / digest).write_bytes(b"changed")
            with self.assertRaisesRegex(IntegrityError, "artifact content hash"):
                ledger.read_artifact(digest)


if __name__ == "__main__":
    unittest.main()
