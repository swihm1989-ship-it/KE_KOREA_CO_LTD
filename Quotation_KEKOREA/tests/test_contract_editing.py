import unittest
from copy import deepcopy

from Quotation_KEKOREA.contracts.editing import (
    RevisionConflict, apply_proposal, restore_revision,
)
from Quotation_KEKOREA.contracts.models import new_snapshot


class ContractEditingTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = new_snapshot("contract-1", "trade_commission", "en")
        self.snapshot["revision"] = 4
        self.snapshot["terms"] = [{
            "id": "rate", "key": "commission_formula", "value": "3%",
            "status": "confirmed", "source_refs": [],
        }]
        self.snapshot["clauses"] = [{
            "id": "clause-1", "title": "Commission", "order": 1,
            "sentences": [{"id": "sentence-1", "text": "The fee is 3%.", "term_ids": []},
                          {"id": "sentence-2", "text": "Pay after delivery.", "term_ids": []}],
        }]

    def test_apply_updates_selected_sentence_and_term_in_one_snapshot(self):
        proposal = {
            "base_revision": 4,
            "changes": [
                {"id": "c1", "sentence_id": "sentence-1", "original_text": "The fee is 3%.",
                 "proposed_text": "The fee is 2%.", "required_to_resolve_conflict": True},
                {"id": "c2", "sentence_id": None, "term_key": "commission_formula",
                 "proposed_text": "2%", "term_value": {"key": "commission_formula",
                 "value": "2%", "status": "confirmed",
                 "source_refs": [{"kind": "reference", "document_id": "ref-1",
                                  "quote": "The fee is 2%."}]},
                 "required_to_resolve_conflict": True},
            ],
        }
        updated = apply_proposal(self.snapshot, proposal, ["c1", "c2"])
        self.assertEqual(updated["revision"], 5)
        self.assertEqual(updated["clauses"][0]["sentences"][0]["text"], "The fee is 2%.")
        self.assertEqual(updated["clauses"][0]["sentences"][1]["id"], "sentence-2")
        self.assertEqual(updated["terms"][0]["value"], "2%")
        self.assertEqual(updated["reference_ids"], ["ref-1"])

    def test_missing_required_change_rejects_partial_application(self):
        proposal = {
            "base_revision": 4,
            "changes": [
                {"id": "main", "sentence_id": "sentence-1", "original_text": "The fee is 3%.",
                 "proposed_text": "The fee is 2%."},
                {"id": "required", "sentence_id": "sentence-2", "original_text": "Pay after delivery.",
                 "proposed_text": "Pay before pickup.", "required_to_resolve_conflict": True},
            ],
        }
        with self.assertRaises(RevisionConflict):
            apply_proposal(self.snapshot, proposal, ["main"])

    def test_stale_proposal_is_rejected(self):
        proposal = {"base_revision": 3, "changes": []}
        with self.assertRaises(RevisionConflict):
            apply_proposal(self.snapshot, proposal, [])

    def test_undo_restores_bundle_as_a_new_revision(self):
        previous = deepcopy(self.snapshot)
        current = deepcopy(self.snapshot)
        current["revision"] = 5
        current["terms"][0]["value"] = "2%"
        current["clauses"][0]["sentences"][0]["text"] = "The fee is 2%."
        restored = restore_revision(current, previous)
        self.assertEqual(restored["revision"], 6)
        self.assertEqual(restored["terms"][0]["value"], "3%")
        self.assertEqual(restored["clauses"][0]["sentences"][0]["text"], "The fee is 3%.")

    def test_duplicate_sentence_text_keeps_selected_id_target(self):
        self.snapshot["clauses"][0]["sentences"].append({
            "id": "sentence-3", "text": "The fee is 3%.", "term_ids": [],
        })
        proposal = {"base_revision": 4, "changes": [{
            "id": "c1", "sentence_id": "sentence-3",
            "original_text": "The fee is 3%.", "proposed_text": "The fee is 2%.",
        }]}
        updated = apply_proposal(self.snapshot, proposal, ["c1"])
        self.assertEqual(updated["clauses"][0]["sentences"][0]["text"], "The fee is 3%.")
        self.assertEqual(updated["clauses"][0]["sentences"][2]["text"], "The fee is 2%.")


if __name__ == "__main__":
    unittest.main()
