import unittest
from datetime import UTC, datetime

from g0rd0n.core.research import Provenance, ResearchObject, ResearchObjectKind


class ResearchObjectTests(unittest.TestCase):
    def test_all_required_research_object_kinds_exist(self):
        self.assertEqual(len(ResearchObjectKind), 15)

    def test_object_requires_timezone_aware_provenance(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            ResearchObject(
                id="H-1",
                kind=ResearchObjectKind.HYPOTHESIS,
                title="Example",
                content={},
                provenance=Provenance("researcher", datetime(2026, 1, 1), "session-1"),
            )

    def test_valid_object(self):
        obj = ResearchObject(
            id="Q-1",
            kind=ResearchObjectKind.QUESTION,
            title="A bounded question",
            content={"text": "What separates the candidates?"},
            provenance=Provenance("researcher", datetime.now(UTC), "session-1"),
        )
        self.assertEqual(obj.kind, ResearchObjectKind.QUESTION)


if __name__ == "__main__":
    unittest.main()
