"""Streamlit UI click-test: PDF deletion is user-initiated and owner-scoped.

All data, Storage and SMTP are mocked. No real document is deleted.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"
IDENT = "18d53c20-c2bc-493d-b992-6a1611f99857"
PDF = b"%PDF-1.4\nSynthetic contract\n%%EOF"
ROW = {
    "id": IDENT, "kind": "CONTRACT", "status": "final",
    "filename": "TEST-SUPPLY-CONTRACT.pdf",
    "created_at": "2026-11-18T00:00:00+00:00",
    "content_sha256": "a" * 64,
    "storage_path": "synthetic/2026/11/" + IDENT + ".pdf",
}


class PdfDeleteButtonUITests(unittest.TestCase):
    def test_final_pdf_only_deleted_after_click_and_confirmation(self):
        with patch(
            "Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
            return_value="owner@example.test",
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
            return_value=([], None),
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.pdf_archive_page.archive.list_documents",
            return_value=[ROW],
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.pdf_archive_page.archive.load_pdf",
            return_value=(ROW, PDF),
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.pdf_archive_page.archive.delete_document",
        ) as delete, patch(
            "Quotation_KEKOREA.orchestration.ui.pdf_archive_page._env",
            return_value={},
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.pdf_archive_page._preview",
        ), patch(
            "Quotation_KEKOREA.orchestration.ui.saved_contracts.render_saved_contracts",
        ):
            app = AppTest.from_file(str(PAGE), default_timeout=35).run()
            app.radio(key="master_page").set_value("저장된 계약서").run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            app.button(key="pdf_row_" + IDENT).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertTrue(app.button(key="master_pdf_delete_" + IDENT).disabled)
            delete.assert_not_called()
            app.checkbox(key="master_pdf_delete_confirm_" + IDENT).check().run()
            self.assertFalse(app.button(key="master_pdf_delete_" + IDENT).disabled)
            app.button(key="master_pdf_delete_" + IDENT).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            delete.assert_called_once_with({}, "owner@example.test", IDENT)


if __name__ == "__main__":
    unittest.main()
