"""DRAFT document generation and new pending PDF archive UI regression tests."""
import unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.orchestration.workflows.draft_files import create_review_files
from Quotation_KEKOREA.orchestration.tests.test_draft_files import trade_fixture
from Quotation_KEKOREA.contracts.models import new_snapshot

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


class DraftFileUiTests(unittest.TestCase):
    def test_trade_review_engine_is_not_replaced_by_pdf_archive(self):
        files = create_review_files("PI", trade_fixture())
        self.assertIn("docx", files)
        self.assertNotIn("pdf", files)
        self.assertFalse(files["docx"]["sendable"])

    def test_no_blank_contract_draft_is_exported(self):
        with self.assertRaises(ValueError):
            create_review_files("CONTRACT", new_snapshot("sample", "sale", "ko"))

    def test_pending_sidebar_is_for_real_pdfs_not_mock_email(self):
        with patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                   return_value="synthetic@example.test"), patch(
            "Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
            return_value=([], None)
        ), patch(
            "Quotation_KEKOREA.orchestration.workflows.pdf_archive.list_documents",
            return_value=[]
        ):
            app = AppTest.from_file(str(UI)).run()
            app.radio[0].set_value("발송 대기").run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertTrue(any("DRAFT PDF" in x.value for x in app.subheader))


if __name__ == "__main__":
    unittest.main()
