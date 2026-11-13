"""Regression checks for MASTER integration of the existing document engine."""
import unittest
from unittest.mock import patch
from pathlib import Path

from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft


class LegacyExportsTests(unittest.TestCase):
    def test_incomplete_pi_gets_pdf_without_fabricating_amount_or_seal(self):
        from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_incomplete_trade_pdf
        from hashlib import sha256
        import pymupdf
        original = {"document_type": "PI", "product_family": "solar_cell",
                    "document_number": "", "buyer": {"legal_name": "Smart Solar Systems Co. Ltd",
                    "address": ""}, "seller": {"legal_name": "KE KOREA CO. LTD"},
                    "currency": "USD", "items": [{"product_name": "M10 Solar Cells",
                    "quantity": "", "unit": "PCS", "unit_price": ""}],
                    "missing_fields": ["payment year"]}
        snapshot = __import__("copy").deepcopy(original)
        files = render_incomplete_trade_pdf("PI", original)
        self.assertEqual(original, snapshot)
        self.assertEqual(set(files), {"pdf"})
        self.assertTrue(files["pdf"]["content"].startswith(b"%PDF"))
        self.assertEqual(files["pdf"]["sha256"], sha256(files["pdf"]["content"]).hexdigest())
        self.assertFalse(files["pdf"]["final"])
        self.assertFalse(files["pdf"]["sendable"])
        self.assertTrue(files["pdf"]["review_only"])
        self.assertNotIn(b"PRIVATE", files["pdf"]["content"])
        with pymupdf.open(stream=files["pdf"]["content"], filetype="pdf") as document:
            text = "\n".join(page.get_text() for page in document)
        self.assertIn("Smart Solar Systems Co. Ltd", text)
        self.assertIn("M10 Solar Cells", text)
        self.assertIn("NOT FOR ISSUE", text)
        self.assertIn("NOT PROVIDED", text)
        self.assertIn("TOTAL: NOT PROVIDED", text)
        self.assertNotIn("0.00", text)

    def test_incomplete_pdf_rejects_wrong_document_type_without_seal(self):
        from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_incomplete_trade_pdf
        with self.assertRaisesRegex(ValueError, "mismatch"):
            render_incomplete_trade_pdf("PI", {"document_type": "PO"})
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            render_incomplete_trade_pdf("CONTRACT", {})

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

    def test_master_all_four_documents_use_identical_legacy_renderer_and_assets(self):
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as module
        original_renderer = module.render_files
        from Quotation_KEKOREA.agent.renderers import render_files
        self.assertIs(original_renderer, render_files)
        expected = []
        def fake_render(doc, output_dir, **kwargs):
            self.assertTrue(kwargs["logo_path"].name == "company_logo.png")
            self.assertTrue(kwargs["logo_path"].is_file())
            self.assertTrue(kwargs["seal_path"].is_file())
            expected.append((doc["document_type"], set(kwargs)))
            output_dir.mkdir(parents=True, exist_ok=True)
            result = {}
            for fmt in ("pdf", "xlsx", "html"):
                p = output_dir / ("sample." + fmt)
                p.write_bytes(b"same-legacy-engine")
                result[fmt] = p
            return result

        env = {("KEKOREA_USD_" + key): "safe-test-value" for key in module.BANK_KEYS}
        with (patch.object(module, "validate_and_calculate") as validate,
              patch.object(module, "ci_render_data", side_effect=lambda x: x),
              patch.object(module, "resolve_company_seal",
                           return_value=(Path("/not-present/image.png"), b"png-test-bytes", None)),
              patch.object(module, "render_files", side_effect=fake_render)):
            for kind in ("PI", "PO", "CI", "PL"):
                validate.return_value = {"blocking_issues": [], "ready_for_issue": True,
                                         "document_type": kind,
                                         "_ci_from_pi": kind == 'CI', "source_document_type": 'PI'}
                files = render_master_trade_draft(kind, {"document_type": kind}, env)
                self.assertEqual(set(files), {"pdf", "xlsx", "html"})
                self.assertTrue(all(not file["final"] and not file["sendable"]
                                    for file in files.values()))
        self.assertEqual([kind for kind, _ in expected], ["PI", "PO", "CI", "PL"])
        self.assertTrue(all(keys == {"bank_details", "seal_path", "logo_path"}
                            for _, keys in expected))

    @patch("Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.validate_and_calculate")
    def test_pi_requires_complete_bank_profile(self, validate):
        validate.return_value = {"blocking_issues": [], "ready_for_issue": True}
        with self.assertRaisesRegex(ValueError, "은행정보"):
            render_master_trade_draft("PI", {}, {})

    def test_ci_without_original_pi_is_blocked_before_seal_or_renderer(self):
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as module
        with patch.object(module,'validate_and_calculate',return_value={'document_type':'CI','blocking_issues':[],'ready_for_issue':True}),patch.object(module,'resolve_company_seal') as seal:
            with self.assertRaisesRegex(ValueError,'attached PI'):
                module.render_master_trade_draft('CI',{'document_type':'CI'}, {})
            seal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
