"""Synthetic regression for real production MASTER incomplete contract AI draft."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import generate_draft


def approved_synthetic_clause():
    return {
        "title": "Long-term Supply",
        "clauses": [
            {"id": "scope", "title": "Scope of Supply", "topic_key": "scope", "order": 1,
             "sentences": [
                 {"id": "scope-1", "text": "The Seller shall supply the goods meeting the agreed specifications, with all missing commercial values to be agreed in writing.", "term_ids": [], "source_refs": []},
                 {"id": "scope-2", "text": "Delivery quantities and scheduling remain subject to the final written purchase nominations.", "term_ids": [], "source_refs": []},
             ]},
            {"id": "payment", "title": "Payment", "topic_key": "payment", "order": 2,
             "sentences": [
                 {"id": "payment-1", "text": "The Buyer shall pay the agreed price under a payment schedule to be specified in the executed order.", "term_ids": [], "source_refs": []},
             ]},
        ],
        "issues": [],
    }


class MasterDraftShapeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = new_snapshot("orchestration-synthetic-id", "sale", "en")
        self.snapshot["title"] = "Synthetic Long-term Supply Agreement"
        self.env = {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}

    def test_missing_top_level_clauses_retries_once_and_keeps_reviewer_warning(self):
        output = approved_synthetic_clause()
        with patch("Quotation_KEKOREA.contracts.service._call",
                   side_effect=[{"title": "ignored", "clauses": [], "issues": []},
                                output]) as call:
            draft = generate_draft(self.snapshot, [], env=self.env,
                                   drafting_plan={"topics": [{"key": "scope"}, {"key": "payment"}]})
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args.kwargs["max_output_tokens"], 14000)
        self.assertEqual(len(draft["clauses"]), 2)
        self.assertEqual(draft["title"], "Synthetic Long-term Supply Agreement")
        self.assertIn("ai_draft_structure_recovered", [i["code"] for i in draft["issues"]])

    def test_nested_complete_clauses_do_not_cost_a_second_call(self):
        with patch("Quotation_KEKOREA.contracts.service._call",
                   return_value={"draft": approved_synthetic_clause()}) as call:
            result = generate_draft(self.snapshot, [], env=self.env)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(result["clauses"]), 2)

    def test_missing_title_does_not_block_complete_clauses(self):
        draft_data=deepcopy(approved_synthetic_clause())
        draft_data.pop("title")
        self.snapshot.pop("title")
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=draft_data) as call:
            result=generate_draft(self.snapshot, [], env=self.env)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["title"], "Contract Draft for Review")

    def test_failed_second_attempt_stays_fail_closed(self):
        incomplete = {"clauses": [], "issues": []}
        with patch("Quotation_KEKOREA.contracts.service._call",
                   return_value=incomplete) as call:
            with self.assertRaisesRegex(ValueError, "after one schema recovery attempt"):
                generate_draft(self.snapshot, [], env=self.env)
        self.assertEqual(call.call_count, 2)

    def test_existing_clauses_still_must_be_reviewed_not_replaced(self):
        output = approved_synthetic_clause()
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=output):
            with self.assertRaisesRegex(ValueError, "draft"):
                altered = deepcopy(self.snapshot)
                altered["clauses"] = output["clauses"]
                # The draft graph's outer guard is authoritative.
                from Quotation_KEKOREA.contracts.ai_graph import generate_contract_draft_graph
                generate_contract_draft_graph(altered, [], env=self.env)


if __name__ == "__main__":
    unittest.main()
