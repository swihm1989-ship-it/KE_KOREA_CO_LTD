"""Checkpoint and interrupt integration must not mutate existing contract output."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.ai_graph import (
    analyze_contract_terms_graph, generate_contract_draft_graph,
)
from Quotation_KEKOREA.contracts.approval_interrupt import (
    start_review, complete_review,
)


class CheckpointContractTests(unittest.TestCase):
    def test_draft_output_and_input_are_unchanged(self):
        original = new_snapshot("contract-d", "sale", "en")
        before = deepcopy(original)
        draft = deepcopy(original)
        draft["clauses"] = [{"id": "c", "title": "Scope", "sentences": [
            {"id": "s", "text": "Goods delivered."},
        ]}]
        draft["draft_quality"] = {"checks": [], "legal_certification": False}
        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_reviewed_draft",
                   return_value=draft) as call:
            result = generate_contract_draft_graph(original, [], env={})
        self.assertEqual(original, before)
        self.assertEqual(result["clauses"][0]["sentences"][0]["text"], "Goods delivered.")
        call.assert_called_once()

    def test_analysis_keeps_suggested_terms_unapproved(self):
        snapshot = new_snapshot("contract-a", "sale", "en")
        ai_result = {"terms": [{"key": "quantity", "value": "500", "status": "suggested"}],
                     "parties": [], "issues": [], "questions": [], "contract_type": "sale"}
        with patch("Quotation_KEKOREA.contracts.ai_graph.analyze_trade",
                   return_value=ai_result):
            output = analyze_contract_terms_graph([], snapshot, [], env={})
        self.assertEqual(output["terms"][0]["status"], "suggested")


class ApprovalInterruptTests(unittest.TestCase):
    def test_pauses_then_resumes_approved(self):
        token = start_review("contract-test", 3, "proposal-a")
        self.assertTrue(complete_review(token, "contract-test", 3, "proposal-a",
                                        approved=True))

    def test_rejected_review_does_not_approve(self):
        token = start_review("contract-test", 3, "proposal-b")
        self.assertFalse(complete_review(token, "contract-test", 3, "proposal-b",
                                         approved=False))

    def test_wrong_revision_cannot_resume(self):
        token = start_review("contract-test", 3, "proposal-c")
        with self.assertRaisesRegex(ValueError, "stale"):
            complete_review(token, "contract-test", 4, "proposal-c", approved=True)
        self.assertTrue(complete_review(token, "contract-test", 3, "proposal-c",
                                        approved=True))


if __name__ == "__main__":
    unittest.main()
