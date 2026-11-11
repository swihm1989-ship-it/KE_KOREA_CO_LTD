"""End-to-end review flow: routing, existing engine, document approval, email handoff."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
import unittest

from Quotation_KEKOREA.orchestration.workflows.unified_review import (
    new_request, prepare_documents, approve_document, change_request,
    set_email_draft, approve_email_review, verify_handoff,
)


def pi():
    return {"document_type": "PI", "product_family": "solar_cell", "currency": "USD",
            "document_number": "DRAFT", "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
            "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
            "incoterms": "EXW Seoul", "payment_terms": "T/T",
            "items": [{"product_name": "M10 test cell", "quantity": "100", "unit": "PCS",
                       "unit_price": "0.20", "price_basis": "PCS", "price_source": "demo"}]}


class UnifiedFlowTests(unittest.TestCase):
    def test_classifies_and_prepares_real_draft_from_existing_engine(self):
        source = {"PI": pi()}
        copy_source = deepcopy(source)
        run = new_request("Please prepare PI", source)
        self.assertEqual(run.kinds, ("PI",))
        prepared = prepare_documents(run)
        self.assertEqual(source, copy_source)
        self.assertEqual(prepared.status, "awaiting_document_approval")
        self.assertEqual(len(prepared.documents), 1)
        self.assertIn("docx", prepared.documents[0].files)
        self.assertFalse(prepared.documents[0].approved)
        self.assertFalse(prepared.documents[0].files["docx"]["sendable"])

    def test_missing_document_data_blocks_approval(self):
        run = prepare_documents(new_request("PI and packing list please", {"PI": pi()}))
        self.assertEqual(run.kinds, ("PI", "PL"))
        self.assertEqual(run.status, "needs_input")
        self.assertFalse(run.documents[1].files)
        with self.assertRaises(ValueError):
            approve_document(run, "PL")

    def test_unresolved_trade_validation_blocks_approval(self):
        run = prepare_documents(new_request("PO", {"PO": {"document_type": "PO"}}))
        self.assertEqual(run.status, "needs_input")
        with self.assertRaises(ValueError):
            approve_document(run, "PO")

    def test_explicit_two_gate_flow_never_sends(self):
        run = prepare_documents(new_request("PI", {"PI": pi()}))
        with self.assertRaises(ValueError):
            approve_email_review(run)
        run = approve_document(run, "PI")
        self.assertEqual(run.status, "awaiting_email_review")
        with self.assertRaises(ValueError):
            approve_email_review(run)
        run = set_email_draft(run, "buyer@example.test", "PI draft", "DRAFT for internal review")
        run = approve_email_review(run)
        self.assertEqual(run.status, "review_complete_not_sendable")
        self.assertTrue(verify_handoff(run))
        self.assertFalse(run.can_send)
        self.assertEqual(run.documents[0].files["docx"]["final"], False)

    def test_changes_revoke_document_and_email_approval(self):
        run = prepare_documents(new_request("PI", {"PI": pi()}))
        run = approve_document(run, "PI")
        run = set_email_draft(run, "buyer@example.test", "DRAFT", "Review")
        run = approve_email_review(run)
        altered = deepcopy(pi())
        altered["items"][0]["unit_price"] = "0.21"
        changed = change_request(run, {"PI": altered})
        self.assertEqual(changed.status, "needs_preparation")
        self.assertFalse(verify_handoff(changed))
        refreshed = prepare_documents(changed)
        self.assertFalse(refreshed.documents[0].approved)
        self.assertFalse(refreshed.email_approved)

    def test_email_edit_invalidates_email_review_only(self):
        run = prepare_documents(new_request("PI", {"PI": pi()}))
        run = approve_document(run, "PI")
        run = set_email_draft(run, "buyer@example.test", "DRAFT", "Review")
        run = approve_email_review(run)
        changed = set_email_draft(run, "buyer@example.test", "DRAFT revised", "Review")
        self.assertFalse(verify_handoff(changed))
        self.assertTrue(changed.documents[0].approved)

    def test_unrecognized_intent_cannot_generate_any_files(self):
        run = prepare_documents(new_request("Can we chat?", {}))
        self.assertEqual(run.kinds, ())
        self.assertFalse(run.documents)
        self.assertEqual(run.status, "needs_input")

    def test_request_cannot_override_document_kind(self):
        run = new_request("PI", {"PI": {"document_type": "CI"}})
        run = prepare_documents(run)
        self.assertTrue(run.documents[0].blockers)
        self.assertFalse(run.documents[0].files)

    def test_contract_requires_actual_clauses(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        snapshot = new_snapshot("test-contract", "sale", "ko")
        run = prepare_documents(new_request("계약서", {"CONTRACT": snapshot}))
        self.assertFalse(run.documents[0].files)
        with self.assertRaises(ValueError):
            approve_document(run, "CONTRACT")


if __name__ == "__main__":
    unittest.main()
