import json
import tempfile
import unittest
from pathlib import Path

from kseo.knowledge import import_materials, load_cards, retrieve
from kseo.util import redact


class KnowledgeTests(unittest.TestCase):
    def test_model_specific_card_needs_matching_context(self):
        cards = load_cards()
        self.assertNotIn("C02", {c["id"] for c in retrieve({}, cards, 100)})
        context = {"model_family": "glm5_2", "capabilities": ["index_share", "mtp"]}
        self.assertIn("C02", {c["id"] for c in retrieve(context, cards, 100)})

    def test_missing_capabilities_not_assumed(self):
        self.assertNotIn("C02", {c["id"] for c in retrieve({"model_family": "glm5_2"}, load_cards(), 100)})

    def test_hypothesis_remains_hypothesis(self):
        card = next(c for c in load_cards() if c["id"] == "C09")
        self.assertIn("NOT_CONFIRMED", card["status"])

    def test_deployment_failure_not_performance_failure(self):
        card = next(c for c in load_cards() if c["id"] == "C06")
        self.assertEqual(card["status"], "DEPLOYMENT_FAILURE")

    def test_ingest_requires_review_and_redacts(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); source = root / "test.md"
            source.write_text("# 报告\nTPOT: 20ms host 192.168.1.2\npassword: do-not-copy\n")
            output = root / "cards.json"
            self.assertEqual(import_materials([source], output), 1)
            text = output.read_text(); card = json.loads(text)["cards"][0]
            self.assertEqual(card["status"], "NEEDS_REVIEW")
            self.assertNotIn("192.168.1.2", text)
            self.assertNotIn("do-not-copy", text)

    def test_private_paths_redacted(self):
        text = redact("TPOT /nfs/internal/model and 10.1.2.3")
        self.assertNotIn("/nfs/", text)
        self.assertNotIn("10.1.2.3", text)
