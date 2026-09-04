import copy
import json
import unittest
from pathlib import Path

from g0rd0n.core.mission import MissionSpec
from g0rd0n.core.vocabulary import ScientificDimension


MISSION_PATH = Path(__file__).parents[1] / "config" / "mission.json"
SCHEMA_DIR = Path(__file__).parents[1] / "schemas"


class MissionSpecTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(MISSION_PATH.read_text(encoding="utf-8"))

    def test_canonical_mission_validates(self):
        spec = MissionSpec.from_json(MISSION_PATH)
        self.assertEqual(spec.target_continuous_power_watts, 20)
        self.assertEqual({item.term for item in spec.glossary}, set(ScientificDimension))

    def test_json_schema_documents_are_valid_json(self):
        schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
        self.assertEqual(
            {path.name for path in schemas},
            {
                "baseline-manifest.schema.json",
                "budget.schema.json",
                "campaign-preregistration.schema.json",
                "energy-profile.schema.json",
                "isolated-evaluation-suite.schema.json",
                "integrity-adversarial-suite.schema.json",
                "integrity-event.schema.json",
                "integrity-policy.schema.json",
                "ledger-event.schema.json",
                "method-protocol.schema.json",
                "mission.schema.json",
                "paradigm-spec.schema.json",
                "proof-bundle.schema.json",
                "research-program.schema.json",
                "research-object.schema.json",
                "research-memory-event.schema.json",
                "resource.schema.json",
            },
        )
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")

    def test_every_criterion_is_checkable_and_falsifiable(self):
        spec = MissionSpec.from_json(MISSION_PATH)
        for criterion in spec.criteria:
            self.assertTrue(criterion.indicator)
            self.assertTrue(criterion.threshold)
            self.assertTrue(criterion.falsifier)

    def test_duplicate_contradictory_definition_is_rejected(self):
        invalid = copy.deepcopy(self.data)
        invalid["glossary"].append(
            {"term": "computability", "definition": "A conflicting definition", "excludes": []}
        )
        with self.assertRaisesRegex(ValueError, "exactly once"):
            MissionSpec.from_dict(invalid)

    def test_duplicate_criterion_id_is_rejected(self):
        invalid = copy.deepcopy(self.data)
        invalid["criteria"].append(copy.deepcopy(invalid["criteria"][0]))
        invalid["criteria"][-1]["description"] = "Contradiction"
        with self.assertRaisesRegex(ValueError, "duplicate criterion"):
            MissionSpec.from_dict(invalid)

    def test_unbounded_interpretation_is_rejected(self):
        invalid = copy.deepcopy(self.data)
        invalid["interpretation"] = "unrestricted_computability"
        with self.assertRaisesRegex(ValueError, "resource_bounded_separation"):
            MissionSpec.from_dict(invalid)


if __name__ == "__main__":
    unittest.main()
