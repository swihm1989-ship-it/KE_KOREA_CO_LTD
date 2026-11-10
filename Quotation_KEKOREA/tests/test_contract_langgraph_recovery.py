"""Graph boundary and non-destructive historical contract recovery tests."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.models import new_snapshot, validate_snapshot
from Quotation_KEKOREA.contracts.legacy_recovery import prepare_duplicate_term_recovery
from Quotation_KEKOREA.contracts.ai_graph import generate_contract_draft_graph


class LegacyRecoveryTests(unittest.TestCase):
    def sample(self):
        snap = new_snapshot("historic", "sale", "ko")
        snap["terms"] = [
            {"id": "t1", "key": "수량", "value": "2324938", "unit": "PCS",
             "status": "confirmed", "source_refs": [{"kind": "user", "quote": "2324938"}]},
            {"id": "t2", "key": "quantity", "value": "2324939", "unit": "PCS",
             "status": "suggested", "source_refs": []},
        ]
        snap["clauses"] = [{
            "id": "c1", "title": "Scope", "sentences": [
                {"id": "s1", "text": "Quantity subject to review.", "term_ids": ["t1", "t2"]}
            ],
        }]
        return snap

    def test_conflicting_saved_terms_are_reviewed_not_silently_rewritten(self):
        original = self.sample()
        before = deepcopy(original)
        recovered, collisions = prepare_duplicate_term_recovery(original)
        self.assertEqual(original, before)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(len(recovered["terms"]), 1)
        self.assertEqual(recovered["terms"][0]["status"], "confirmed")
        self.assertEqual(recovered["terms"][0]["value"], "2324938")
        self.assertEqual(recovered["clauses"][0]["sentences"][0]["term_ids"], ["t1"])
        self.assertEqual(len(collisions[0]["candidates"]), 2)
        self.assertTrue(recovered["_term_recovery_pending"])
        self.assertEqual(validate_snapshot(recovered)["terms"][0]["value"], "2324938")

    def test_no_automatic_recovery_when_snapshot_is_valid(self):
        original = self.sample()
        original["terms"].pop()
        result, conflicts = prepare_duplicate_term_recovery(original)
        self.assertEqual(conflicts, [])
        self.assertEqual(result["terms"][0]["key"], "수량")
        self.assertNotIn("_term_recovery_pending", result)


class ContractLangGraphTests(unittest.TestCase):
    def test_graph_runs_existing_reviewed_pipeline_without_changing_input(self):
        snap = new_snapshot("graph", "sale", "en")
        base = deepcopy(snap)
        draft = deepcopy(snap)
        draft["clauses"] = [{"id": "scope", "title": "Scope",
                             "sentences": [{"id": "scope_1", "text": "Goods sold."}]}]
        draft["draft_quality"] = {"checks": [], "legal_certification": False}
        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_reviewed_draft",
                   return_value=draft) as mocked:
            output = generate_contract_draft_graph(snap, [], env={})
        self.assertEqual(snap, base)
        self.assertTrue(output["clauses"])
        mocked.assert_called_once()

    def test_graph_refuses_existing_clauses_and_never_calls_ai(self):
        snap = new_snapshot("graph", "sale", "ko")
        snap["clauses"] = [{"id": "c1", "title": "Existing",
                            "sentences": [{"id": "s1", "text": "Saved original."}]}]
        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_reviewed_draft") as mocked:
            with self.assertRaisesRegex(ValueError, "existing contract"):
                generate_contract_draft_graph(snap, [], env={})
        mocked.assert_not_called()

    def test_graph_fails_closed_on_missing_quality_audit(self):
        snap = new_snapshot("graph", "sale", "en")
        invalid = deepcopy(snap)
        invalid["clauses"] = [{"id": "c1", "title": "Scope",
                               "sentences": [{"id": "s1", "text": "Goods."}]}]
        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_reviewed_draft",
                   return_value=invalid):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                generate_contract_draft_graph(snap, [], env={})


if __name__ == "__main__":
    unittest.main()
