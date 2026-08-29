import unittest
from datetime import UTC, datetime
from typing import Any, Mapping

from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind
from g0rd0n.knowledge.contract import AssertionStatus, Conflict, Query, WriteContext
from g0rd0n.knowledge.knk import KnkKnowledgeStore
from g0rd0n.knowledge.memory import InMemoryKnowledgeStore
from g0rd0n.knowledge.research_mapping import assert_research_relation, research_entity


class FakeKnkToolClient:
    """Behavioral fake at knk's public MCP tool boundary, not its C++ internals."""

    def __init__(self) -> None:
        self.store = InMemoryKnowledgeStore()
        self.entities: list[str] = []
        self.predicates: list[str] = []
        self.recorded_provenance: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    @staticmethod
    def _context(arguments: Mapping[str, Any]) -> WriteContext:
        return WriteContext(
            valid_from=int(arguments["valid_from"]),
            valid_to=int(arguments["valid_to"]),
            observed_at=int(arguments["observed_at"]),
            confidence=float(arguments["confidence"]),
            source="pending",
            method="pending",
        )

    def _intern(self, values: list[str], value: str) -> int:
        if value not in values:
            values.append(value)
        return values.index(value) + 1

    def _assertion(self, assertion_id: int):
        try:
            return next(item for item in self.store._assertions if item.id == str(assertion_id))
        except StopIteration as error:
            raise RuntimeError("unknown assertion") from error

    def _raw(self, assertion) -> dict[str, Any]:
        statuses = {
            AssertionStatus.ACTIVE: "Active",
            AssertionStatus.SUPERSEDED: "Superseded",
            AssertionStatus.RETRACTED: "Retracted",
            AssertionStatus.RETRACTION: "Retraction",
        }
        return {
            "id": int(assertion.id),
            "subject": self._intern(self.entities, assertion.subject),
            "predicate": self._intern(self.predicates, assertion.predicate),
            "object": self._intern(self.entities, assertion.object),
            "valid_from": assertion.valid_from,
            "valid_to": assertion.valid_to,
            "observed_at": assertion.observed_at,
            "confidence": assertion.confidence,
            "status": statuses[assertion.status],
            "supersedes_id": int(assertion.supersedes_id or 0),
            "retracts_id": int(assertion.retracts_id or 0),
        }

    def call(self, name: str, arguments: Mapping[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name == "intern_entity":
            return self._intern(self.entities, str(arguments["name"]))
        if name == "intern_predicate":
            return self._intern(self.predicates, str(arguments["name"]))
        if name == "find_entity":
            value = str(arguments["name"])
            return self.entities.index(value) + 1 if value in self.entities else None
        if name == "find_predicate":
            value = str(arguments["name"])
            return self.predicates.index(value) + 1 if value in self.predicates else None
        if name == "intern_value":
            return self._intern(self.entities, str(arguments["value"]["value"]))
        if name == "commit_by_name":
            record = self.store.assert_(
                str(arguments["subject_name"]),
                str(arguments["predicate_name"]),
                str(arguments["object"]["value"]),
                self._context(arguments),
            )
            return int(record.id)
        if name == "get":
            try:
                return self._raw(self._assertion(int(arguments["id"])))
            except RuntimeError:
                return None
        if name == "record_provenance":
            self.recorded_provenance[str(arguments["assertion_id"])] = dict(arguments)
            return None
        if name == "commit_superseding":
            target = self._assertion(int(arguments["supersedes_id"]))
            new_object = self.entities[int(arguments["object"]) - 1]
            record = self.store.supersede(target.id, new_object, self._context(arguments))
            return int(record.id)
        if name == "commit_retraction":
            target = self._assertion(int(arguments["retracts_id"]))
            record = self.store.retract(target.id, self._context(arguments))
            return int(record.id)
        if name == "entity_name":
            return self.entities[int(arguments["id"]) - 1]
        if name == "predicate_name":
            return self.predicates[int(arguments["id"]) - 1]
        if name in {"current_by_name", "valid_at", "known_at", "valid_at_known_at"}:
            if name == "current_by_name":
                query = Query(str(arguments["subject_name"]))
            else:
                subject = self.entities[int(arguments["subject"]) - 1]
                query = Query(
                    subject,
                    valid_at=int(arguments["valid_time"]) if "valid_time" in arguments else None,
                    known_at=int(arguments["observed_time"]) if "observed_time" in arguments else None,
                )
            return [self._raw(item) for item in self.store.query(query)]
        if name == "commit_history":
            subject = self.entities[int(arguments["subject"]) - 1]
            predicate = self.predicates[int(arguments["predicate"]) - 1]
            return [self._raw(item) for item in self.store.history(subject, predicate)]
        if name == "provenance_for":
            value = self.recorded_provenance.get(str(arguments["assertion_id"]))
            if value is None:
                return None
            return {
                "assertion_id": int(value["assertion_id"]),
                "source": int(value["source"]),
                "recorded_at": int(value["recorded_at"]),
                "method": value["method"],
            }
        if name == "find_conflicts":
            subject = self.entities[int(arguments["subject"]) - 1]
            predicate = self.predicates[int(arguments["predicate"]) - 1]
            return [[self._raw(item.left), self._raw(item.right)] for item in self.store.conflicts(subject, predicate)]
        raise AssertionError(f"unexpected knk tool call: {name}")


def exercise_contract(store):
    first_context = WriteContext(10, 20, "experiment:E-1", "measured", confidence=0.8)
    second_context = WriteContext(12, 21, "experiment:E-2", "measured", confidence=0.7)
    first = store.assert_("claim:C-1", "supported_by", "result:R-1", first_context)
    second = store.assert_("claim:C-1", "supported_by", "result:R-2", second_context)
    before_changes = store.query(Query("claim:C-1", "supported_by", valid_at=15, known_at=21))
    conflicts = store.conflicts("claim:C-1", "supported_by")
    replacement_context = WriteContext(30, 31, "review:RV-1", "superseded after review", confidence=0.9)
    replacement = store.supersede(first.id, "result:R-3", replacement_context)
    retraction_context = WriteContext(32, 33, "review:RV-1", "failed replication")
    retraction = store.retract(second.id, retraction_context)
    return {
        "before_changes": before_changes,
        "conflicts": conflicts,
        "replacement": replacement,
        "retraction": retraction,
        "history": store.history("claim:C-1", "supported_by"),
        "provenance": store.provenance(replacement.id),
        "current": store.query(Query("claim:C-1", "supported_by")),
    }


class KnowledgeStoreContractTests(unittest.TestCase):
    def test_both_adapters_satisfy_identical_contract(self):
        memory_result = exercise_contract(InMemoryKnowledgeStore())
        client = FakeKnkToolClient()
        knk_result = exercise_contract(KnkKnowledgeStore(client))
        self.assertEqual(knk_result, memory_result)
        self.assertTrue(any(name == "commit_by_name" for name, _ in client.calls))
        self.assertTrue(any(name == "find_conflicts" for name, _ in client.calls))

    def test_knk_reads_do_not_intern_unknown_names(self):
        client = FakeKnkToolClient()
        store = KnkKnowledgeStore(client)
        self.assertEqual(store.query(Query("unknown")), ())
        self.assertEqual(store.history("unknown", "missing"), ())
        self.assertEqual(store.conflicts("unknown", "missing"), ())
        called_tools = [name for name, _ in client.calls]
        self.assertNotIn("intern_entity", called_tools)
        self.assertNotIn("intern_predicate", called_tools)

    def test_contract_preserves_conflicting_assertions(self):
        result = exercise_contract(InMemoryKnowledgeStore())
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertIsInstance(result["conflicts"][0], Conflict)
        self.assertEqual(len(result["history"]), 4)
        self.assertEqual(result["current"][0].object, "result:R-3")

    def test_research_object_mapping_uses_stable_ids(self):
        timestamp = datetime(2026, 8, 29, tzinfo=UTC)
        provenance = Provenance("researcher", timestamp, "session")
        hypothesis = ResearchObject("H-1", ResearchObjectKind.HYPOTHESIS, "Candidate", {}, provenance)
        prediction = ResearchObject("P-1", ResearchObjectKind.PREDICTION, "Prediction", {}, provenance)
        store = InMemoryKnowledgeStore()
        assertion = assert_research_relation(
            store,
            hypothesis,
            "predicts",
            prediction,
            WriteContext(1, 2, "session", "human-authored"),
        )
        self.assertEqual(assertion.subject, research_entity(hypothesis))
        self.assertEqual(assertion.object, "g0rd0n:prediction:P-1")
        with self.assertRaisesRegex(ValueError, "unsupported research predicate"):
            assert_research_relation(
                store,
                hypothesis,
                "confidence_means_truth",
                prediction,
                WriteContext(1, 2, "session", "invalid"),
            )


if __name__ == "__main__":
    unittest.main()
