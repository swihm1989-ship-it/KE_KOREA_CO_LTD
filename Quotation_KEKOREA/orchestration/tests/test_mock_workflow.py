"""Mock workflow never touches production services or mail."""
import unittest
from Quotation_KEKOREA.orchestration.workflows.mock_workflow import (
    SAMPLE_MESSAGES, start_mock_run, approve_mock_document,
    approve_mock_email, edit_mock_document, update_mock_email, is_mock_approval_current,
)

class MockFlowTests(unittest.TestCase):
    def test_two_documents_then_email_approval(self):
        run = start_mock_run(SAMPLE_MESSAGES[0])
        self.assertEqual([x.kind for x in run.tasks], ["PI", "PL"])
        self.assertEqual(run.status, "awaiting_document_approval")
        with self.assertRaises(ValueError):
            approve_mock_email(run)
        run = approve_mock_document(run, "PI")
        with self.assertRaises(ValueError):
            approve_mock_email(run)
        run = approve_mock_document(run, "PL")
        self.assertEqual(run.status, "awaiting_email_approval")
        run = approve_mock_email(run)
        self.assertTrue(is_mock_approval_current(run))
        self.assertEqual(run.status, "ready_for_future_integration")

    def test_document_edit_invalidates_both_approvals(self):
        run = start_mock_run(SAMPLE_MESSAGES[1])
        run = approve_mock_document(run, "CONTRACT")
        run = approve_mock_email(run)
        changed = edit_mock_document(run, "CONTRACT", "Revised draft. Never final.")
        self.assertFalse(changed.email_approved)
        self.assertFalse(changed.tasks[0].approved)
        self.assertEqual(changed.status, "awaiting_document_approval")

    def test_email_edit_invalidates_approval(self):
        run = start_mock_run(SAMPLE_MESSAGES[1])
        run = approve_mock_email(approve_mock_document(run, "CONTRACT"))
        run = update_mock_email(run, run.email_to, run.email_subject, "Updated text")
        self.assertFalse(is_mock_approval_current(run))
        self.assertFalse(run.email_approved)

    def test_unknown_kind_stops_in_needs_input(self):
        run = start_mock_run(SAMPLE_MESSAGES[2])
        self.assertEqual(run.tasks, ())
        self.assertEqual(run.status, "needs_input")

    def test_blank_document_is_rejected(self):
        run = start_mock_run(SAMPLE_MESSAGES[0])
        with self.assertRaises(ValueError):
            edit_mock_document(run, "PI", "  ")

    def test_real_addresses_never_present_in_samples(self):
        self.assertTrue(all(msg.sender.endswith("@example.test") for msg in SAMPLE_MESSAGES))

if __name__ == "__main__":
    unittest.main()
