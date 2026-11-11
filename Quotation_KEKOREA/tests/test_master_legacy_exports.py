"""Regression checks for MASTER integration of the existing document engine."""
import unittest
from unittest.mock import patch
from pathlib import Path

from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft


class LegacyExportsTests(unittest.TestCase):
    def test_rejects_unknown_document_kind(self):
        with self.assertRaisesRegex(ValueError, "Only PI"):
            render_master_trade_draft("CONTRACT", {}, {})

    def test_rejects_mismatched_type(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            render_master_trade_draft("PI", {"document_type": "PO"}, {})

    @patch("Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.validate_and_calculate")
    def test_incomplete_document_never_renders(self, validate):
        validate.return_value = {"blocking_issues": ["Missing buyer"], "ready_for_issue": False}
        with self.assertRaisesRegex(ValueError, "Missing buyer"):
            render_master_trade_draft("PO", {}, {})

    @patch("Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.resolve_company_seal")
    @patch("Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.validate_and_calculate")
    def test_missing_seal_blocks_export(self, validate, seal):
        validate.return_value = {"blocking_issues": [], "ready_for_issue": True}
        seal.return_value = (Path("/nonexistent/company-seal.png"), None, "not configured")
        with self.assertRaisesRegex(ValueError, "직인"):
            render_master_trade_draft("PO", {}, {})

    @patch("Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.validate_and_calculate")
    def test_pi_requires_complete_bank_profile(self, validate):
        validate.return_value = {"blocking_issues": [], "ready_for_issue": True}
        with self.assertRaisesRegex(ValueError, "은행정보"):
            render_master_trade_draft("PI", {}, {})


if __name__ == "__main__":
    unittest.main()
