import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from g0rd0n.methods import ExecutionStatus, MethodJournal, MethodProtocol, artifact_tree_hash
from g0rd0n.research.ledger import IntegrityError


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def protocol(method_id: str = "method:sparse-memory-v1") -> MethodProtocol:
    return MethodProtocol(
        id=method_id,
        title="Sparse gated memory",
        abstract="Test an event-gated external memory on exact delayed recall.",
        motivation="Fixed state failed once recall exceeded its information capacity.",
        related_work=("Prior fixed-state campaign", "External-memory architectures"),
        mechanism="Write an input only when a deterministic novelty gate opens.",
        data_construction="Generate every binary sequence for registered lengths.",
        configuration={"state_bits": 2, "lengths": [1, 2, 3]},
        assumptions=("Logical memory access is measured exactly.",),
        expected_result="Recall remains exact while redundant writes decrease.",
        falsifiers=("Recall accuracy falls below one on any registered sequence.",),
        compliance_declarations=("No evaluation examples are used as training data.",),
    )


def write_artifact(root: Path, content: str = "print('candidate')\n") -> None:
    root.mkdir()
    (root / "candidate.py").write_text(content, encoding="utf-8")


class MethodProtocolTests(unittest.TestCase):
    def test_protocol_and_code_changes_invalidate_their_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "code"
            write_artifact(code)
            journal = MethodJournal(root / "methods.jsonl")
            frozen = journal.freeze(protocol(), actor="researcher", frozen_at=NOW)
            approval = journal.approve(
                frozen.protocol.id,
                code,
                approval_id="approval:1",
                reviewer="reviewer",
                policy_version="integrity:v1",
                approved_at=NOW,
            )
            changed_protocol = replace(protocol("method:sparse-memory-v2"), mechanism="Always write every input.")
            changed = journal.freeze(changed_protocol, actor="researcher", frozen_at=NOW)
            self.assertNotEqual(frozen.protocol_hash, changed.protocol_hash)

            (code / "candidate.py").write_text("print('changed')\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact approval"):
                journal.record_execution(
                    frozen.protocol.id,
                    code,
                    approval_id=approval.id,
                    receipt_id="receipt:1",
                    result_artifact_hash="a" * 64,
                    status=ExecutionStatus.SUCCEEDED,
                    recorded_at=NOW,
                )

    def test_unapproved_and_misbound_results_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "code"
            write_artifact(code)
            journal = MethodJournal(root / "methods.jsonl")
            first = journal.freeze(protocol(), actor="researcher", frozen_at=NOW)
            second = journal.freeze(protocol("method:other-v1"), actor="researcher", frozen_at=NOW)
            with self.assertRaisesRegex(ValueError, "requires an approval"):
                journal.record_execution(
                    first.protocol.id,
                    code,
                    approval_id="approval:missing",
                    receipt_id="receipt:missing",
                    result_artifact_hash="b" * 64,
                    status=ExecutionStatus.FAILED,
                    recorded_at=NOW,
                )
            approval = journal.approve(
                first.protocol.id,
                code,
                approval_id="approval:first",
                reviewer="reviewer",
                policy_version="integrity:v1",
                approved_at=NOW,
            )
            with self.assertRaisesRegex(ValueError, "for this frozen method"):
                journal.record_execution(
                    second.protocol.id,
                    code,
                    approval_id=approval.id,
                    receipt_id="receipt:wrong",
                    result_artifact_hash="c" * 64,
                    status=ExecutionStatus.SUCCEEDED,
                    recorded_at=NOW,
                )

    def test_results_and_missing_reproducibility_fields_are_rejected(self):
        value = protocol().to_dict()
        value["result"] = {"accuracy": 1.0}
        with self.assertRaisesRegex(ValueError, "result-bearing"):
            MethodProtocol.from_dict(value)
        value = protocol().to_dict()
        value["configuration"]["execution_id"] = "prior-run"
        with self.assertRaisesRegex(ValueError, "result-bearing"):
            MethodProtocol.from_dict(value)
        value = protocol().to_dict()
        del value["falsifiers"]
        with self.assertRaisesRegex(ValueError, "missing protocol fields"):
            MethodProtocol.from_dict(value)

    def test_supersession_preserves_history_and_replays_identically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "code"
            write_artifact(code)
            path = root / "methods.jsonl"
            journal = MethodJournal(path)
            first = journal.freeze(protocol(), actor="researcher", frozen_at=NOW)
            approval = journal.approve(
                first.protocol.id,
                code,
                approval_id="approval:1",
                reviewer="reviewer",
                policy_version="integrity:v1",
                approved_at=NOW,
            )
            receipt = journal.record_execution(
                first.protocol.id,
                code,
                approval_id=approval.id,
                receipt_id="receipt:1",
                result_artifact_hash="d" * 64,
                status=ExecutionStatus.SUCCEEDED,
                recorded_at=NOW,
            )
            replacement = journal.freeze(protocol("method:sparse-memory-v2"), actor="researcher", frozen_at=NOW)
            journal.supersede(
                first.protocol.id,
                replacement.protocol.id,
                actor="reviewer",
                reason="Revise the gate without mutating the original.",
                superseded_at=NOW,
            )
            replayed = MethodJournal(path)
            self.assertEqual(replayed.events(), journal.events())
            self.assertEqual(replayed.method(first.protocol.id), first)
            self.assertEqual(replayed.approval(approval.id), approval)
            self.assertEqual(replayed.receipt(receipt.id), receipt)
            self.assertEqual(replayed.supersession(first.protocol.id).replacement_method_id, replacement.protocol.id)
            with self.assertRaisesRegex(ValueError, "superseded"):
                replayed.approve(
                    first.protocol.id,
                    code,
                    approval_id="approval:late",
                    reviewer="reviewer",
                    policy_version="integrity:v1",
                    approved_at=NOW,
                )

    def test_tampering_and_external_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "code"
            write_artifact(code)
            path = root / "methods.jsonl"
            journal = MethodJournal(path)
            journal.freeze(protocol(), actor="researcher", frozen_at=NOW)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events[0]["payload"]["protocol"]["title"] = "Rewritten after the result"
            path.write_text(json.dumps(events[0]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "hash chain"):
                MethodJournal(path)

            link_root = root / "linked"
            link_root.mkdir()
            (link_root / "candidate.py").symlink_to(code / "candidate.py")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                artifact_tree_hash(link_root)

    def test_failed_append_does_not_publish_frozen_state(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = MethodJournal(Path(directory) / "methods.jsonl")
            with patch("g0rd0n.methods.journal.os.write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    journal.freeze(protocol(), actor="researcher", frozen_at=NOW)
            self.assertEqual(journal.events(), ())
            with self.assertRaises(KeyError):
                journal.method(protocol().id)


if __name__ == "__main__":
    unittest.main()
