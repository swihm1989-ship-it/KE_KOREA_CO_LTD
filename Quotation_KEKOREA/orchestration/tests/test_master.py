"""Run with: python -m unittest discover -s Quotation_KEKOREA/orchestration/tests"""
import unittest
import importlib.util
from Quotation_KEKOREA.orchestration.router import classify
from Quotation_KEKOREA.orchestration.security.attachment_manifest import build_manifest, verify_manifest
from Quotation_KEKOREA.orchestration.approval.send_gate import envelope_digest, requires_reapproval

class RouterTests(unittest.TestCase):
    def test_multidocument(self):
        self.assertEqual(classify("PI and Packing List", "계약서 검토"), ["PI", "PL", "CONTRACT"])
    def test_no_guess(self):
        self.assertEqual(classify("hello", "just checking"), [])
    def test_user_requested_kinds_are_validated(self):
        self.assertEqual(classify("", "", ["pi", "PI", "po"]), ["PI", "PO"])
        with self.assertRaises(ValueError):
            classify("", "", ["WIRE_PAYMENT"])

class ManifestTests(unittest.TestCase):
    def test_modified_bytes_rejected(self):
        m = build_manifest("test.pdf", "1", b"reviewed-document")
        self.assertTrue(verify_manifest(m, b"reviewed-document"))
        self.assertFalse(verify_manifest(m, b"modified-document"))

class ApprovalTests(unittest.TestCase):
    def test_envelope_change_revokes_email_approval(self):
        draft = {"from": "sender@example.test", "to": ["buyer@example.test"],
                 "subject": "PI", "body": "Please review"}
        fingerprint = ["a" * 64]
        approved = envelope_digest(draft, fingerprint)
        self.assertFalse(requires_reapproval(approved, draft, fingerprint))
        self.assertTrue(requires_reapproval(approved, {**draft, "to": ["other@example.test"]}, fingerprint))
        self.assertTrue(requires_reapproval(approved, draft, ["b" * 64]))

@unittest.skipUnless(importlib.util.find_spec("langgraph") is not None, "langgraph not installed in this environment")
class GraphTests(unittest.TestCase):
    def test_graph_blocks_all_actions(self):
        from Quotation_KEKOREA.orchestration.master_graph import run_dry_run
        result = run_dry_run("PI / CI", "Please prepare")
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual([t["kind"] for t in result["document_tasks"]], ["PI", "CI"])
        self.assertNotIn("send_intent", result)
        self.assertNotIn("approved", result)

if __name__ == "__main__":
    unittest.main()
